# 子项目 A — 策略启动故障修复 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 Docker 环境下策略任务创建后无法启动的问题，使策略可正常创建→启动→运行→输出日志。

**Architecture:** 三处根因分别修：①worker 动态解析 compose 项目名拼卷名/网络名（不再硬编码 `quanly`）；②strategy-runner 镜像纳入 compose 构建；③拆分容器启动与日志采集、解除 worker 阻塞，日志改由 runner 主动上报。附带启动前置校验与分类报错。

**Tech Stack:** Django + DRF + Celery + docker SDK（Docker-out-of-Docker）；strategy-runner Python 容器；前端 Vue3 + i18n。

## Global Constraints

- **严禁任何 git 操作**（用户硬约束）：本计划所有 task **不含 git add/commit/push**；每个 task 以"运行测试验证通过"作为完成检查点。
- 不破坏 OKX 适配器层、虚实盘 `env` 隔离、回测引擎、runner_api 鉴权模型。
- 本子项目**不改** Strategy/StrategyRun/StrategyLog 表结构（`last_heartbeat` 留给子项目 B）。
- 新增前端文案走 i18n，`zh-CN.ts` 与 `en-US.ts` key **完全对齐**。
- 后端测试用 sqlite + pytest；装包用 `uv pip install --python .venv/bin/python --index-url https://pypi.tuna.tsinghua.edu.cn/simple`。
- docker SDK 相关逻辑单测一律 **mock docker client**，不真起容器。
- 验收后端命令：`.venv/bin/python -m pytest backend/apps/strategy/ -v`（在 backend 目录设 `DJANGO_SETTINGS_MODULE`，沿用现有 pytest 配置）。

---

## File Structure

- `backend/apps/strategy/docker_env.py`（新建）：`compose_project()`、`scripts_volume_name()`、`strategy_network_name()` —— 集中所有"从运行环境推导 docker 项目名/卷名/网络名"的逻辑，便于单测。
- `backend/apps/strategy/tasks.py`（改）：启动改用 docker_env 的名字；`containers.run` 异常分类；启动后不再阻塞 attach 日志。
- `strategy-runner/runner.py`（改）：`main()` 里包装 stdout，使 `print` 也经 `ctx.log()` 上报。
- `backend/apps/strategy/views.py`（改）：`run_strategy` 加轻量前置校验。
- `docker-compose.yml`（改）：新增一次性构建服务 `strategy-runner-build`。
- `deploy/deploy.sh`（改）：注释说明 compose 已负责构建，`build_strategy_runner` 保留为兜底。
- `frontend/src/i18n/zh-CN.ts` / `en-US.ts`（改）：策略启动分类报错 key。
- `backend/apps/strategy/test_launch_fix.py`（新建）：本子项目全部单测。

---

### Task 1: docker_env —— 动态解析 compose 项目名 / 卷名 / 网络名

**Files:**
- Create: `backend/apps/strategy/docker_env.py`
- Test: `backend/apps/strategy/test_launch_fix.py`

**Interfaces:**
- Produces:
  - `compose_project(client=None) -> str`：解析 worker 自身容器的 label `com.docker.compose.project`；失败回退 `os.environ` 约定或 `"quanly"`。
  - `scripts_volume_name(client=None) -> str`：返回 `f"{compose_project(client)}_strategy_scripts"`。
  - `strategy_network_name(client=None) -> str`：优先 `settings.STRATEGY_DOCKER_NETWORK` 若被显式设为非默认值则用之；否则 `f"{compose_project(client)}_default"`。
  - 模块级缓存 `_cache`，避免重复解析；提供 `reset_cache()` 供测试。

- [ ] **Step 1: 写失败测试 —— label 解析成功**

```python
# backend/apps/strategy/test_launch_fix.py
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
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest backend/apps/strategy/test_launch_fix.py -v`
Expected: FAIL（`ModuleNotFoundError: apps.strategy.docker_env`）

- [ ] **Step 3: 实现 docker_env**

```python
# backend/apps/strategy/docker_env.py
"""从运行环境推导策略容器所需的 docker 项目名/卷名/网络名。

celery-worker 自身也是 compose 起的容器,带 label com.docker.compose.project,
据此拿到真实项目名,拼出正确的卷名/网络名——不再硬编码假设项目名为 quanly。
"""
import os
import socket

from django.conf import settings

_cache = {}


def reset_cache():
    _cache.clear()


def _get_client(client):
    if client is not None:
        return client
    import docker
    return docker.from_env()


def compose_project(client=None) -> str:
    if "project" in _cache:
        return _cache["project"]
    project = None
    try:
        c = _get_client(client)
        self_container = c.containers.get(socket.gethostname())
        project = self_container.labels.get("com.docker.compose.project")
    except Exception:
        project = None
    if not project:
        project = os.environ.get("COMPOSE_PROJECT_NAME") or "quanly"
    _cache["project"] = project
    return project


def scripts_volume_name(client=None) -> str:
    return f"{compose_project(client)}_strategy_scripts"


def strategy_network_name(client=None) -> str:
    # 若用户显式覆盖(非默认 quanly_default),尊重其配置;否则按项目名推导
    configured = getattr(settings, "STRATEGY_DOCKER_NETWORK", "")
    if configured and configured != "quanly_default":
        return configured
    return f"{compose_project(client)}_default"
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest backend/apps/strategy/test_launch_fix.py -v`
Expected: PASS（2 项）

- [ ] **Step 5: 加回退分支测试并确认通过**

```python
def test_compose_project_fallback_when_no_label(monkeypatch):
    client = MagicMock()
    client.containers.get.side_effect = Exception("not found")
    monkeypatch.delenv("COMPOSE_PROJECT_NAME", raising=False)
    assert docker_env.compose_project(client) == "quanly"
```

Run: `.venv/bin/python -m pytest backend/apps/strategy/test_launch_fix.py -v`
Expected: PASS（3 项）

---

### Task 2: tasks.py 启动改用动态名 + 异常分类 + 解除阻塞

**Files:**
- Modify: `backend/apps/strategy/tasks.py`
- Test: `backend/apps/strategy/test_launch_fix.py`

**Interfaces:**
- Consumes: `docker_env.scripts_volume_name()`、`docker_env.strategy_network_name()`（Task 1）。
- Produces:
  - `run_strategy_task(run_id)`：起容器后**立即返回**（不再 `container.logs(follow=True)` 阻塞）。
  - `_classify_launch_error(exc) -> str`：把异常映射为分类 key（`image_not_found` / `volume_error` / `network_error` / `unknown`）。

- [ ] **Step 1: 写失败测试 —— 启动用动态卷名/网络名且不阻塞**

```python
def test_run_strategy_task_uses_dynamic_names_and_returns(monkeypatch, db):
    from django.contrib.auth import get_user_model
    from apps.strategy.models import Strategy, StrategyRun
    from apps.strategy import tasks, docker_env

    user = get_user_model().objects.create_user("t1", password="pass12345")
    strat = Strategy.objects.create(user=user, name="s", source="def on_tick(ctx):\n    pass\n")
    run = StrategyRun.objects.create(user=user, strategy=strat, env="sim", symbol="BTC-USDT")

    monkeypatch.setattr(docker_env, "scripts_volume_name", lambda client=None: "proj_strategy_scripts")
    monkeypatch.setattr(docker_env, "strategy_network_name", lambda client=None: "proj_default")

    captured = {}
    fake_container = MagicMock(); fake_container.id = "cid123"

    class FakeClient:
        class containers:
            @staticmethod
            def run(image, **kw):
                captured["image"] = image
                captured["volumes"] = kw.get("volumes")
                captured["network"] = kw.get("network")
                return fake_container
    monkeypatch.setattr("docker.from_env", lambda: FakeClient(), raising=False)
    monkeypatch.setattr(tasks, "_publish_log", lambda *a, **k: None)

    tasks.run_strategy_task(run.id)  # 必须能返回(不阻塞)

    assert "proj_strategy_scripts" in str(captured["volumes"])
    assert captured["network"] == "proj_default"
    run.refresh_from_db()
    assert run.status == StrategyRun.Status.RUNNING
    assert run.container_id == "cid123"
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest backend/apps/strategy/test_launch_fix.py::test_run_strategy_task_uses_dynamic_names_and_returns -v`
Expected: FAIL（当前用写死卷名，且阻塞在 logs follow）

- [ ] **Step 3: 改 tasks.py 的 run_strategy_task**

替换 `backend/apps/strategy/tasks.py` 中 `run_strategy_task` 的容器启动与日志段：

```python
from . import docker_env

def _classify_launch_error(exc) -> str:
    name = exc.__class__.__name__
    msg = str(exc).lower()
    if "imagenotfound" in name.lower() or "no such image" in msg or "pull access" in msg:
        return "image_not_found"
    if "volume" in msg:
        return "volume_error"
    if "network" in msg:
        return "network_error"
    return "unknown"


@shared_task
def run_strategy_task(run_id):
    import docker

    run = StrategyRun.objects.select_related("strategy").get(id=run_id)
    os.makedirs(SCRIPTS_DIR, exist_ok=True)
    script_path = os.path.join(SCRIPTS_DIR, f"run_{run_id}.py")
    with open(script_path, "w") as f:
        f.write(run.strategy.source)

    client = docker.from_env()
    try:
        container = client.containers.run(
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
        )
    except Exception as e:  # noqa
        run.status = StrategyRun.Status.ERROR
        run.save()
        _publish_log(run_id, f"启动容器失败[{_classify_launch_error(e)}]: {e}", "error")
        return

    run.container_id = container.id
    run.status = StrategyRun.Status.RUNNING
    run.save()
    _publish_log(run_id, "策略容器已启动", "info")
    # 不再阻塞 attach 日志:日志由 runner 容器主动经 /api/strategy-api/log 上报(见 Task 3)。
```

同时**删除**原文件里 `run_strategy_task` 末尾 `for line in container.logs(stream=True, follow=True): ...` 及其后的 `finally` 阻塞块。`stop_strategy_task` 保持不变。

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest backend/apps/strategy/test_launch_fix.py::test_run_strategy_task_uses_dynamic_names_and_returns -v`
Expected: PASS

- [ ] **Step 5: 加异常分类测试并确认通过**

```python
def test_launch_error_classified_image_not_found(monkeypatch, db):
    from django.contrib.auth import get_user_model
    from apps.strategy.models import Strategy, StrategyRun
    from apps.strategy import tasks

    user = get_user_model().objects.create_user("t2", password="pass12345")
    strat = Strategy.objects.create(user=user, name="s", source="x")
    run = StrategyRun.objects.create(user=user, strategy=strat, env="sim", symbol="BTC-USDT")

    class ImageNotFound(Exception):
        pass

    class FakeClient:
        class containers:
            @staticmethod
            def run(*a, **k):
                raise ImageNotFound("No such image: quanly-strategy-runner")
    monkeypatch.setattr("docker.from_env", lambda: FakeClient(), raising=False)

    logged = {}
    monkeypatch.setattr(tasks, "_publish_log", lambda rid, msg, lvl="info": logged.update(msg=msg, lvl=lvl))
    tasks.run_strategy_task(run.id)
    run.refresh_from_db()
    assert run.status == StrategyRun.Status.ERROR
    assert "image_not_found" in logged["msg"]
    assert logged["lvl"] == "error"
```

Run: `.venv/bin/python -m pytest backend/apps/strategy/test_launch_fix.py -v`
Expected: PASS（全部）

---

### Task 3: runner.py —— print 也经 ctx.log 上报（保证日志不丢）

**Files:**
- Modify: `strategy-runner/runner.py`
- Test: `backend/apps/strategy/test_launch_fix.py`（对可提取的纯函数做单测）

**Interfaces:**
- Produces: runner `main()` 执行用户脚本时，`print(...)` 输出被捕获并经 `ctx.log()` 上报后端。
- 说明：runner 在独立容器运行，端到端在验收阶段测；此处对"stdout 包装器"逻辑做可导入的纯函数单测。

- [ ] **Step 1: 在 runner.py 提取可测的 stdout 包装器**

在 `strategy-runner/runner.py` 增加（放在 `Ctx` 类之后、`main()` 之前）：

```python
class _LogStream:
    """把写入 stdout 的整行文本转发给 ctx.log,使只 print 的脚本日志也能上报。"""

    def __init__(self, ctx, original):
        self._ctx = ctx
        self._orig = original
        self._buf = ""

    def write(self, s):
        self._orig.write(s)
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line.strip():
                try:
                    self._ctx.log(line)
                except Exception:
                    pass

    def flush(self):
        self._orig.flush()
```

- [ ] **Step 2: 在 main() 里安装包装器**

修改 `main()`：`exec` 用户脚本前，把 `sys.stdout` 替换为 `_LogStream(ctx, sys.stdout)`。注意 `ctx.log` 自身也调用 `print`——为避免递归，`ctx.log` 里改为写 `_LogStream._orig`（即先保存原始 stdout，`ctx.log` 的 `print(message, flush=True)` 用原始流）。

具体：`main()` 开头 `orig_stdout = sys.stdout`；给 `Ctx` 增加类属性 `_out = None`，`ctx._out = orig_stdout`，把 `Ctx.log` 里的 `print(message, flush=True)` 改为 `(self._out or sys.__stdout__).write(str(message) + "\n")`；再 `sys.stdout = _LogStream(ctx, orig_stdout)`。

```python
def main():
    ctx = Ctx()
    orig_stdout = sys.stdout
    ctx._out = orig_stdout
    sys.stdout = _LogStream(ctx, orig_stdout)
    with open(SCRIPT_PATH) as f:
        code = f.read()
    namespace = {"ctx": ctx}
    exec(compile(code, SCRIPT_PATH, "exec"), namespace)
    on_tick = namespace.get("on_tick")
    if callable(on_tick):
        ctx.log("runner: on_tick 模式,每 %ds 轮询" % INTERVAL)
        while True:
            try:
                on_tick(ctx)
            except Exception as e:
                ctx.log("on_tick error: %s" % e)
            time.sleep(INTERVAL)
    else:
        ctx.log("runner: 脚本执行完毕")
```

并把 `Ctx.log` 改为：

```python
    def log(self, message):
        (self._out or sys.__stdout__).write(str(message) + "\n")
        (self._out or sys.__stdout__).flush()
        try:
            requests.post(
                f"{BACKEND_URL}/api/strategy-api/log",
                json={"message": str(message)},
                headers=_HEADERS,
                timeout=5,
            )
        except Exception:
            pass
```

（`Ctx` 增加类属性 `_out = None`。）

- [ ] **Step 3: 写 _LogStream 纯逻辑单测**

`_LogStream` 依赖 requests，无法直接跨目录 import runner。在测试里用最小复刻验证按行转发语义（记录规则），或将 `_LogStream` 逻辑保持简单并以人工核对为准。**本 task 的自动化验证以 Step 4 的语法编译为准，行为在验收阶段端到端验证。**

```python
def test_runner_syntax_compiles():
    import pathlib
    src = pathlib.Path("strategy-runner/runner.py").read_text()
    compile(src, "runner.py", "exec")  # 语法正确即通过
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest backend/apps/strategy/test_launch_fix.py::test_runner_syntax_compiles -v`
Expected: PASS
（注意：pytest 需在仓库根目录运行以便相对路径 `strategy-runner/runner.py` 命中；若在 backend 目录运行，改用绝对路径或 `ROOT` 环境变量。）

---

### Task 4: run_strategy 视图前置校验

**Files:**
- Modify: `backend/apps/strategy/views.py:39-64`
- Test: `backend/apps/strategy/test_launch_fix.py`

**Interfaces:**
- Consumes: 现有 `run_strategy` 视图、`StrategyRun`、`ExchangeCredential`。
- Produces: `run_strategy` 在建 run 前校验 symbol 非空、interval_sec 在合理范围（1..3600），非法返回 400 带 i18n-friendly `detail_key`。

- [ ] **Step 1: 写失败测试 —— 非法 interval 返回 400**

```python
def test_run_strategy_rejects_bad_interval(db):
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient
    from apps.strategy.models import Strategy

    user = get_user_model().objects.create_user("t3", password="pass12345")
    strat = Strategy.objects.create(user=user, name="s", source="x")
    c = APIClient(); c.force_authenticate(user)
    r = c.post(f"/api/strategies/{strat.id}/run", {"symbol": "BTC-USDT", "interval_sec": 0}, format="json")
    assert r.status_code == 400
    assert "detail_key" in r.data
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest backend/apps/strategy/test_launch_fix.py::test_run_strategy_rejects_bad_interval -v`
Expected: FAIL（当前无校验，会走到派发）

- [ ] **Step 3: 在 run_strategy 加前置校验**

在 `views.py` `run_strategy` 建 `StrategyRun` 之前插入：

```python
    symbol = request.data.get("symbol", "BTC-USDT")
    if not symbol or not str(symbol).strip():
        return Response({"detail_key": "strategy.launch.err.symbol_required"}, status=400)
    try:
        interval = int(request.data.get("interval_sec", 5))
    except (TypeError, ValueError):
        return Response({"detail_key": "strategy.launch.err.interval_invalid"}, status=400)
    if not (1 <= interval <= 3600):
        return Response({"detail_key": "strategy.launch.err.interval_invalid"}, status=400)
```

并把后续 `StrategyRun.objects.create(...)` 的 `symbol=` / `interval_sec=` 改用上面校验后的 `symbol` / `interval` 变量。

- [ ] **Step 4: 运行确认通过 + 回归**

Run: `.venv/bin/python -m pytest backend/apps/strategy/ -v`
Expected: PASS（新测试 + 现有 strategy 测试全绿）

---

### Task 5: compose 纳入 runner 镜像构建 + deploy.sh 注释

**Files:**
- Modify: `docker-compose.yml`（services 段末尾新增）
- Modify: `deploy/deploy.sh:14-23,113-114`

**Interfaces:**
- Produces: `compose build` / `compose up --build` 时自动构建 `quanly-strategy-runner` 镜像。

- [ ] **Step 1: docker-compose.yml 新增一次性构建服务**

在 `services:` 段内（`frontend` 之后）新增：

```yaml
  # 策略运行器镜像:纳入 compose 构建,避免漏 build 导致启动策略 404。
  # 构建完即退出(不常驻),不进入任何 depends_on 链路。
  strategy-runner-build:
    build: ./strategy-runner
    image: quanly-strategy-runner
    command: ["true"]
    restart: "no"
```

- [ ] **Step 2: 验证 compose 配置语法**

Run: `docker compose config >/dev/null && echo OK`
Expected: 输出 `OK`（配置合法；若本机 docker 不可用则跳过，人工核对缩进）。

- [ ] **Step 3: deploy.sh 注释说明改由 compose 构建**

把 `deploy/deploy.sh:14-18` 注释与 `hot_update` 内 `build_strategy_runner` 处补一行说明：镜像已由 compose 服务 `strategy-runner-build` 构建，`build_strategy_runner()` 保留为兜底（无 compose 缓存时仍可单独构建）。不删除 `build_strategy_runner`，避免破坏现有一键流程。

- [ ] **Step 4: 检查点**

Run: `grep -n "strategy-runner-build" docker-compose.yml`
Expected: 命中新增服务；deploy.sh 注释已更新。

---

### Task 6: i18n 启动报错 key（zh/en 对齐）

**Files:**
- Modify: `frontend/src/i18n/zh-CN.ts`、`frontend/src/i18n/en-US.ts`

**Interfaces:**
- Consumes: 后端返回的 `detail_key`（Task 4）与容器错误分类（Task 2）。
- Produces: `strategy.launch.err.*` key 两语言对齐。

- [ ] **Step 1: zh-CN 增加 key**

在 `zh-CN.ts` 的 `strategy` 分组内新增：

```ts
    launch: {
      err: {
        symbol_required: '请填写交易标的',
        interval_invalid: '轮询间隔需在 1–3600 秒之间',
        image_not_found: '策略运行镜像缺失，请重新部署构建镜像',
        volume_error: '脚本卷挂载失败，请检查部署',
        network_error: '策略容器网络不可用，请检查部署',
        unknown: '策略启动失败',
      },
    },
```

- [ ] **Step 2: en-US 对齐同结构 key**

```ts
    launch: {
      err: {
        symbol_required: 'Please specify a trading symbol',
        interval_invalid: 'Interval must be between 1 and 3600 seconds',
        image_not_found: 'Strategy runner image missing; redeploy to build it',
        volume_error: 'Script volume mount failed; check deployment',
        network_error: 'Strategy container network unavailable; check deployment',
        unknown: 'Failed to start strategy',
      },
    },
```

- [ ] **Step 3: 校验 key 对齐**

Run: `cd frontend && npx vue-tsc --noEmit 2>/dev/null; echo done`（或人工 diff 两文件 `launch.err` 结构一致）
Expected: 两文件 `strategy.launch.err` 下 key 集合完全一致。

- [ ] **Step 4: 前端 build 通过**

Run: `cd frontend && npm run build`
Expected: 构建成功（如 node_modules 跨机器拷来致 rolldown 原生模块缺失，先删 `node_modules` + `package-lock.json` 重新 `npm install`）。

---

## Self-Review

**Spec coverage：** A spec 四项修复均有 task —— 根因1(卷/网络)→Task1+2；根因2(镜像)→Task5；根因3(解阻塞+日志上报)→Task2+3；附带前置校验/报错→Task4+6。验收标准 1–6 分别由 Task2(动态名)/Task5(镜像)/Task2(不阻塞可并发)/Task3(日志)/Task4+6(明确报错)/Task4 回归覆盖。

**Placeholder scan：** 无 TBD；每个代码步骤含实际代码。Task3 Step3 明确说明 runner 行为以端到端验收为准（已解释原因，非占位）。

**Type consistency：** `compose_project/scripts_volume_name/strategy_network_name`（Task1）→ Task2 调用一致；`_classify_launch_error` 分类 key 与 Task6 i18n key（image_not_found/volume_error/network_error/unknown）一致；`detail_key`（Task4）与 i18n `symbol_required/interval_invalid`（Task6）一致。

## Execution Handoff

计划已保存到 `docs/superpowers/plans/2026-08-12-quanly-A-strategy-launch-fix.md`。
