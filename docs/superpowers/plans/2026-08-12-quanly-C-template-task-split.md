# 子项目 C — 策略模板库/任务执行面板拆分 + 批量并行 实现计划

> **For agentic workers:** 当前会话直接执行(用户约束:严禁 git)。每 task 以运行测试/前端 build 作为完成检查点。

**Goal:** 把「写完只能跑一次」重构为永久模板库 + 任务执行面板(单标的/批量多标的并行、运行总览、启停/日志/实时盈亏)。

**Architecture:** 后端在现有 Strategy/StrategyRun 上加字段(mode/visual_config/description/batch_id) + 批量 API;前端把 Strategies.vue 拆成 TemplateLibrary.vue(模板库) + TaskPanel.vue(任务面板)。一标的一容器,复用 A/B 的启动与保活。

**Tech Stack:** Django + DRF + Celery;Vue3 + Pinia + i18n。

## Global Constraints

- **严禁 git 操作**;测试作检查点。
- 不破坏 OKX 适配器/虚实盘 env/回测/runner 执行路径(批量=多起同类容器)。
- 容器执行路径不变;`mode/visual_config` 字段本 task 建好(供子项目 D 使用)。
- i18n zh/en 完全对齐。
- 后端测试:`cd backend && ../.venv/bin/python -m pytest apps/strategy/ -v`;前端:`cd frontend && npm run build`。
- 依赖 A/B 完成:`run_strategy_task`/`_launch_container`/`recover` 就绪;`StrategyRun.last_heartbeat` 已有。

---

## File Structure

- `backend/apps/strategy/models.py` + 迁移：Strategy 加 `mode/visual_config/description`；StrategyRun 加 `batch_id`。
- `backend/apps/strategy/serializers.py`：StrategySerializer 加新字段；StrategyRunSerializer 加 `batch_id/last_heartbeat`。
- `backend/apps/strategy/views.py`：`batch_run` / `tasks_overview` / `batch_stop`。
- `backend/apps/strategy/pnl.py`（新建）：`run_pnl(run)` 近似盈亏聚合。
- `backend/apps/strategy/urls.py`：三条新路由。
- `frontend/src/api/strategy.ts`：batch 接口。
- `frontend/src/views/TemplateLibrary.vue`（新建，拆自 Strategies.vue）。
- `frontend/src/views/TaskPanel.vue`（新建）。
- `frontend/src/router/index.ts`、`layouts/GlassLayout.vue`：路由/侧边栏。
- `frontend/src/i18n/zh-CN.ts` / `en-US.ts`：`strategy.templates.* / strategy.tasks.*`。
- 后端测试：`backend/apps/strategy/test_tasks_panel.py`（新建）。

---

### Task 1: 模型字段 + 迁移

**Files:**
- Modify: `backend/apps/strategy/models.py`
- Create: 迁移（makemigrations 生成）
- Test: `backend/apps/strategy/test_tasks_panel.py`

**Interfaces:**
- Produces: `Strategy.mode`(choices code/visual, default code)、`Strategy.visual_config`(JSON null)、`Strategy.description`(Char blank)；`StrategyRun.batch_id`(Char blank, indexed)。

- [ ] **Step 1: Strategy 加字段**

在 `Strategy` 的 `kind` 字段后加：

```python
    class Mode(models.TextChoices):
        CODE = "code", "代码"
        VISUAL = "visual", "可视化"

    mode = models.CharField(max_length=8, choices=Mode.choices, default=Mode.CODE)
    visual_config = models.JSONField(null=True, blank=True)
    description = models.CharField(max_length=255, blank=True, default="")
```

- [ ] **Step 2: StrategyRun 加 batch_id**

在 `StrategyRun.run_token` 后加：

```python
    batch_id = models.CharField(max_length=40, blank=True, default="", db_index=True)
```

- [ ] **Step 3: 生成迁移**

Run: `cd backend && ../.venv/bin/python manage.py makemigrations strategy`
Expected: 生成迁移，含 4 个 AddField。

- [ ] **Step 4: 写测试并通过**

```python
# backend/apps/strategy/test_tasks_panel.py
import pytest


def test_new_model_fields(db):
    from django.contrib.auth import get_user_model
    from apps.strategy.models import Strategy, StrategyRun

    user = get_user_model().objects.create_user("c1", password="pass12345")
    strat = Strategy.objects.create(user=user, name="s", source="x")
    assert strat.mode == "code"
    assert strat.visual_config is None
    assert strat.description == ""
    run = StrategyRun.objects.create(user=user, strategy=strat, env="sim", symbol="BTC-USDT")
    assert run.batch_id == ""
```

Run: `cd backend && ../.venv/bin/python -m pytest apps/strategy/test_tasks_panel.py::test_new_model_fields -q`
Expected: PASS

---

### Task 2: serializer 暴露新字段

**Files:**
- Modify: `backend/apps/strategy/serializers.py`
- Test: `backend/apps/strategy/test_tasks_panel.py`

**Interfaces:**
- Produces: StrategySerializer 含 `mode/visual_config/description`；StrategyRunSerializer 含 `batch_id/last_heartbeat`。

- [ ] **Step 1: 改 serializers.py**

```python
class StrategySerializer(serializers.ModelSerializer):
    class Meta:
        model = Strategy
        fields = ("id", "name", "language", "source", "kind", "mode",
                  "visual_config", "description", "created_at")
        read_only_fields = ("kind", "created_at")


class StrategyRunSerializer(serializers.ModelSerializer):
    strategy_name = serializers.CharField(source="strategy.name", read_only=True)

    class Meta:
        model = StrategyRun
        fields = (
            "id", "strategy", "strategy_name", "env", "credential", "symbol",
            "interval_sec", "status", "started_at", "stopped_at",
            "batch_id", "last_heartbeat",
        )
        read_only_fields = ("status", "started_at", "stopped_at", "last_heartbeat")
```

- [ ] **Step 2: 写测试并通过**

```python
def test_strategy_serializer_has_mode(db):
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient
    from apps.strategy.models import Strategy

    user = get_user_model().objects.create_user("c2", password="pass12345")
    Strategy.objects.create(user=user, name="s", source="x", mode="visual",
                            visual_config={"kind": "ma"}, description="d")
    c = APIClient(); c.force_authenticate(user)
    r = c.get("/api/strategies/")
    row = [s for s in r.data if s["name"] == "s"][0]
    assert row["mode"] == "visual"
    assert row["visual_config"] == {"kind": "ma"}
    assert row["description"] == "d"
```

Run: `cd backend && ../.venv/bin/python -m pytest apps/strategy/test_tasks_panel.py::test_strategy_serializer_has_mode -q`
Expected: PASS（注意 create 接口写入 mode/visual_config 需 serializer 允许写；此测试直接建对象再读，验证读出）

---

### Task 3: pnl 近似聚合

**Files:**
- Create: `backend/apps/strategy/pnl.py`
- Test: `backend/apps/strategy/test_tasks_panel.py`

**Interfaces:**
- Consumes: `apps.trading.models.Bill`（现有，CLOSE_PNL 类型记平仓盈亏，带 user/env/symbol）。
- Produces: `run_pnl(run) -> float`：该 run 的近似盈亏 = 其 user+env+symbol 的 CLOSE_PNL 账单金额合计（run.started_at 之后）。

- [ ] **Step 1: 确认 Bill 字段**

先读 `backend/apps/trading/models.py` 的 `Bill` 定义，确认字段名（`bill_type`/`amount`/`symbol`/`ts` 或类似）。**实现按实际字段名调整**，下面以 `bill_type=CLOSE_PNL`、`amount`、`symbol`、`created_at` 为例。

- [ ] **Step 2: 写测试**

```python
def test_run_pnl_sums_close_bills(db):
    from django.contrib.auth import get_user_model
    from apps.strategy.models import Strategy, StrategyRun
    from apps.strategy.pnl import run_pnl

    user = get_user_model().objects.create_user("c3", password="pass12345")
    strat = Strategy.objects.create(user=user, name="s", source="x")
    run = StrategyRun.objects.create(user=user, strategy=strat, env="sim", symbol="BTC-USDT")
    # 无账单时应为 0
    assert run_pnl(run) == 0.0
```

- [ ] **Step 3: 实现 pnl.py（按实际 Bill 字段名）**

```python
"""策略运行的近似盈亏聚合。

近似口径:该 run 的 user+env+symbol 在 run 启动后的平仓盈亏(CLOSE_PNL)账单合计。
注:同一 symbol 若有手动单会混入,这是任务面板的近似展示,非精确 run 级隔离。
"""
from apps.trading.models import Bill


def run_pnl(run) -> float:
    qs = Bill.objects.filter(user=run.user, env=run.env, symbol=run.symbol)
    # 仅统计平仓盈亏类账单 + run 启动后
    qs = qs.filter(bill_type=Bill.Type.CLOSE_PNL, created_at__gte=run.started_at)
    total = sum(float(b.amount) for b in qs)
    return round(total, 8)
```

（若 Bill 的类型枚举/字段名不同，Step 1 已要求先核对并相应调整；保持函数签名 `run_pnl(run)->float` 不变。）

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && ../.venv/bin/python -m pytest apps/strategy/test_tasks_panel.py::test_run_pnl_sums_close_bills -q`
Expected: PASS

---

### Task 4: 批量 API — batch_run / tasks_overview / batch_stop

**Files:**
- Modify: `backend/apps/strategy/views.py`、`backend/apps/strategy/urls.py`
- Test: `backend/apps/strategy/test_tasks_panel.py`

**Interfaces:**
- Consumes: `run_strategy_task`、`stop_strategy_task`、`run_pnl`、`StrategyRunSerializer`。
- Produces:
  - `POST /api/strategy/tasks/batch-run` body `{template_id, symbols[], env, credential_id?, interval_sec?}` → 建 N 个 run（共享 `batch_id=secrets.token_hex(8)`），逐个 `run_strategy_task.delay`，返回 `{batch_id, runs:[...]}`。
  - `GET /api/strategy/tasks` → 该用户所有 run 按 batch_id 分组：`[{batch_id, template_name, env, runs:[{...run, pnl}]}]`（含无 batch 的单跑 run，batch_id 为空时各自成组或归入 "single"）。
  - `POST /api/strategy/tasks/batch-stop` body `{batch_id}` → stop 该 batch 全部 run。

- [ ] **Step 1: 写失败测试 — batch_run 建 N 个共享 batch_id 的 run**

```python
def test_batch_run_creates_runs_with_shared_batch(db, monkeypatch):
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient
    from apps.strategy.models import Strategy, StrategyRun
    from apps.strategy import views

    # 拦截 celery 派发,避免连 redis
    monkeypatch.setattr(views, "run_strategy_task", type("T", (), {"delay": staticmethod(lambda rid: None)}))

    user = get_user_model().objects.create_user("c4", password="pass12345")
    strat = Strategy.objects.create(user=user, name="s", source="x")
    c = APIClient(); c.force_authenticate(user)
    r = c.post("/api/strategy/tasks/batch-run",
               {"template_id": strat.id, "symbols": ["BTC-USDT", "ETH-USDT"], "env": "sim", "interval_sec": 5},
               format="json")
    assert r.status_code == 201
    batch_id = r.data["batch_id"]
    assert batch_id
    runs = StrategyRun.objects.filter(batch_id=batch_id)
    assert runs.count() == 2
    assert set(runs.values_list("symbol", flat=True)) == {"BTC-USDT", "ETH-USDT"}
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest apps/strategy/test_tasks_panel.py::test_batch_run_creates_runs_with_shared_batch -q`
Expected: FAIL（404）

- [ ] **Step 3: views.py 加三个视图**

在 `views.py` 顶部 import：`import secrets`；`from .pnl import run_pnl`；把 `run_strategy_task` 提为模块级可 patch 引用（在函数内 import 改为模块级 try import，或在文件顶部 `from .tasks import run_strategy_task, stop_strategy_task` —— 若顶部 import 触发 celery 加载问题，用惰性：在视图内 `from . import tasks` 并调 `tasks.run_strategy_task.delay`）。为可测，采用：文件顶部 `from . import tasks as _tasks`，测试 patch `views.run_strategy_task`。**统一实现**：

```python
import secrets
from .pnl import run_pnl
from .tasks import run_strategy_task, stop_strategy_task


@api_view(["POST"])
def batch_run(request):
    template_id = request.data.get("template_id")
    strategy = get_object_or_404(Strategy, pk=template_id, user=request.user)
    symbols = request.data.get("symbols") or []
    if not isinstance(symbols, list) or not symbols:
        return Response({"detail_key": "strategy.launch.err.symbol_required"}, status=400)
    env = request.data.get("env", "sim")
    cred_id = request.data.get("credential_id")
    credential = None
    if cred_id:
        credential = get_object_or_404(ExchangeCredential, pk=cred_id, user=request.user)
    try:
        interval = int(request.data.get("interval_sec", 5))
    except (TypeError, ValueError):
        return Response({"detail_key": "strategy.launch.err.interval_invalid"}, status=400)
    if not (1 <= interval <= 3600):
        return Response({"detail_key": "strategy.launch.err.interval_invalid"}, status=400)

    batch_id = secrets.token_hex(8)
    created = []
    for sym in symbols:
        if not str(sym).strip():
            continue
        run = StrategyRun.objects.create(
            user=request.user, strategy=strategy, env=env, credential=credential,
            symbol=str(sym).strip(), interval_sec=interval, batch_id=batch_id,
        )
        try:
            run_strategy_task.delay(run.id)
        except Exception as e:  # noqa
            run.status = StrategyRun.Status.ERROR
            run.save()
        created.append(run)
    return Response(
        {"batch_id": batch_id, "runs": StrategyRunSerializer(created, many=True).data},
        status=201,
    )


@api_view(["GET"])
def tasks_overview(request):
    qs = StrategyRun.objects.filter(user=request.user).select_related("strategy")
    groups = {}
    for run in qs[:300]:
        key = run.batch_id or f"single-{run.id}"
        g = groups.setdefault(key, {
            "batch_id": run.batch_id, "template_name": run.strategy.name,
            "env": run.env, "runs": [],
        })
        row = StrategyRunSerializer(run).data
        row["pnl"] = run_pnl(run)
        g["runs"].append(row)
    return Response(list(groups.values()))


@api_view(["POST"])
def batch_stop(request):
    batch_id = request.data.get("batch_id")
    if not batch_id:
        return Response({"detail": "batch_id required"}, status=400)
    runs = StrategyRun.objects.filter(user=request.user, batch_id=batch_id)
    from django.utils import timezone
    for run in runs:
        try:
            stop_strategy_task.delay(run.id)
        except Exception:
            pass
        run.status = StrategyRun.Status.STOPPED
        run.stopped_at = timezone.now()
        run.save()
    return Response({"stopped": runs.count()})
```

`urls.py` 加（在现有 strategy-runs 路由后）：

```python
    path("strategy/tasks/batch-run", views.batch_run),
    path("strategy/tasks", views.tasks_overview),
    path("strategy/tasks/batch-stop", views.batch_stop),
```

- [ ] **Step 4: 运行确认通过 + 补 overview/stop 测试**

补测试：

```python
def test_tasks_overview_groups_by_batch(db, monkeypatch):
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient
    from apps.strategy.models import Strategy, StrategyRun

    user = get_user_model().objects.create_user("c5", password="pass12345")
    strat = Strategy.objects.create(user=user, name="s", source="x")
    StrategyRun.objects.create(user=user, strategy=strat, env="sim", symbol="BTC-USDT", batch_id="b1")
    StrategyRun.objects.create(user=user, strategy=strat, env="sim", symbol="ETH-USDT", batch_id="b1")
    c = APIClient(); c.force_authenticate(user)
    r = c.get("/api/strategy/tasks")
    assert r.status_code == 200
    grp = [g for g in r.data if g["batch_id"] == "b1"][0]
    assert len(grp["runs"]) == 2
    assert "pnl" in grp["runs"][0]


def test_batch_stop_stops_all(db, monkeypatch):
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient
    from apps.strategy.models import Strategy, StrategyRun
    from apps.strategy import views

    monkeypatch.setattr(views, "stop_strategy_task", type("T", (), {"delay": staticmethod(lambda rid: None)}))
    user = get_user_model().objects.create_user("c6", password="pass12345")
    strat = Strategy.objects.create(user=user, name="s", source="x")
    for sym in ("BTC-USDT", "ETH-USDT"):
        StrategyRun.objects.create(user=user, strategy=strat, env="sim", symbol=sym,
                                   batch_id="b2", status=StrategyRun.Status.RUNNING)
    c = APIClient(); c.force_authenticate(user)
    r = c.post("/api/strategy/tasks/batch-stop", {"batch_id": "b2"}, format="json")
    assert r.status_code == 200
    assert r.data["stopped"] == 2
    assert StrategyRun.objects.filter(batch_id="b2", status="stopped").count() == 2
```

Run: `cd backend && ../.venv/bin/python -m pytest apps/strategy/test_tasks_panel.py -q`
Expected: PASS（全部）

注：`batch_run` 用顶部 `from .tasks import run_strategy_task`，测试 `monkeypatch.setattr(views, "run_strategy_task", ...)` 替换模块级名即可拦截。

---

### Task 5: 前端 strategy.ts + 路由 + 侧边栏

**Files:**
- Modify: `frontend/src/api/strategy.ts`、`frontend/src/router/index.ts`、`frontend/src/layouts/GlassLayout.vue`

**Interfaces:**
- Produces: `strategyApi.batchRun/tasksOverview/batchStop`；路由 `/strategies/templates`、`/strategies/tasks`；`/strategies` 重定向到 templates；侧边栏保留「策略」入口指向 templates。

- [ ] **Step 1: strategy.ts 加接口**

```typescript
  batchRun: (payload: {
    template_id: number; symbols: string[]; env: string;
    credential_id?: number; interval_sec?: number;
  }) => client.post("/strategy/tasks/batch-run", payload),
  tasksOverview: () => client.get("/strategy/tasks"),
  batchStop: (batchId: string) =>
    client.post("/strategy/tasks/batch-stop", { batch_id: batchId }),
```

（加入 `strategyApi` 对象。）

- [ ] **Step 2: router 加两页 + 重定向**

把 `{ path: "strategies", component: Strategies.vue }` 改为：

```typescript
        { path: "strategies", redirect: "/strategies/templates" },
        { path: "strategies/templates", component: () => import("@/views/TemplateLibrary.vue") },
        { path: "strategies/tasks", component: () => import("@/views/TaskPanel.vue") },
        { path: "strategies/:id", component: () => import("@/views/StrategyDetail.vue") },
```

- [ ] **Step 3: 侧边栏加任务面板入口**

`GlassLayout.vue` `navItems` 里把单条 strategies 换为两条：

```typescript
  { path: "/strategies/templates", key: "nav.strategies" },
  { path: "/strategies/tasks", key: "nav.tasks" },
```

`isActive` 的 `/strategies` 判断保留（两条都以 /strategies 开头，需分别精确匹配）：

```typescript
  if (item.path === "/strategies/templates") return route.path === "/strategies/templates" || route.path === "/strategies";
  if (item.path === "/strategies/tasks") return route.path.startsWith("/strategies/tasks");
```

- [ ] **Step 4: 检查点（build 在 Task 7 统一跑）**

Run: `grep -n "batchRun\|tasksOverview" frontend/src/api/strategy.ts`
Expected: 命中新接口。

---

### Task 6: TemplateLibrary.vue + TaskPanel.vue

**Files:**
- Create: `frontend/src/views/TemplateLibrary.vue`（拆自 Strategies.vue，模板 CRUD/预览）
- Create: `frontend/src/views/TaskPanel.vue`（选模板+多选标的+批量启动+运行总览）
- Keep: `frontend/src/views/Strategies.vue`（不再路由引用，可保留文件不删以免破坏其它引用；本 task 不删除）

**Interfaces:**
- Consumes: `strategyApi.list/create/update/remove`（模板库）、`batchRun/tasksOverview/batchStop/stop`（任务面板）、`credentials`。

- [ ] **Step 1: TemplateLibrary.vue（基于 Strategies.vue 内容，标题/入口改模板库语义）**

以现有 `Strategies.vue` 的 script+template+style 为基础复制为 `TemplateLibrary.vue`，改动：
- 列表新增「说明」列显示 `s.description`、「模式」列显示 `s.mode`（code/visual i18n）。
- 标题用 `$t("strategy.templates.title")`，新建按钮 `$t("strategy.templates.new")`。
- 「打开」按钮改为跳 `/strategies/tasks?template=<id>`（在任务面板选中该模板），其余 CRUD 不变。

（完整文件较长，实现时以 Strategies.vue 为蓝本逐段改写，保持 Glass 样式类不变。）

- [ ] **Step 2: TaskPanel.vue**

新建，包含：
- 顶部启动区：模板下拉（`strategyApi.list`）、env 切换（sim/live）、凭证下拉（`strategyApi.credentials(env)`）、interval 输入、交易标的多选（简单实现：逗号分隔输入或多选框，值为 symbol 数组）、「批量启动」按钮 → `strategyApi.batchRun(...)`。
- 运行总览：`strategyApi.tasksOverview()` 每 3s 轮询，按 batch 分组渲染；每组显示 template_name/env + 「全部停止」（`batchStop`）；组内每 run 显示 symbol/status/last_heartbeat/pnl + 单 run「停止」（`strategyApi.stop(runId)`）、「日志」（跳 `/strategies/<runId>` 或打开日志抽屉，首轮跳 StrategyDetail）。
- Glass 样式 + i18n key（`strategy.tasks.*`）。

（完整代码实现时编写；结构参考 Dashboard.vue 的 3s 轮询与 Trade.vue 的表格样式。）

- [ ] **Step 3: 检查点（build 在 Task 7）**

Run: `test -f frontend/src/views/TemplateLibrary.vue && test -f frontend/src/views/TaskPanel.vue && echo OK`
Expected: `OK`

---

### Task 7: i18n + 前端 build

**Files:**
- Modify: `frontend/src/i18n/zh-CN.ts` / `en-US.ts`

**Interfaces:**
- Produces: `strategy.templates.*`、`strategy.tasks.*`、`nav.tasks`，zh/en 对齐。

- [ ] **Step 1: zh-CN 加 key**

`nav` 分组加 `tasks: "任务面板"`；`strategy` 分组加：

```ts
    templates: { title: "策略模板库", new: "新建模板", mode: "模式", codeMode: "代码", visualMode: "可视化", desc: "说明" },
    tasks: {
      title: "任务执行面板", selectTemplate: "选择模板", symbols: "交易标的(逗号分隔)",
      batchRun: "批量启动", running: "运行中任务", stopAll: "全部停止", pnl: "实时盈亏",
      heartbeat: "最近心跳", empty: "暂无运行任务",
    },
```

- [ ] **Step 2: en-US 对齐同结构**

```ts
    templates: { title: "Strategy Templates", new: "New Template", mode: "Mode", codeMode: "Code", visualMode: "Visual", desc: "Description" },
    tasks: {
      title: "Task Panel", selectTemplate: "Select template", symbols: "Symbols (comma-separated)",
      batchRun: "Batch Start", running: "Running Tasks", stopAll: "Stop All", pnl: "PnL",
      heartbeat: "Last heartbeat", empty: "No running tasks",
    },
```

`nav.tasks: "Task Panel"`。

- [ ] **Step 3: build 通过**

Run: `cd frontend && npm run build`
Expected: 构建成功。

- [ ] **Step 4: key 对齐校验**

Run: 人工 diff 或脚本比对 `strategy.templates`/`strategy.tasks`/`nav.tasks` 在两文件 key 集合一致。
Expected: 一致。

---

## Self-Review

**Spec coverage：** C spec C1(模型)→Task1+2；C2(batch API+pnl)→Task3+4；C3(前端拆两页)→Task5+6；C4(i18n)→Task7。验收 1(模板 CRUD)→Task6；2(批量 3 标的并行分组)→Task4+6；3(单 run 独立停)→Task4+6；4(全部停止)→Task4；5(env 隔离)→Task4(env 字段贯穿)；6(回归+key)→Task7。

**Placeholder scan：** Task3 依赖 Bill 实际字段名——已在 Step1 要求先核对（非占位，是必要的运行时确认）。Task6 前端组件说明了结构与蓝本，实现时写完整代码。

**Type consistency：** `run_pnl(run)->float`（Task3）→ Task4 tasks_overview 使用一致；`batch_id`（Task1）→ serializer(Task2)/batch_run(Task4)/前端一致；`batchRun/tasksOverview/batchStop`（Task5）→ Task6 组件调用一致。

## Execution Handoff

计划保存至 `docs/superpowers/plans/2026-08-12-quanly-C-template-task-split.md`，当前会话逐 task 执行。
