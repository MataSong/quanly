# 策略商城（第一版）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development 逐任务执行。步骤用 checkbox 追踪。

**Goal:** 策略成为商城生态：内置策略上架 + 用户基于内置模板创建参数化策略实例(不写代码) + 共享(需管理员审核)/私有 + 商城浏览使用 + 我的策略管理 + 管理员审核。全程 PC/手机响应式 + 中英文 + 零 mock。

**Architecture:** Strategy 模型加 owner/template_ref/params/visibility/status/description;用户策略=内置模板+参数(runner 零改动,跑 template_ref 代码);授权无中间表(run guard);审核状态机 draft→pending→approved/rejected。前端三页(商城/我的策略/运行)+ admin 审核 tab。

**Tech Stack:** Django5+DRF(复用 strategy app/RUN_TOKEN/多租户);Vue3+TS+ElementPlus+Pinia+vue-i18n+ResponsiveTable/useBreakpoint。

## Global Constraints

- **不做用户上传任意代码执行**(下一版):用户策略=参数化内置模板实例,runner/tasks 容器注入零改动风险。
- **零 mock**:业绩只用真实数据(StrategyRun 运行数/使用人数、关联真实回测 metrics),无可靠 PnL 不显示收益率,不编造。
- **授权 guard**:run 创建校验 strategy 可用(approved+public / owner=self / 内置 owner=None),否则 403。credential 归属校验(已有)保资金安全。
- **多租户**:mine/update/delete 限 `owner=request.user`;审核限 `strategy:audit` 权限。私有策略 params 不暴露给非 owner。
- **响应式**:useBreakpoint/ResponsiveTable/mixins @include mobile;PC 不退化。
- **i18n**:新文案 t(),zh-CN.ts+en-US.ts 双语对齐(const en:typeof zh)。
- 本地 commit 不 push;精确 git add;每步 pytest(后端)/npm run build(前端)过。
- BASE = 当前 HEAD(60b6e1f)。

## File Structure

**后端**
- `core/strategy/models.py`(改) — Strategy 加字段 + migration。
- `core/strategy/views.py`(改) — marketplace/mine/CRUD/submit/审核视图 + StrategyRunListCreateView.post 加 guard + StrategySerializer 扩展。
- `core/strategy/urls.py`(改) — 新增路由。
- `core/strategy/tasks.py`(改) — CODE_REF 用 template_ref or code_ref。
- `core/strategy/management/commands/seed_builtin_strategies.py`(改) — 内置设 owner=None/status=approved/visibility=public。
- `core/accounts/permissions_registry.py`(改) — strategy 组加 strategy:audit。
- `tests/test_strategy_marketplace.py`(新) — 模型/API/guard/审核/多租户测试。

**前端**
- `frontend/src/views/strategy/Marketplace.vue`(新)、`MyStrategies.vue`(新)。
- `frontend/src/views/strategy/Strategy.vue`(改) — 新建运行策略选择用 marketplace 集合。
- `frontend/src/views/admin/PermissionAdmin.vue`(改) — 加策略审核 tab。
- `frontend/src/api/strategy.ts`(改) — 新增 API + Strategy interface 扩展。
- `frontend/src/router/index.ts`、`frontend/src/layouts/AppShell.vue`(改) — 路由+菜单。
- `frontend/src/locales/{zh-CN,en-US}.ts`(改) — strategy 分组扩展。

---

## Task 1: Strategy 模型扩展 + migration

**Files:** Modify `backend/core/strategy/models.py`;新增 migration。

**Interfaces:**
- Produces: Strategy 新字段 owner(FK User null)/template_ref(CharField)/params(JSONField)/visibility(private|public)/status(draft|pending|approved|rejected)/description(TextField)/reject_reason(TextField)/updated_at。常量 VISIBILITY_*/STATUS_*。

- [ ] **Step 1: 加字段**

```python
# Strategy 类内新增(source/code_ref 等保留):
VISIBILITY_PRIVATE = "private"; VISIBILITY_PUBLIC = "public"
VISIBILITY_CHOICES = [(VISIBILITY_PRIVATE, "Private"), (VISIBILITY_PUBLIC, "Public")]
STATUS_DRAFT = "draft"; STATUS_PENDING = "pending"; STATUS_APPROVED = "approved"; STATUS_REJECTED = "rejected"
STATUS_CHOICES = [(STATUS_DRAFT,"Draft"),(STATUS_PENDING,"Pending"),(STATUS_APPROVED,"Approved"),(STATUS_REJECTED,"Rejected")]

owner = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE, related_name="strategies")
template_ref = models.CharField(max_length=128, blank=True, default="")
params = models.JSONField(default=dict)
visibility = models.CharField(max_length=16, choices=VISIBILITY_CHOICES, default=VISIBILITY_PRIVATE)
status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_DRAFT)
description = models.TextField(blank=True, default="")
reject_reason = models.TextField(blank=True, default="")
updated_at = models.DateTimeField(auto_now=True)
```

- [ ] **Step 2: makemigrations** — `python manage.py makemigrations core_strategy`。检查生成的迁移(owner nullable、默认值合理)。
- [ ] **Step 3: migrate 验证** — 用测试 PG 跑 migrate 通过。
- [ ] **Step 4: Commit** — `git add backend/core/strategy/models.py backend/core/strategy/migrations/`;`feat(marketplace): Strategy 模型加 owner/template_ref/params/visibility/status`。

---

## Task 2: seed 内置策略元数据 + tasks CODE_REF

**Files:** Modify `seed_builtin_strategies.py`、`tasks.py`。

- [ ] **Step 1: seed 内置策略设商城元数据** — get_or_create dual_ma 时(或 update)设 `owner=None, status="approved", visibility="public", is_builtin=True`。已存在的用 update_or_create 补齐新字段。
- [ ] **Step 2: tasks.py CODE_REF 取 template_ref 兜底** — 第66行 `"CODE_REF": run.strategy.code_ref` 改为 `"CODE_REF": run.strategy.template_ref or run.strategy.code_ref`(用户策略跑 template,内置跑自己 code_ref)。PARAMS 保持 `run.params`(run 创建时会填策略 params,见 Task 3)。
- [ ] **Step 3: 验证** — seed 命令跑通(dual_ma status=approved);tasks 单测(mock docker)确认 CODE_REF 取值。
- [ ] **Step 4: Commit** — `feat(marketplace): 内置策略 seed 商城元数据 + tasks CODE_REF 用 template_ref 兜底`。

---

## Task 3: 商城/我的策略/CRUD API + run guard

**Files:** Modify `views.py`、`urls.py`、`permissions_registry.py`。

**Interfaces:**
- Produces: 端点见下;StrategySerializer 扩展;run guard。
- Consumes: Task1 模型字段。

- [ ] **Step 1: permissions_registry 加 strategy:audit** — strategy 组 items 加 `"strategy:audit": {"zh":"审核策略","en":"Audit Strategies"}`。
- [ ] **Step 2: StrategySerializer 扩展** — 加 owner_username(source=owner.username,内置显示"系统"或空)、template_ref、params、visibility、status、description、reject_reason、updated_at。**私有策略非 owner 请求时 params 置空**(在 to_representation 或视图层控制)。
- [ ] **Step 3: 视图**
  - `MarketplaceListView` GET(strategy:view): `filter(Q(status="approved",visibility="public")|Q(owner=request.user)|Q(owner__isnull=True)).distinct()`。
  - `MyStrategiesListView` GET(strategy:view): `filter(owner=request.user)`。
  - `StrategyCreateView` POST(strategy:create): 建参数化实例(name/template_ref/params/description/visibility),owner=self, source_type=uploaded, status=draft;校验 template_ref 在内置模板集合(Strategy.objects.filter(owner__isnull=True).values_list code_ref 或 runner 支持集合)。
  - `StrategyDetailView` GET(strategy:view): get_object_or_404;私有仅 owner;含业绩聚合(见 Task4,先返回结构占位由 Task4 填)。
  - `StrategyUpdateView` PUT(strategy:update): owner=self;改 params/说明重置 status=draft。
  - `StrategyDeleteView` DELETE(strategy:delete): owner=self;有 run 引用(PROTECT)→ 400 提示先停运行(try/except ProtectedError)。
  - `StrategySubmitView` POST(strategy:update): owner=self;visibility=public, status=pending。
  - `AdminPendingView` GET(strategy:audit): filter(status="pending")。
  - `AdminReviewView` POST(strategy:audit): body{action,reason?};approve→status=approved;reject→status=rejected+reject_reason。
- [ ] **Step 4: StrategyRunListCreateView.post 加 guard** — 取 strategy 后:`ok = strategy.owner_id is None or strategy.owner_id == request.user.id or (strategy.visibility=="public" and strategy.status=="approved")`;否则 403。创建 run 时 `params = strategy.params or request.data.get("params", {})`(用户策略用策略参数)。
- [ ] **Step 5: urls** — 加 marketplace/mine/strategies POST/strategies/<pk> GET|PUT|DELETE/strategies/<pk>/submit/admin/pending/admin/strategies/<pk>/review。
- [ ] **Step 6: 测试**(`tests/test_strategy_marketplace.py`,OKX/docker 打桩): marketplace 过滤;create owner/source/status;mine 多租户;update/delete 限 owner;delete 有 run→400;submit→pending;review approve/reject 需 strategy:audit(无→403);**run guard**(他人私有→403,公开审核过/内置/自己→放行);私有 params 不暴露非 owner。
- [ ] **Step 7: pytest 全过 + Commit** — `feat(marketplace): 商城/我的策略/CRUD/审核 API + run 授权 guard + strategy:audit`。

---

## Task 4: 业绩聚合

**Files:** Modify `views.py`(StrategyDetailView 或独立聚合函数)。

- [ ] **Step 1: 聚合函数** — 给 strategy 算:run_count(StrategyRun.filter(strategy=s).count())、user_count(去重 user)、order_count(StrategyOrder 经 run 关联);可选 latest_backtest(Backtest.filter(strategy__code_ref=template_ref or code_ref).order_by("-created_at").first() 的 metrics)。**不编造收益率**;无数据返 0/None。
- [ ] **Step 2: 详情端点返回 performance 字段** — `{run_count,user_count,order_count,reference_backtest?}`。
- [ ] **Step 3: 测试** — 造 run/order 断言聚合数;无数据返 0。
- [ ] **Step 4: Commit** — `feat(marketplace): 策略业绩聚合(运行数/使用人数/关联回测,零mock不造收益率)`。

---

## Task 5: 前端 API + Strategy 类型 + 路由菜单

**Files:** Modify `api/strategy.ts`、`router/index.ts`、`layouts/AppShell.vue`、`locales/{zh-CN,en-US}.ts`。

- [ ] **Step 1: api/strategy.ts** — Strategy interface 扩展(owner_username/template_ref/params/visibility/status/description/reject_reason/updated_at/performance?);新增 `getMarketplace()/getMyStrategies()/getStrategyDetail(id)/createStrategy(payload)/updateStrategy(id,payload)/deleteStrategy(id)/submitStrategy(id)/getAdminPending()/reviewStrategy(id,action,reason?)`。
- [ ] **Step 2: 路由** — 加 /marketplace(Marketplace.vue)、/my-strategies(MyStrategies.vue),meta.perm page:strategy;懒加载。
- [ ] **Step 3: 菜单** — AppShell featureItems 加 marketplace、myStrategies(perm page:strategy),放 strategy 附近。
- [ ] **Step 4: i18n** — strategy 分组加 marketplace/myStrategies/visibility.{private,public}/status.{draft,pending,approved,rejected}/template/params/description/submit/submitConfirm/audit/approve/reject/rejectReason/useStrategy/runCount/userCount/orderCount/referenceBacktest 等,zh/en 对齐。
- [ ] **Step 5: build 过 + Commit** — `feat(marketplace): 前端 API+类型+路由菜单+i18n`。

---

## Task 6: 商城页 Marketplace.vue

**Files:** Create `frontend/src/views/strategy/Marketplace.vue`。

- [ ] **Step 1: 卡片网格** — getMarketplace() 渲染卡片(名称/来源标签[内置/用户公开,按 owner 判断]/参数摘要/使用人数);筛选 tab(全部/内置/用户公开);响应式网格(grid auto-fill minmax,复用 dashboard stat-row 模式)。
- [ ] **Step 2: 详情** — 点卡片→抽屉(el-drawer)或展开:说明/参数/业绩(run_count/user_count/关联回测参考)/"使用此策略"按钮→跳 /strategy 运行页预填 strategy_id(用 query 或 store)。
- [ ] **Step 3: 响应式 + i18n + build 过 + Commit** — `feat(marketplace): 策略商城页(卡片网格+详情+使用)`。

---

## Task 7: 我的策略页 MyStrategies.vue

**Files:** Create `frontend/src/views/strategy/MyStrategies.vue`。

- [ ] **Step 1: 列表** — getMyStrategies() → ResponsiveTable(名称/模板 template_ref/可见性/审核状态[着色 draft灰/pending橙/approved绿/rejected红]/操作)。
- [ ] **Step 2: 新建/编辑对话框** — 选内置模板(el-select,来自 marketplace 里 owner=None 的)+ 参数表单(按模板 default_params 动态,dual_ma 是 fast_period/slow_period/sz)+ name + description + visibility。createStrategy/updateStrategy。
- [ ] **Step 3: 操作** — 编辑/删除(确认,有 run→提示)/提交审核(private→pending,确认框)/看驳回理由(rejected 时显示 reject_reason)。
- [ ] **Step 4: 响应式 + i18n + build 过 + Commit** — `feat(marketplace): 我的策略管理页(创建参数化实例/编辑/删除/提交审核)`。

---

## Task 8: 运行页微调 + admin 审核 tab

**Files:** Modify `frontend/src/views/strategy/Strategy.vue`、`frontend/src/views/admin/PermissionAdmin.vue`。

- [ ] **Step 1: Strategy.vue 新建运行策略选择** — 策略下拉改用 getMarketplace()(可用集合);支持从商城跳来预填 strategy_id(读 route query/store)。
- [ ] **Step 2: admin 审核 tab** — PermissionAdmin.vue el-tabs 加"策略审核"(v-if hasPerm strategy:audit):getAdminPending() 列表(名称/owner/模板/参数/说明)+ 通过/驳回(驳回填理由 reason)按钮 → reviewStrategy。ResponsiveTable。
- [ ] **Step 3: i18n + build 过 + Commit** — `feat(marketplace): 运行页策略选择用商城集合 + admin 策略审核 tab`。

---

## Task 9: Docker 重建 + 端到端验收

- [ ] **Step 1: 重建** — `docker compose up -d --build backend celery-worker nginx`(模型迁移随 backend entrypoint 跑;celery-worker 载入新代码)。
- [ ] **Step 2: 验收**(见 Verification)。

---

## Verification(整体)

1. **后端 pytest** 全过(模型/迁移、marketplace 过滤、create、mine 多租户、update/delete 限 owner+有run 400、submit、审核需 strategy:audit、**run guard**、业绩聚合、私有 params 不暴露)。回归:现有策略运行/回测不破。
2. **前端 build** 过。
3. **端到端**(CRUD/审核无需 OKX;运行需切代理):
   - 我的策略:选 dual_ma 模板+调参+命名→存 private→列表显示 draft。
   - 提交审核→admin 审核 tab 见 pending→通过→商城出现。
   - 商城:浏览→用公开策略新建运行→跑 template 内置代码+策略参数(切代理连 OKX 验证真跑,下单走自己 credential)。
   - 手机:商城卡片/我的策略表/审核 tab 响应式。
   - 中英文切换所有商城文案。
   - 授权:尝试 run 他人私有策略→403。
4. Docker 重建后浏览器验收。

## 执行方式

subagent-driven-development。依赖顺序:T1(模型)→T2(seed/tasks)→T3(API核心)→T4(业绩)→T5(前端基建)→T6/T7/T8(前端页,可较独立)→T9(验收)。后端 T1-T4 是核心,重点 review T3 的 run guard(安全)+ 私有 params 不暴露。BASE=60b6e1f。
