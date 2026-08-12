# 子项目 C — 策略模板库 / 任务执行面板拆分 + 批量并行

日期：2026-08-12
父设计：`2026-08-12-quanly-strategy-page-overhaul-overview.md`
优先级：中（依赖 A/B 使策略能稳定启动、保活）
状态：待复审

## 目标

把「写完脚本只能临时跑一次」重构为：**永久模板库**（可反复调用） +
**任务执行面板**（单标的 / 批量多标的并行、运行中任务总览、启停/日志/实时盈亏）。

## 现状（基于当前代码）

- `Strategy`（source/kind） + `StrategyRun`（env/credential/symbol/interval/status/container_id）
  + `StrategyLog` 已是「模板/实例」雏形，一份 Strategy 已可跑多个 Run。
- 前端 `Strategies.vue` 把「列表 + 新建/编辑（textarea 写 Python）」混在一页；
  `StrategyDetail.vue` 单 run 启停 + WS 日志。**无批量、无任务总览、无按批分组**。
- API：`StrategyViewSet` CRUD、`run_strategy`(单 run)、`list_runs`、`run_logs`、`stop_strategy`。

## 设计

### C1：模型演进（在现有表上加字段，不推倒；配合 D 一并落地）
- `Strategy` 增：
  - `mode = CharField(choices=[code, visual], default=code)`（配合子项目 D）
  - `visual_config = JSONField(null=True, blank=True)`（可视化配置，D 用）
  - `description = CharField(blank=True, default="")`（模板说明）
- `StrategyRun` 增：
  - `batch_id = CharField(max_length=40, blank=True, default="", db_index=True)`
    （同一次批量启动的多个 run 共享，便于分组展示 / 统一启停）
- 迁移：一个 migration 覆盖以上字段。

### C2：任务执行 API
- `POST /api/strategy/tasks/batch-run`：body `{template_id, symbols[], env, credential_id, interval_sec}`
  → 生成 `batch_id`（`secrets.token_hex`）→ 对每个 symbol 建一个 StrategyRun（共享 batch_id）
  → 逐个 `run_strategy_task.delay`（A 修后 worker 不阻塞，可并发起 N 容器）
  → 返回 batch_id + run 列表。
- `GET /api/strategy/tasks`：运行中任务总览，按 batch 分组返回
  `{batch_id, template_name, env, runs:[{id, symbol, status, last_heartbeat, pnl}]}`。
  - `pnl`：复用 trading 的 Bill/Position 按 user+env+symbol 聚合该 run 的实时盈亏
    （近似：run 期间该 symbol 的平仓盈亏 + 持仓浮盈）。
- `POST /api/strategy/tasks/batch-stop`：body `{batch_id}` → stop 该 batch 全部 run。
- 单 run 启停/日志：复用现有 `run_strategy` / `stop_strategy` / `run_logs`（保留）。

### C3：前端拆两页（替换现 Strategies.vue 的混合模式）
- **策略模板库** `/strategies/templates`（TemplateLibrary.vue）
  - 模板列表（名称/mode/说明/创建时间），新建/编辑/删除、代码预览、参数预设入口。
  - builtin 不可删（沿用现规则）。
  - 新建/编辑跳子项目 D 的双模式编辑器。
- **任务执行面板** `/strategies/tasks`（TaskPanel.vue）
  - 顶部：选模板 → 多选交易标的（复用 `/market/symbols`）→ env/凭证/interval → 「批量启动」。
  - 主体：运行中任务总览表，**按 batch 分组**，每行 symbol/状态/心跳/实时盈亏 +
    单 run 启停、查看日志（复用现终端式 WS 日志组件）；批次级「全部停止」。
  - 每 3s 轮询 `/api/strategy/tasks` 刷新状态与盈亏（沿用 Dashboard 轮询风格）。
- 路由：`/strategies` 重定向到 `/strategies/templates`；侧边栏「策略」下二级入口
  「模板库」「任务面板」。原 `/strategies/:id` 详情并入任务面板的日志抽屉或保留。

### C4：i18n
- 新增 key 分组 `strategy.templates.* / strategy.tasks.*`（批量启动、按批分组、心跳、
  实时盈亏、全部停止等），zh-CN / en-US 完全对齐。

## 涉及文件
- `backend/apps/strategy/models.py` + 迁移（C1）
- `backend/apps/strategy/views.py`（C2 batch-run / tasks / batch-stop）
- `backend/apps/strategy/serializers.py`（batch 分组 / pnl 序列化）
- `backend/apps/strategy/urls.py`（C2 路由）
- `backend/apps/strategy/tasks.py`（复用；批量并发起容器）
- `frontend/src/views/TemplateLibrary.vue`（C3 新增，拆自 Strategies.vue）
- `frontend/src/views/TaskPanel.vue`（C3 新增）
- `frontend/src/api/strategy.ts`（batch 接口）
- `frontend/src/router/index.ts` + `GlassLayout.vue`（C3 路由/侧边栏）
- `frontend/src/i18n/zh-CN.ts` / `en-US.ts`（C4）

## 不改动（保护边界）
- 容器执行路径（runner / runner_api / on_tick 接口）不变——批量只是多起几个同类容器。
- OKX 适配器、虚实盘 env、回测引擎不动。

## 验收标准（网页可测）
1. 模板库新建/编辑/删除/预览一份策略；builtin 不可删。
2. 任务面板选一模板 + 勾选 3 个标的 + 批量启动 → 3 个独立容器并行 RUNNING、
   按同一 batch 分组展示。
3. 各 run 日志独立、实时盈亏分别显示；单 run 停止不影响同批其他 run。
4. 「全部停止」一次性停掉整个 batch。
5. env 隔离正确（sim/live 数据不串）。
6. 后端 pytest 全绿；zh/en key 对齐校验通过。

## 测试
- 单测：batch-run 生成 N 个 run 且共享 batch_id；tasks 分组结构；batch-stop 停全批；
  pnl 聚合正确性（构造 Bill/Position 断言）。
- TDD：先写失败测试再实现。
