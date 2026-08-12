import pytest
from unittest.mock import MagicMock


def test_launch_container_sets_restart_policy(monkeypatch, db, tmp_path):
    from django.contrib.auth import get_user_model
    from apps.strategy.models import Strategy, StrategyRun
    from apps.strategy import tasks, docker_env

    user = get_user_model().objects.create_user("kb1", password="pass12345")
    strat = Strategy.objects.create(
        user=user, name="s", source="def on_tick(ctx):\n    pass\n"
    )
    run = StrategyRun.objects.create(
        user=user, strategy=strat, env="sim", symbol="BTC-USDT"
    )

    monkeypatch.setattr(docker_env, "scripts_volume_name", lambda client=None: "p_scripts")
    monkeypatch.setattr(docker_env, "strategy_network_name", lambda client=None: "p_default")
    monkeypatch.setattr(tasks, "SCRIPTS_DIR", str(tmp_path))

    captured = {}
    fake_container = MagicMock()
    fake_container.id = "cid"

    class FakeClient:
        class containers:
            @staticmethod
            def run(image, **kw):
                captured.update(kw)
                return fake_container

    import docker

    monkeypatch.setattr(docker, "from_env", lambda: FakeClient(), raising=False)

    tasks._launch_container(run)
    assert captured["restart_policy"] == {"Name": "unless-stopped"}


def test_run_has_last_heartbeat_field(db):
    from django.contrib.auth import get_user_model
    from apps.strategy.models import Strategy, StrategyRun

    user = get_user_model().objects.create_user("kb2", password="pass12345")
    strat = Strategy.objects.create(user=user, name="s", source="x")
    run = StrategyRun.objects.create(
        user=user, strategy=strat, env="sim", symbol="BTC-USDT"
    )
    assert run.last_heartbeat is None


def test_heartbeat_updates_last_heartbeat(db):
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient
    from apps.strategy.models import Strategy, StrategyRun

    user = get_user_model().objects.create_user("kb3", password="pass12345")
    strat = Strategy.objects.create(user=user, name="s", source="x")
    run = StrategyRun.objects.create(
        user=user, strategy=strat, env="sim", symbol="BTC-USDT",
        status=StrategyRun.Status.RUNNING,
    )
    c = APIClient()
    r = c.post(
        "/api/strategy-api/heartbeat", {}, format="json", HTTP_X_RUN_TOKEN=run.run_token
    )
    assert r.status_code == 200
    run.refresh_from_db()
    assert run.last_heartbeat is not None


def test_runner_has_heartbeat():
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[3]
    src = (root / "strategy-runner" / "runner.py").read_text()
    compile(src, "runner.py", "exec")
    assert "def heartbeat" in src and "ctx.heartbeat()" in src


def test_recover_relaunches_dead_container(monkeypatch, db):
    from django.contrib.auth import get_user_model
    from apps.strategy.models import Strategy, StrategyRun
    from apps.strategy import recover, tasks

    user = get_user_model().objects.create_user("kb4", password="pass12345")
    strat = Strategy.objects.create(user=user, name="s", source="x")
    run = StrategyRun.objects.create(
        user=user, strategy=strat, env="sim", symbol="BTC-USDT",
        status=StrategyRun.Status.RUNNING, container_id="old",
    )

    class FakeClient:
        class containers:
            @staticmethod
            def get(name):
                raise Exception("not found")

    relaunched = {}

    def fake_launch(r):
        relaunched["id"] = r.id
        return MagicMock(id="new")

    monkeypatch.setattr(tasks, "_launch_container", fake_launch)
    monkeypatch.setattr(tasks, "_publish_log", lambda *a, **k: None)

    result = recover.recover_running_runs(client=FakeClient())
    assert result["relaunched"] == 1
    assert relaunched["id"] == run.id


def test_recover_keeps_alive_container(monkeypatch, db):
    from django.contrib.auth import get_user_model
    from apps.strategy.models import Strategy, StrategyRun
    from apps.strategy import recover, tasks

    user = get_user_model().objects.create_user("kb5", password="pass12345")
    strat = Strategy.objects.create(user=user, name="s", source="x")
    StrategyRun.objects.create(
        user=user, strategy=strat, env="sim", symbol="BTC-USDT",
        status=StrategyRun.Status.RUNNING, container_id="live",
    )

    alive_container = MagicMock()
    alive_container.status = "running"

    class FakeClient:
        class containers:
            @staticmethod
            def get(name):
                return alive_container

    called = {"n": 0}
    monkeypatch.setattr(tasks, "_launch_container", lambda r: called.update(n=called["n"] + 1))
    monkeypatch.setattr(tasks, "_publish_log", lambda *a, **k: None)

    result = recover.recover_running_runs(client=FakeClient())
    assert result["alive"] == 1
    assert called["n"] == 0


def test_recover_command_runs(monkeypatch, db):
    from django.core.management import call_command
    from apps.strategy import recover

    monkeypatch.setattr(
        recover, "recover_running_runs",
        lambda: {"alive": 0, "relaunched": 0, "failed": 0},
    )
    call_command("recover_strategies")
