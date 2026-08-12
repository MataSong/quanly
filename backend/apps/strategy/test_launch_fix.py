import pytest
from unittest.mock import MagicMock

from apps.strategy import docker_env


@pytest.fixture(autouse=True)
def _reset():
    docker_env.reset_cache()
    yield
    docker_env.reset_cache()


def _client_with_project(project):
    client = MagicMock()
    self_container = MagicMock()
    self_container.labels = {"com.docker.compose.project": project}
    client.containers.get.return_value = self_container
    return client


def test_compose_project_from_label():
    client = _client_with_project("myproj")
    assert docker_env.compose_project(client) == "myproj"


def test_volume_and_network_names_follow_project():
    client = _client_with_project("myproj")
    assert docker_env.scripts_volume_name(client) == "myproj_strategy_scripts"
    assert docker_env.strategy_network_name(client) == "myproj_default"


def test_compose_project_fallback_when_no_label(monkeypatch):
    client = MagicMock()
    client.containers.get.side_effect = Exception("not found")
    monkeypatch.delenv("COMPOSE_PROJECT_NAME", raising=False)
    assert docker_env.compose_project(client) == "quanly"


def test_run_strategy_task_uses_dynamic_names_and_returns(monkeypatch, db, tmp_path):
    from django.contrib.auth import get_user_model
    from apps.strategy.models import Strategy, StrategyRun
    from apps.strategy import tasks, docker_env

    user = get_user_model().objects.create_user("t1", password="pass12345")
    strat = Strategy.objects.create(
        user=user, name="s", source="def on_tick(ctx):\n    pass\n"
    )
    run = StrategyRun.objects.create(
        user=user, strategy=strat, env="sim", symbol="BTC-USDT"
    )

    monkeypatch.setattr(
        docker_env, "scripts_volume_name", lambda client=None: "proj_strategy_scripts"
    )
    monkeypatch.setattr(
        docker_env, "strategy_network_name", lambda client=None: "proj_default"
    )
    monkeypatch.setattr(tasks, "SCRIPTS_DIR", str(tmp_path))

    captured = {}
    fake_container = MagicMock()
    fake_container.id = "cid123"

    class FakeClient:
        class containers:
            @staticmethod
            def run(image, **kw):
                captured["image"] = image
                captured["volumes"] = kw.get("volumes")
                captured["network"] = kw.get("network")
                return fake_container

    import docker

    monkeypatch.setattr(docker, "from_env", lambda: FakeClient(), raising=False)
    monkeypatch.setattr(tasks, "_publish_log", lambda *a, **k: None)

    tasks.run_strategy_task(run.id)  # 必须能返回(不阻塞)

    assert "proj_strategy_scripts" in str(captured["volumes"])
    assert captured["network"] == "proj_default"
    run.refresh_from_db()
    assert run.status == StrategyRun.Status.RUNNING
    assert run.container_id == "cid123"


def test_launch_error_classified_image_not_found(monkeypatch, db, tmp_path):
    from django.contrib.auth import get_user_model
    from apps.strategy.models import Strategy, StrategyRun
    from apps.strategy import tasks

    user = get_user_model().objects.create_user("t2", password="pass12345")
    strat = Strategy.objects.create(user=user, name="s", source="x")
    run = StrategyRun.objects.create(
        user=user, strategy=strat, env="sim", symbol="BTC-USDT"
    )
    monkeypatch.setattr(tasks, "SCRIPTS_DIR", str(tmp_path))

    class ImageNotFound(Exception):
        pass

    class FakeClient:
        class containers:
            @staticmethod
            def run(*a, **k):
                raise ImageNotFound("No such image: quanly-strategy-runner")

    import docker

    monkeypatch.setattr(docker, "from_env", lambda: FakeClient(), raising=False)

    logged = {}
    monkeypatch.setattr(
        tasks,
        "_publish_log",
        lambda rid, msg, lvl="info": logged.update(msg=msg, lvl=lvl),
    )
    tasks.run_strategy_task(run.id)
    run.refresh_from_db()
    assert run.status == StrategyRun.Status.ERROR
    assert "image_not_found" in logged["msg"]
    assert logged["lvl"] == "error"


def test_runner_syntax_compiles():
    import pathlib

    # test 位于 backend/apps/strategy/;runner 在仓库根的 strategy-runner/
    root = pathlib.Path(__file__).resolve().parents[3]
    src = (root / "strategy-runner" / "runner.py").read_text()
    compile(src, "runner.py", "exec")  # 语法正确即通过


def test_runner_logstream_forwards_lines_to_ctx():
    """验证 _LogStream 按整行把 stdout 转发给 ctx.log(print 也能上报)。"""
    import io
    import pathlib
    import sys
    import types

    root = pathlib.Path(__file__).resolve().parents[3]
    src = (root / "strategy-runner" / "runner.py").read_text()
    # runner 顶层 import requests;注入一个假的以便 exec
    fake_requests = types.ModuleType("requests")
    fake_requests.get = lambda *a, **k: None
    fake_requests.post = lambda *a, **k: None
    sys.modules.setdefault("requests", fake_requests)
    ns = {}
    exec(compile(src, "runner.py", "exec"), ns)
    LogStream = ns["_LogStream"]

    captured = []

    class FakeCtx:
        def log(self, msg):
            captured.append(msg)

    orig = io.StringIO()
    stream = LogStream(FakeCtx(), orig)
    stream.write("hello\n")
    stream.write("partial ")  # 未换行,不应立即转发
    stream.write("line\n")
    assert captured == ["hello", "partial line"]
    assert "hello" in orig.getvalue()  # 原始流仍收到输出


def test_run_strategy_rejects_bad_interval(db):
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient
    from apps.strategy.models import Strategy

    user = get_user_model().objects.create_user("t3", password="pass12345")
    strat = Strategy.objects.create(user=user, name="s", source="x")
    c = APIClient()
    c.force_authenticate(user)
    r = c.post(
        f"/api/strategies/{strat.id}/run",
        {"symbol": "BTC-USDT", "interval_sec": 0},
        format="json",
    )
    assert r.status_code == 400
    assert "detail_key" in r.data


def test_run_strategy_rejects_empty_symbol(db):
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient
    from apps.strategy.models import Strategy

    user = get_user_model().objects.create_user("t4", password="pass12345")
    strat = Strategy.objects.create(user=user, name="s", source="x")
    c = APIClient()
    c.force_authenticate(user)
    r = c.post(
        f"/api/strategies/{strat.id}/run",
        {"symbol": "  ", "interval_sec": 5},
        format="json",
    )
    assert r.status_code == 400
    assert r.data["detail_key"] == "strategy.launch.err.symbol_required"
