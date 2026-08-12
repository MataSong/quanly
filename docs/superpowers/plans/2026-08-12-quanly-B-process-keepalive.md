# 子项目 B — 部署升级不中断 + 策略进程保活 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: 本计划在当前会话直接执行(用户约束:严禁 git 操作)。每个 task 以运行测试作为完成检查点。Steps 用 checkbox。

**Goal:** 让策略进程 7×24 不间断:worker/backend 重启、部署升级重建容器时运行中策略零中断,容器意外退出可自动恢复。

**Architecture:** ①策略容器加 restart_policy 自治;②StrategyRun 加 last_heartbeat + runner 上报心跳;③worker 启动时重扫 RUNNING run,容器活着则对齐、死了则自动重拉;④部署升级只重建无状态服务,策略容器(不在 compose)天然不动。

**Tech Stack:** Django + DRF + Celery(worker_ready 信号) + docker SDK;strategy-runner 容器;pytest。

## Global Constraints

- **严禁任何 git 操作**:所有 task 不含 git 命令;以运行测试作为完成检查点。
- 不破坏 OKX 适配器、虚实盘 `env` 隔离、回测、runner_api 鉴权模型。
- 不引入 supervisor / 常驻进程(保持 DooD 隔离契约)。
- docker SDK 逻辑单测一律 mock docker client,不真起容器。
- 新增前端文案(若有)i18n zh/en 对齐。
- 测试:`cd backend && ../.venv/bin/python -m pytest apps/strategy/ -v`。
- 依赖子项目 A 已完成:`tasks.py` 已用 `docker_env` 动态卷名/网络名、`run_strategy_task` 起容器后不阻塞。

---

## File Structure

- `backend/apps/strategy/tasks.py`（改）：把 `containers.run(...)` 段抽成 `_launch_container(run)`（供启动与恢复共用）；加 `restart_policy`。
- `backend/apps/strategy/models.py` + 新迁移（改）：`StrategyRun.last_heartbeat`。
- `backend/apps/strategy/runner_api.py`（改）：新增 `heartbeat` 端点。
- `backend/apps/strategy/urls.py`（改）：`strategy-api/heartbeat` 路由。
- `strategy-runner/runner.py`（改）：每轮 tick 上报心跳。
- `backend/apps/strategy/recover.py`（新建）：`recover_running_runs()`。
- `backend/config/celery.py`（改）：`worker_ready` 信号触发恢复。
- `backend/apps/strategy/management/commands/recover_strategies.py`（新建）：手动命令。
- `deploy/deploy.sh`（改）：注释 + 升级后策略容器计数。
- 测试写入 `backend/apps/strategy/test_keepalive.py`（新建）。

---

### Task 1: 抽出 _launch_container + 加 restart_policy

**Files:**
- Modify: `backend/apps/strategy/tasks.py`
- Test: `backend/apps/strategy/test_keepalive.py`

**Interfaces:**
- Produces: `_launch_container(run) -> container`：起策略容器（含 `restart_policy={"Name":"unless-stopped"}`），返回 docker container 对象。`run_strategy_task` 改为调用它。

- [ ] **Step 1: 写失败测试 —— 启动带 restart_policy**

```python
# backend/apps/strategy/test_keepalive.py
import pytest
from unittest.mock import MagicMock


def test_launch_container_sets_restart_policy(monkeypatch, db, tmp_path):
    from django.contrib.auth import get_user_model
    from apps.strategy.models import Strategy, StrategyRun
    from apps.strategy import tasks, docker_env

    user = get_user_model().objects.create_user("kb1", password="pass12345")
    strat = Strategy.objects.create(user=user, name="s", source="def on_tick(ctx):\n    pass\n")
    run = StrategyRun.objects.create(user=user, strategy=strat, env="sim", symbol="BTC-USDT")

    monkeypatch.setattr(docker_env, "scripts_volume_name", lambda client=None: "p_scripts")
    monkeypatch.setattr(docker_env, "strategy_network_name", lambda client=None: "p_default")
    monkeypatch.setattr(tasks, "SCRIPTS_DIR", str(tmp_path))

    captured = {}
    fake_container = MagicMock(); fake_container.id = "cid"

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
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest apps/strategy/test_keepalive.py -q`
Expected: FAIL（`_launch_container` 不存在）

- [ ] **Step 3: 重构 tasks.py —— 抽出 _launch_container 并加 restart_policy**

把 `run_strategy_task` 内从 `client = docker.from_env()` 到 `containers.run(...)` 返回容器这段，抽成模块级函数：

```python
def _launch_container(run):
    """起一个策略隔离容器并返回 container 对象。启动与恢复共用。"""
    import docker

    run_id = run.id
    os.makedirs(SCRIPTS_DIR, exist_ok=True)
    script_path = os.path.join(SCRIPTS_DIR, f"run_{run_id}.py")
    with open(script_path, "w") as f:
        f.write(run.strategy.source)

    client = docker.from_env()
    return client.containers.run(
        settings.STRATEGY_RUNNER_IMAGE,
        detach=True,
        name=f"quanly-strategy-{run_id}",
        environment={
            "RUN_ID": str(run_id),
            "RUN_TOKEN": run.run_token,
            "BACKEND_URL": settings.BACKEND_INTERNAL_URL,
            "SYMBOL": run.symbol,
            "INTERVAL": str(run.interval_sec),
            "SCRIPT_PATH": f"/scripts/run_{run_id}.py",
        },
        volumes={docker_env.scripts_volume_name(client): {"bind": "/scripts", "mode": "ro"}},
        network=docker_env.strategy_network_name(client),
        mem_limit="256m",
        nano_cpus=500_000_000,
        cap_drop=["ALL"],
        read_only=True,
        tmpfs={"/tmp": ""},
        restart_policy={"Name": "unless-stopped"},
    )
```

`run_strategy_task` 改为：

```python
@shared_task
def run_strategy_task(run_id):
    run = StrategyRun.objects.select_related("strategy").get(id=run_id)
    try:
        container = _launch_container(run)
    except Exception as e:  # noqa
        run.status = StrategyRun.Status.ERROR
        run.save()
        _publish_log(run_id, f"启动容器失败[{_classify_launch_error(e)}]: {e}", "error")
        return
    run.container_id = container.id
    run.status = StrategyRun.Status.RUNNING
    run.save()
    _publish_log(run_id, "策略容器已启动", "info")
```

（`import docker` 移入 `_launch_container`；确保 `run_strategy_task` 顶部不再重复 `import docker` 造成未用。）

- [ ] **Step 4: 运行确认通过 + A 的测试不回归**

Run: `cd backend && ../.venv/bin/python -m pytest apps/strategy/test_keepalive.py apps/strategy/test_launch_fix.py -q`
Expected: PASS（全部；注意 `test_launch_fix.py::test_run_strategy_task_uses_dynamic_names_and_returns` 断言的 volumes/network 仍成立）

---

### Task 2: StrategyRun.last_heartbeat 字段 + 迁移

**Files:**
- Modify: `backend/apps/strategy/models.py`
- Create: `backend/apps/strategy/migrations/00NN_run_last_heartbeat.py`（由 makemigrations 生成）
- Test: `backend/apps/strategy/test_keepalive.py`

**Interfaces:**
- Produces: `StrategyRun.last_heartbeat`（`DateTimeField(null=True, blank=True)`）。

- [ ] **Step 1: 加字段**

在 `StrategyRun` 的 `stopped_at` 后加：

```python
    last_heartbeat = models.DateTimeField(null=True, blank=True)
```

- [ ] **Step 2: 生成迁移**

Run: `cd backend && ../.venv/bin/python manage.py makemigrations strategy`
Expected: 生成新迁移文件，含 `AddField last_heartbeat`。

- [ ] **Step 3: 写测试 —— 字段存在且默认 None**

```python
def test_run_has_last_heartbeat_field(db):
    from django.contrib.auth import get_user_model
    from apps.strategy.models import Strategy, StrategyRun
    user = get_user_model().objects.create_user("kb2", password="pass12345")
    strat = Strategy.objects.create(user=user, name="s", source="x")
    run = StrategyRun.objects.create(user=user, strategy=strat, env="sim", symbol="BTC-USDT")
    assert run.last_heartbeat is None
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && ../.venv/bin/python -m pytest apps/strategy/test_keepalive.py::test_run_has_last_heartbeat_field -q`
Expected: PASS

---

### Task 3: heartbeat 端点 + runner 上报

**Files:**
- Modify: `backend/apps/strategy/runner_api.py`、`backend/apps/strategy/urls.py`
- Modify: `strategy-runner/runner.py`
- Test: `backend/apps/strategy/test_keepalive.py`

**Interfaces:**
- Consumes: `_run_from_token`（runner_api 现有）、`StrategyRun.last_heartbeat`（Task 2）。
- Produces: `POST /api/strategy-api/heartbeat`（RUN_TOKEN 鉴权）→ 更新该 run `last_heartbeat=now()`，返回 `{"ok": True}`。

- [ ] **Step 1: 写失败测试**

```python
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
    r = c.post("/api/strategy-api/heartbeat", {}, format="json", HTTP_X_RUN_TOKEN=run.run_token)
    assert r.status_code == 200
    run.refresh_from_db()
    assert run.last_heartbeat is not None
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest apps/strategy/test_keepalive.py::test_heartbeat_updates_last_heartbeat -q`
Expected: FAIL（404，路由未定义）

- [ ] **Step 3: 加 heartbeat 端点**

`runner_api.py` 末尾（`_infer_level` 之前）加：

```python
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def heartbeat(request):
    run = _run_from_token(request)
    if not run:
        return Response({"detail": "invalid run token"}, status=403)
    from django.utils import timezone

    run.last_heartbeat = timezone.now()
    run.save(update_fields=["last_heartbeat"])
    return Response({"ok": True})
```

`urls.py` 在 `strategy-api/log` 后加：

```python
    path("strategy-api/heartbeat", runner_api.heartbeat),
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && ../.venv/bin/python -m pytest apps/strategy/test_keepalive.py::test_heartbeat_updates_last_heartbeat -q`
Expected: PASS

- [ ] **Step 5: runner 每轮 tick 上报心跳**

`strategy-runner/runner.py` 的 `Ctx` 加方法：

```python
    def heartbeat(self):
        try:
            requests.post(
                f"{BACKEND_URL}/api/strategy-api/heartbeat",
                json={},
                headers=_HEADERS,
                timeout=5,
            )
        except Exception:
            pass
```

`main()` 的 on_tick 轮询循环里，每轮调用一次（在 `on_tick(ctx)` 后）：

```python
        while True:
            try:
                on_tick(ctx)
            except Exception as e:
                ctx.log("on_tick error: %s" % e)
            ctx.heartbeat()
            time.sleep(INTERVAL)
```

- [ ] **Step 6: runner 语法编译测试**

```python
def test_runner_has_heartbeat():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[3]
    src = (root / "strategy-runner" / "runner.py").read_text()
    compile(src, "runner.py", "exec")
    assert "def heartbeat" in src and "ctx.heartbeat()" in src
```

Run: `cd backend && ../.venv/bin/python -m pytest apps/strategy/test_keepalive.py::test_runner_has_heartbeat -q`
Expected: PASS

---

### Task 4: recover_running_runs 恢复逻辑

**Files:**
- Create: `backend/apps/strategy/recover.py`
- Test: `backend/apps/strategy/test_keepalive.py`

**Interfaces:**
- Consumes: `StrategyRun`、`tasks._launch_container`（Task 1）、`docker` SDK。
- Produces: `recover_running_runs(client=None) -> dict`：扫所有 `status=RUNNING` run；容器存在且 running → 计入 `alive`；否则调 `_launch_container` 重拉 → 计入 `relaunched`；重拉失败 → run 置 error 计入 `failed`。返回 `{"alive": n, "relaunched": n, "failed": n}`。幂等。

- [ ] **Step 1: 写失败测试 —— 死容器被重拉**

```python
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

    # docker client: 查容器抛 NotFound(已死)
    class FakeClient:
        class containers:
            @staticmethod
            def get(name):
                raise Exception("not found")

    relaunched = {}
    monkeypatch.setattr(tasks, "_launch_container",
                        lambda r: relaunched.setdefault("id", r.id) or __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock(id="new"))

    result = recover.recover_running_runs(client=FakeClient())
    assert result["relaunched"] == 1
    assert relaunched["id"] == run.id


def test_recover_keeps_alive_container(monkeypatch, db):
    from django.contrib.auth import get_user_model
    from apps.strategy.models import Strategy, StrategyRun
    from apps.strategy import recover, tasks
    from unittest.mock import MagicMock

    user = get_user_model().objects.create_user("kb5", password="pass12345")
    strat = Strategy.objects.create(user=user, name="s", source="x")
    StrategyRun.objects.create(
        user=user, strategy=strat, env="sim", symbol="BTC-USDT",
        status=StrategyRun.Status.RUNNING, container_id="live",
    )

    alive_container = MagicMock(); alive_container.status = "running"
    class FakeClient:
        class containers:
            @staticmethod
            def get(name):
                return alive_container

    called = {"n": 0}
    monkeypatch.setattr(tasks, "_launch_container", lambda r: called.update(n=called["n"] + 1))
    result = recover.recover_running_runs(client=FakeClient())
    assert result["alive"] == 1
    assert called["n"] == 0  # 活着的不重拉
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest apps/strategy/test_keepalive.py -k recover -q`
Expected: FAIL（`recover` 模块不存在）

- [ ] **Step 3: 实现 recover.py**

```python
"""worker/backend 重启后恢复运行中的策略。

扫 DB 中 status=RUNNING 的 StrategyRun:容器还活着则对齐(不动),
容器已死(NotFound/exited)则自动重拉同参数容器。幂等,可重复执行。
"""
from .models import StrategyRun


def _get_client(client):
    if client is not None:
        return client
    import docker

    return docker.from_env()


def recover_running_runs(client=None) -> dict:
    from . import tasks

    c = _get_client(client)
    result = {"alive": 0, "relaunched": 0, "failed": 0}
    runs = StrategyRun.objects.filter(status=StrategyRun.Status.RUNNING)
    for run in runs:
        name = f"quanly-strategy-{run.id}"
        alive = False
        try:
            container = c.containers.get(name)
            alive = getattr(container, "status", "") == "running"
        except Exception:
            alive = False
        if alive:
            result["alive"] += 1
            continue
        try:
            container = tasks._launch_container(run)
            if container is not None and getattr(container, "id", None):
                run.container_id = container.id
                run.save(update_fields=["container_id"])
            result["relaunched"] += 1
            tasks._publish_log(run.id, "worker 重启,策略已自动恢复", "info")
        except Exception as e:  # noqa
            run.status = StrategyRun.Status.ERROR
            run.save(update_fields=["status"])
            result["failed"] += 1
            tasks._publish_log(run.id, f"恢复失败: {e}", "error")
    return result
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && ../.venv/bin/python -m pytest apps/strategy/test_keepalive.py -k recover -q`
Expected: PASS（2 项）

---

### Task 5: worker_ready 信号 + 手动命令

**Files:**
- Modify: `backend/config/celery.py`
- Create: `backend/apps/strategy/management/commands/recover_strategies.py`
- Create: `backend/apps/strategy/management/__init__.py`、`.../commands/__init__.py`（若不存在）
- Test: `backend/apps/strategy/test_keepalive.py`

**Interfaces:**
- Consumes: `recover.recover_running_runs`（Task 4）。
- Produces: Celery `worker_ready` 信号触发恢复；`python manage.py recover_strategies` 手动命令。

- [ ] **Step 1: celery.py 连 worker_ready 信号**

```python
from celery.signals import worker_ready


@worker_ready.connect
def _recover_on_worker_ready(**kwargs):
    try:
        from apps.strategy.recover import recover_running_runs

        recover_running_runs()
    except Exception:
        pass
```

（加在 `app.autodiscover_tasks()` 之后。）

- [ ] **Step 2: 建 management command**

`backend/apps/strategy/management/commands/recover_strategies.py`：

```python
from django.core.management.base import BaseCommand

from apps.strategy.recover import recover_running_runs


class Command(BaseCommand):
    help = "扫描 RUNNING 策略,容器已死则自动重拉(部署/重启后手动恢复用)。"

    def handle(self, *args, **options):
        result = recover_running_runs()
        self.stdout.write(self.style.SUCCESS(f"恢复完成: {result}"))
```

确保 `management/__init__.py` 与 `management/commands/__init__.py` 存在（空文件）。

- [ ] **Step 3: 写命令 smoke 测试**

```python
def test_recover_command_runs(monkeypatch, db):
    from django.core.management import call_command
    from apps.strategy import recover

    monkeypatch.setattr(recover, "recover_running_runs", lambda: {"alive": 0, "relaunched": 0, "failed": 0})
    call_command("recover_strategies")  # 不抛异常即通过
```

- [ ] **Step 4: 运行确认通过 + 全量回归**

Run: `cd backend && ../.venv/bin/python -m pytest apps/strategy/ -q`
Expected: PASS（strategy 全绿）

---

### Task 6: deploy.sh 升级不碰策略容器 + 计数

**Files:**
- Modify: `deploy/deploy.sh`

**Interfaces:**
- Produces: `hot_update()` 结束打印当前 `quanly-strategy-*` 容器数;注释说明策略容器不受升级影响。

- [ ] **Step 1: hot_update 末尾加策略容器计数与说明**

在 `hot_update()` 的清理步骤后、结束语前加：

```bash
  # 策略容器(quanly-strategy-*)不在 compose services 内,全量重建不会 recreate 它们,
  # 升级期间保持运行(restart_policy=unless-stopped),实现"运行中策略零中断"。
  RUNNING_STRATEGIES=$(docker ps --filter "name=quanly-strategy-" --format '{{.Names}}' | wc -l | tr -d ' ')
  say "运行中策略容器数: ${RUNNING_STRATEGIES}(升级不影响其运行)。"
```

- [ ] **Step 2: 检查点**

Run: `grep -n "quanly-strategy-" deploy/deploy.sh`
Expected: 命中新增计数逻辑与注释。

- [ ] **Step 3: bash 语法自检**

Run: `bash -n deploy/deploy.sh && echo "SYNTAX OK"`
Expected: 输出 `SYNTAX OK`。

---

## Self-Review

**Spec coverage：** B spec 四项 —— B1 restart_policy→Task1；B2 last_heartbeat+心跳→Task2+3；B3 recover+worker_ready+命令→Task4+5；B4 deploy 不碰策略容器→Task6。验收标准 1(worker 重启策略续跑)→Task1+4+5；2(升级零中断)→Task6；3(kill 后重拉)→Task4；4(心跳)→Task3；5(回归)→Task5。

**Placeholder scan：** 无 TBD；每步含实际代码。迁移文件名由 makemigrations 生成（已注明）。

**Type consistency：** `_launch_container(run)`（Task1）→ Task4 recover 调用一致；`recover_running_runs(client=None)->dict` 返回 `alive/relaunched/failed`（Task4）→ Task5 命令/信号使用一致；`last_heartbeat`（Task2）→ Task3 heartbeat 端点写入一致。

## Execution Handoff

计划保存至 `docs/superpowers/plans/2026-08-12-quanly-B-process-keepalive.md`，在当前会话逐 task 执行。
