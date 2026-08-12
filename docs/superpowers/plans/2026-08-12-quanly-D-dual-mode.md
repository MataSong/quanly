# 子项目 D — 策略双模式创建(可视化 + 代码编辑器) 实现计划

> **For agentic workers:** 当前会话直接执行(用户约束:严禁 git)。每 task 以测试/前端 build 作检查点。

**Goal:** 新增可视化表单配置(自动生成 Python 源码)与专业代码模式(在线编辑器+校验+预运行),产物统一进模板库、共用容器执行路径。

**Architecture:** 可视化用参数 schema + Python 字符串骨架(`.format`)生成 `on_tick(ctx)` 源码存 `Strategy.source`;代码模式用 CodeMirror 6,validate 走 `compile()`,dryrun 复用回测引擎 `run_backtest`。不引入 Jinja2(零新依赖,不改 runner 镜像/部署)。

**Tech Stack:** Django + DRF;Vue3 + CodeMirror 6。

## Global Constraints

- **严禁 git 操作**;测试作检查点。
- **不新增后端 Python 依赖**(用标准库字符串模板,非 Jinja2)。
- 两模式产物都是普通 `Strategy`(source 符合 on_tick(ctx) 接口),共用现有容器执行路径,不破坏沙箱/OKX/虚实盘/回测。
- 依赖 C:`Strategy.mode/visual_config` 已就绪。
- i18n zh/en 对齐。
- 后端测试:`cd backend && ../.venv/bin/python -m pytest apps/strategy/ -v`;前端:`cd frontend && npm run build`。

---

## File Structure

- `backend/apps/strategy/visual/__init__.py`、`schemas.py`、`generate.py`、`skeletons.py`（新建）
- `backend/apps/strategy/views.py`：`visual_schemas` / `visual_preview` / `code_validate` / `code_dryrun`；`StrategyViewSet.perform_create/update` 支持 mode/visual_config。
- `backend/apps/strategy/urls.py`：4 条新路由。
- `frontend/src/api/strategy.ts`：visual/code 接口。
- `frontend/src/views/StrategyEditor.vue`（新建，双模式）。
- `frontend/src/views/TemplateLibrary.vue`：新建/编辑跳 StrategyEditor。
- `frontend/src/router/index.ts`：`/strategies/editor`、`/strategies/editor/:id`。
- `frontend/package.json`：codemirror + @codemirror/lang-python。
- `frontend/src/i18n/*`：`strategy.editor.* / strategy.visual.*`。
- 测试：`backend/apps/strategy/test_visual.py`（新建）。

---

### Task 1: 可视化 schema + 骨架 + 生成器

**Files:**
- Create: `backend/apps/strategy/visual/__init__.py`、`schemas.py`、`skeletons.py`、`generate.py`
- Test: `backend/apps/strategy/test_visual.py`

**Interfaces:**
- Produces:
  - `SCHEMAS: dict[str, list[dict]]` —— 4 类(ma_cross/grid/dca/tp_sl)的字段 schema，每字段 `{name, type, default, min?, max?, label_key}`。
  - `generate_source(kind: str, config: dict) -> str` —— 校验 config 后用骨架生成完整 `on_tick(ctx)` Python 源码；生成后 `compile()` 自检；kind 非法或缺字段抛 `ValueError`。

- [ ] **Step 1: 写失败测试**

```python
# backend/apps/strategy/test_visual.py
import pytest


def test_generate_ma_cross_compiles():
    from apps.strategy.visual.generate import generate_source
    src = generate_source("ma_cross", {"short": 3, "long": 10, "size": 0.001})
    assert "def on_tick(ctx):" in src
    compile(src, "gen.py", "exec")


def test_generate_all_kinds_compile():
    from apps.strategy.visual.generate import generate_source
    from apps.strategy.visual.schemas import SCHEMAS
    defaults = {
        "ma_cross": {"short": 3, "long": 10, "size": 0.001},
        "grid": {"lower": 100, "upper": 200, "grids": 5, "size": 0.001},
        "dca": {"period": 12, "amount": 10},
        "tp_sl": {"tp_pct": 0.04, "sl_pct": 0.02, "size": 0.001},
    }
    for kind in SCHEMAS:
        src = generate_source(kind, defaults[kind])
        compile(src, f"{kind}.py", "exec")
        assert "on_tick" in src


def test_generate_rejects_unknown_kind():
    from apps.strategy.visual.generate import generate_source
    with pytest.raises(ValueError):
        generate_source("nope", {})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest apps/strategy/test_visual.py -q`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 schemas.py**

```python
"""可视化策略参数 schema:前端据此渲染表单,后端据此校验。"""

SCHEMAS = {
    "ma_cross": [
        {"name": "short", "type": "int", "default": 3, "min": 1, "max": 200, "label_key": "strategy.visual.f.short"},
        {"name": "long", "type": "int", "default": 10, "min": 2, "max": 400, "label_key": "strategy.visual.f.long"},
        {"name": "size", "type": "float", "default": 0.001, "min": 0, "label_key": "strategy.visual.f.size"},
    ],
    "grid": [
        {"name": "lower", "type": "float", "default": 100, "min": 0, "label_key": "strategy.visual.f.lower"},
        {"name": "upper", "type": "float", "default": 200, "min": 0, "label_key": "strategy.visual.f.upper"},
        {"name": "grids", "type": "int", "default": 5, "min": 1, "max": 100, "label_key": "strategy.visual.f.grids"},
        {"name": "size", "type": "float", "default": 0.001, "min": 0, "label_key": "strategy.visual.f.size"},
    ],
    "dca": [
        {"name": "period", "type": "int", "default": 12, "min": 1, "label_key": "strategy.visual.f.period"},
        {"name": "amount", "type": "float", "default": 10, "min": 0, "label_key": "strategy.visual.f.amount"},
    ],
    "tp_sl": [
        {"name": "tp_pct", "type": "float", "default": 0.04, "min": 0, "label_key": "strategy.visual.f.tp"},
        {"name": "sl_pct", "type": "float", "default": 0.02, "min": 0, "label_key": "strategy.visual.f.sl"},
        {"name": "size", "type": "float", "default": 0.001, "min": 0, "label_key": "strategy.visual.f.size"},
    ],
}
```

- [ ] **Step 4: 实现 skeletons.py（Python .format 骨架，双大括号转义）**

```python
"""可视化策略的 Python 源码骨架(str.format 填参)。生成的源码即普通 on_tick(ctx)。"""

MA_CROSS = '''\
# 可视化生成:均线交叉(short={short} long={long})
_p = []
def on_tick(ctx):
    px = ctx.price(ctx.symbol)
    _p.append(px)
    if len(_p) > {long}:
        _p.pop(0)
    if len(_p) < {long}:
        ctx.log("warming up %d/{long}" % len(_p)); return
    short = sum(_p[-{short}:]) / {short}
    long = sum(_p[-{long}:]) / {long}
    ctx.log("px=%.2f s=%.2f l=%.2f" % (px, short, long))
    if short > long:
        ctx.buy(ctx.symbol, {size})
    elif short < long:
        ctx.sell(ctx.symbol, {size})
'''

GRID = '''\
# 可视化生成:网格({lower}-{upper} {grids} 格)
def on_tick(ctx):
    px = ctx.price(ctx.symbol)
    lo, up, n = {lower}, {upper}, {grids}
    step = (up - lo) / n
    if step <= 0:
        ctx.log("invalid grid range"); return
    level = int((px - lo) / step) if px > lo else -1
    ctx.log("px=%.2f level=%d" % (px, level))
    if px < lo:
        ctx.buy(ctx.symbol, {size})
    elif px > up:
        ctx.sell(ctx.symbol, {size})
'''

DCA = '''\
# 可视化生成:定投(每 {period} tick 买入 {amount})
_n = [0]
def on_tick(ctx):
    _n[0] += 1
    if _n[0] % {period} == 0:
        px = ctx.price(ctx.symbol)
        sz = {amount} / px if px > 0 else 0
        ctx.log("DCA buy %.6f @ %.2f" % (sz, px))
        ctx.buy(ctx.symbol, round(sz, 6))
'''

TP_SL = '''\
# 可视化生成:止盈{tp_pct}/止损{sl_pct}
_entry = [None]
def on_tick(ctx):
    px = ctx.price(ctx.symbol)
    if _entry[0] is None:
        _entry[0] = px
        ctx.buy(ctx.symbol, {size})
        ctx.log("entry @ %.2f" % px); return
    pnl = (px - _entry[0]) / _entry[0]
    ctx.log("px=%.2f pnl=%.4f" % (px, pnl))
    if pnl >= {tp_pct}:
        ctx.log("TAKE-PROFIT"); ctx.sell(ctx.symbol, {size}); _entry[0] = None
    elif pnl <= -{sl_pct}:
        ctx.log("STOP-LOSS"); ctx.sell(ctx.symbol, {size}); _entry[0] = None
'''

SKELETONS = {"ma_cross": MA_CROSS, "grid": GRID, "dca": DCA, "tp_sl": TP_SL}
```

- [ ] **Step 5: 实现 generate.py**

```python
from .schemas import SCHEMAS
from .skeletons import SKELETONS


def generate_source(kind: str, config: dict) -> str:
    if kind not in SKELETONS:
        raise ValueError(f"unknown strategy kind: {kind}")
    schema = SCHEMAS[kind]
    params = {}
    for field in schema:
        name = field["name"]
        val = config.get(name, field.get("default"))
        if val is None:
            raise ValueError(f"missing field: {name}")
        if field["type"] == "int":
            val = int(val)
        elif field["type"] == "float":
            val = float(val)
        params[name] = val
    src = SKELETONS[kind].format(**params)
    compile(src, f"visual_{kind}.py", "exec")  # 自检:生成的源码必须语法正确
    return src
```

`visual/__init__.py` 留空。

- [ ] **Step 6: 运行确认通过**

Run: `cd backend && ../.venv/bin/python -m pytest apps/strategy/test_visual.py -q`
Expected: PASS（3 项）

---

### Task 2: 可视化 + 代码 API 端点

**Files:**
- Modify: `backend/apps/strategy/views.py`、`backend/apps/strategy/urls.py`
- Test: `backend/apps/strategy/test_visual.py`

**Interfaces:**
- Produces:
  - `GET /api/strategy/visual/schemas` → `SCHEMAS`。
  - `POST /api/strategy/visual/preview` body `{kind, config}` → `{source}`（不落库；生成失败返回 400 `detail`）。
  - `POST /api/strategy/code/validate` body `{source}` → `{ok: true}` 或 400 `{ok: false, error, lineno}`。
  - `POST /api/strategy/code/dryrun` body `{source, symbol?, bar?, bars?}` → `{logs: [...], error?}`（复用 `run_backtest`，截断 logs 到前 50 条）。

- [ ] **Step 1: 写失败测试**

```python
def test_visual_schemas_endpoint(db):
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient
    user = get_user_model().objects.create_user("d1", password="pass12345")
    c = APIClient(); c.force_authenticate(user)
    r = c.get("/api/strategy/visual/schemas")
    assert r.status_code == 200
    assert "ma_cross" in r.data


def test_visual_preview_endpoint(db):
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient
    user = get_user_model().objects.create_user("d2", password="pass12345")
    c = APIClient(); c.force_authenticate(user)
    r = c.post("/api/strategy/visual/preview",
               {"kind": "ma_cross", "config": {"short": 3, "long": 10, "size": 0.001}}, format="json")
    assert r.status_code == 200
    assert "def on_tick" in r.data["source"]


def test_code_validate_detects_syntax_error(db):
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient
    user = get_user_model().objects.create_user("d3", password="pass12345")
    c = APIClient(); c.force_authenticate(user)
    ok = c.post("/api/strategy/code/validate", {"source": "def on_tick(ctx):\n    pass"}, format="json")
    assert ok.status_code == 200 and ok.data["ok"] is True
    bad = c.post("/api/strategy/code/validate", {"source": "def on_tick(ctx:"}, format="json")
    assert bad.status_code == 400 and bad.data["ok"] is False
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest apps/strategy/test_visual.py -k "endpoint or validate" -q`
Expected: FAIL（404）

- [ ] **Step 3: views.py 加 4 端点**

顶部 import：`from .visual.schemas import SCHEMAS`、`from .visual.generate import generate_source`。加：

```python
@api_view(["GET"])
def visual_schemas(request):
    return Response(SCHEMAS)


@api_view(["POST"])
def visual_preview(request):
    kind = request.data.get("kind")
    config = request.data.get("config") or {}
    try:
        source = generate_source(kind, config)
    except Exception as e:  # noqa
        return Response({"detail": str(e)}, status=400)
    return Response({"source": source})


@api_view(["POST"])
def code_validate(request):
    source = request.data.get("source", "")
    try:
        compile(source, "strategy.py", "exec")
        return Response({"ok": True})
    except SyntaxError as e:
        return Response({"ok": False, "error": str(e), "lineno": e.lineno}, status=400)


@api_view(["POST"])
def code_dryrun(request):
    source = request.data.get("source", "")
    symbol = request.data.get("symbol", "BTC-USDT")
    bar = request.data.get("bar", "1m")
    try:
        bars = int(request.data.get("bars", 120))
    except (TypeError, ValueError):
        bars = 120
    from apps.backtest.engine import run_backtest

    try:
        result = run_backtest(source, symbol=symbol, bar=bar, bars=bars)
        logs = result.get("logs", [])[:50]
        return Response({"logs": logs})
    except Exception as e:  # noqa
        return Response({"logs": [], "error": str(e)}, status=200)
```

`urls.py` 加：

```python
    path("strategy/visual/schemas", views.visual_schemas),
    path("strategy/visual/preview", views.visual_preview),
    path("strategy/code/validate", views.code_validate),
    path("strategy/code/dryrun", views.code_dryrun),
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && ../.venv/bin/python -m pytest apps/strategy/test_visual.py -q`
Expected: PASS（全部）

---

### Task 3: StrategyViewSet 支持保存 mode/visual_config

**Files:**
- Modify: `backend/apps/strategy/views.py`
- Test: `backend/apps/strategy/test_visual.py`

**Interfaces:**
- Produces: 创建/更新 Strategy 时接受 `mode`、`visual_config`；可视化模式保存时后端按 `visual_config` 重新 `generate_source` 覆盖 `source`（确保 source 与 config 一致）。

- [ ] **Step 1: 写失败测试**

```python
def test_create_visual_strategy_regenerates_source(db):
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient
    from apps.strategy.models import Strategy
    user = get_user_model().objects.create_user("d4", password="pass12345")
    c = APIClient(); c.force_authenticate(user)
    r = c.post("/api/strategies/", {
        "name": "vis", "source": "", "mode": "visual",
        "visual_config": {"kind": "ma_cross", "config": {"short": 3, "long": 10, "size": 0.001}},
    }, format="json")
    assert r.status_code == 201
    s = Strategy.objects.get(name="vis", user=user)
    assert s.mode == "visual"
    assert "def on_tick" in s.source
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest apps/strategy/test_visual.py::test_create_visual_strategy_regenerates_source -q`
Expected: FAIL（source 为空，perform_create 未处理 mode/visual_config）

- [ ] **Step 3: 改 StrategyViewSet.perform_create/perform_update**

```python
    def _maybe_generate(self, serializer):
        mode = serializer.validated_data.get("mode", "code")
        vc = serializer.validated_data.get("visual_config")
        if mode == "visual" and vc and vc.get("kind"):
            src = generate_source(vc["kind"], vc.get("config") or {})
            serializer.save(user=self.request.user, kind=Strategy.Kind.UPLOADED, source=src)
        else:
            serializer.save(user=self.request.user, kind=Strategy.Kind.UPLOADED)

    def perform_create(self, serializer):
        self._maybe_generate(serializer)

    def perform_update(self, serializer):
        mode = serializer.validated_data.get("mode", getattr(serializer.instance, "mode", "code"))
        vc = serializer.validated_data.get("visual_config")
        if mode == "visual" and vc and vc.get("kind"):
            src = generate_source(vc["kind"], vc.get("config") or {})
            serializer.save(source=src)
        else:
            serializer.save()
```

（替换现有 `perform_create`。`generate_source` 已在 Task2 顶部 import。）

- [ ] **Step 4: 运行确认通过 + 全量 strategy 回归**

Run: `cd backend && ../.venv/bin/python -m pytest apps/strategy/ -q`
Expected: PASS（strategy 全绿）

---

### Task 4: 前端依赖 + strategy.ts + 路由

**Files:**
- Modify: `frontend/package.json`（或用 npm install 直接装）
- Modify: `frontend/src/api/strategy.ts`、`frontend/src/router/index.ts`、`frontend/src/views/TemplateLibrary.vue`

**Interfaces:**
- Produces: `strategyApi.visualSchemas/visualPreview/codeValidate/codeDryrun/createFull/updateFull`；路由 `/strategies/editor`、`/strategies/editor/:id`；模板库「新建/编辑」跳编辑器。

- [ ] **Step 1: 装 CodeMirror**

Run: `cd frontend && npm install codemirror @codemirror/lang-python @codemirror/state @codemirror/view`
Expected: 安装成功。

- [ ] **Step 2: strategy.ts 加接口**

```typescript
  visualSchemas: () => client.get("/strategy/visual/schemas"),
  visualPreview: (kind: string, config: any) =>
    client.post("/strategy/visual/preview", { kind, config }),
  codeValidate: (source: string) => client.post("/strategy/code/validate", { source }),
  codeDryrun: (source: string, symbol = "BTC-USDT") =>
    client.post("/strategy/code/dryrun", { source, symbol }),
  createFull: (payload: any) => client.post("/strategies/", payload),
  updateFull: (id: number, payload: any) => client.put(`/strategies/${id}/`, payload),
```

- [ ] **Step 3: router 加编辑器路由**

```typescript
        { path: "strategies/editor", component: () => import("@/views/StrategyEditor.vue") },
        { path: "strategies/editor/:id", component: () => import("@/views/StrategyEditor.vue") },
```

- [ ] **Step 4: TemplateLibrary 新建/编辑跳编辑器**

把 `newStrategy()` 改为 `router.push("/strategies/editor")`；`edit(s)` 改为 `router.push(`/strategies/editor/${s.id}`)`；移除内联编辑面板（或保留但主入口走编辑器）。检查点：`grep -n "editor" frontend/src/views/TemplateLibrary.vue`。

---

### Task 5: StrategyEditor.vue 双模式

**Files:**
- Create: `frontend/src/views/StrategyEditor.vue`

**Interfaces:**
- Consumes: `strategyApi.visualSchemas/visualPreview/codeValidate/codeDryrun/get/createFull/updateFull`；CodeMirror 6。

- [ ] **Step 1: 实现 StrategyEditor.vue**

结构：
- 顶部：名称输入 + 模式切换 Tab(可视化/代码)。
- **可视化 Tab**：策略类型下拉(ma_cross/grid/dca/tp_sl)→ 拉 `visualSchemas` 动态渲染表单(int/float 用 number input)→ 输入变化调 `visualPreview` 在只读代码框显示生成源码 →「转为代码模式」把 preview 源码灌入代码 Tab 并切 code。
- **代码 Tab**：CodeMirror 6 编辑器(python 语言) →「校验」调 `codeValidate` 显示结果 →「预运行」调 `codeDryrun` 显示 logs。
- 保存：可视化 `createFull/updateFull({name, source: preview, mode:"visual", visual_config:{kind, config}})`；代码 `{name, source, mode:"code"}`。保存后 `router.push("/strategies/templates")`。
- Glass 样式 + i18n(`strategy.editor.*`/`strategy.visual.*`)。

CodeMirror 挂载用 `onMounted` new EditorView，`:id` 存在时先 `strategyApi.get(id)` 回填。

（完整代码实现时编写。）

- [ ] **Step 2: 检查点**

Run: `test -f frontend/src/views/StrategyEditor.vue && echo OK`
Expected: `OK`

---

### Task 6: i18n + 前端 build

**Files:**
- Modify: `frontend/src/i18n/zh-CN.ts` / `en-US.ts`

**Interfaces:**
- Produces: `strategy.editor.*`、`strategy.visual.*`（含 4 类字段 label `strategy.visual.f.*` 与类型名），zh/en 对齐。

- [ ] **Step 1: zh-CN 加 key**

`strategy` 分组加：

```ts
    editor: { title: "策略编辑器", codeTab: "代码模式", visualTab: "可视化模式", type: "策略类型",
      preview: "生成预览", toCode: "转为代码模式", validate: "校验", dryrun: "预运行", validOk: "语法正确" },
    visual: {
      kinds: { ma_cross: "均线交叉", grid: "网格交易", dca: "定投 DCA", tp_sl: "止盈止损" },
      f: { short: "短周期", long: "长周期", size: "下单量", lower: "下界", upper: "上界",
        grids: "格数", period: "周期(tick)", amount: "每次金额", tp: "止盈比例", sl: "止损比例" },
    },
```

- [ ] **Step 2: en-US 对齐**

```ts
    editor: { title: "Strategy Editor", codeTab: "Code", visualTab: "Visual", type: "Strategy type",
      preview: "Preview", toCode: "Convert to code", validate: "Validate", dryrun: "Dry run", validOk: "Syntax OK" },
    visual: {
      kinds: { ma_cross: "MA Cross", grid: "Grid", dca: "DCA", tp_sl: "Take-profit/Stop-loss" },
      f: { short: "Short period", long: "Long period", size: "Order size", lower: "Lower", upper: "Upper",
        grids: "Grids", period: "Period (ticks)", amount: "Amount each", tp: "Take-profit %", sl: "Stop-loss %" },
    },
```

- [ ] **Step 3: build + key 对齐**

Run: `cd frontend && npm run build`
Expected: 构建成功；`strategy.editor`/`strategy.visual` 两文件 key 集合一致。

---

## Self-Review

**Spec coverage：** D spec D1(schema+骨架+生成)→Task1；D2(visual API+保存)→Task2+3；D3(validate/dryrun)→Task2；D4(前端双模式编辑器)→Task4+5；D5(i18n)→Task6。用 Python 字符串模板替代 Jinja2(spec 提 Jinja2,此为实现选择:零新依赖、不改 runner 镜像——**与 spec 的产物目标一致,仅生成手段不同**)。验收 1-5 由 Task1-5 覆盖。

**Placeholder scan：** Task5 前端组件说明结构，实现时写完整代码。骨架用 `.format`,`{{}}` 无需转义(骨架内无字面大括号)。

**Type consistency：** `generate_source(kind, config)->str`(Task1)→ Task2 preview/Task3 保存一致;`SCHEMAS`(Task1)→ Task2 端点一致;`visualSchemas/visualPreview/codeValidate/codeDryrun`(Task4)→ Task5 组件一致;label_key `strategy.visual.f.*`(Task1 schema)→ Task6 i18n 一致。

## 注意：偏离 spec 的实现决策

spec D 写"用 Jinja2 模板生成"。实现改用 **Python 标准库字符串模板(`str.format`)**,原因:①避免新增后端依赖(否则需同步 requirements + 可能影响部署);②骨架是简单参数替换,不需要 Jinja2 的控制流。**产物完全一致**(生成符合 on_tick(ctx) 的 Python 源码存 Strategy.source)。若你坚持用 Jinja2,告知即可切换(需加依赖)。

## Execution Handoff

计划保存至 `docs/superpowers/plans/2026-08-12-quanly-D-dual-mode.md`,当前会话逐 task 执行。
