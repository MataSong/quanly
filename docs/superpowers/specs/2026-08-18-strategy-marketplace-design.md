# 策略商城（第一版：参数化内置模板实例）设计文档

**日期**: 2026-08-18
**范围**: 策略商城生态第一版 —— 内置策略上架 + 用户基于内置模板创建参数化策略实例 + 共享(需审核)/私有 + 商城浏览使用 + 我的策略管理 + 管理员审核。全程 PC/手机响应式 + 中英文 i18n + 零 mock。
**明确不做(下一版独立 spec)**: 用户上传任意 Python 代码执行(代码沙箱、AST 审查、出站网络限制)、付费/订阅授权、真实盘 PnL 收益率。

## 背景与目标

quanly 要做成开放量化平台。当前策略是全局无归属的内置策略,策略页曾展示全部策略(已改为只显示"我的运行")。用户希望:策略成为一个商城生态——有内置策略,用户能创建自己的策略并选择共享(公开)或私有,公开的经审核后上架商城供所有用户浏览使用。

**第一版关键取舍(已与用户确认)**:
- 用户"自己写策略" = **参数化内置模板实例**(选内置模板如双均线 + 调参数 + 命名 + 说明),**不写任意代码**。彻底避开代码执行沙箱风险(留下一版)。
- 因此 runner 完全不用改:用户策略运行时跑的仍是内置模板代码(template_ref),只是参数不同。
- 共享到商城**需管理员审核**才上架。
- 业绩展示只用可靠真实数据(运行数/使用人数/关联回测),**不编造收益率**(零 mock)。

## 架构决策

1. **参数化实例模型**:用户策略 = `owner=self` + `source_type=uploaded` + `template_ref`(指向内置模板 code_ref) + `params`(用户调的参数)。执行时 runner 收 `CODE_REF=template_ref` + `PARAMS=params`,跑内置代码。**runner/tasks.py 的容器注入零改动**(CODE_REF 已通过 env 传,只是值来源变)。
2. **授权无中间表**:`owner`(可空,内置=None) + `visibility`(public/private) + `status`(审核态)。run 创建时 guard 表达式鉴权:`status=approved & visibility=public` 或 `owner=self` 或内置(owner=None)。credential 归属校验(已有)保证资金安全。中间表(付费/订阅)留将来。
3. **审核状态机**:draft → pending(提交审核) → approved(上架) / rejected。内置策略直接 approved+public+owner=None。
4. **业绩诚实**:StrategyRun 聚合运行数/使用人数;可选关联该 template 的真实回测 metrics 作参考业绩。无可靠 PnL 不显示收益率。

## 数据模型(`backend/core/strategy/models.py`)

`Strategy` 现有字段: name / source_type(builtin|uploaded, 枚举已存在) / code_ref / default_params / is_builtin / created_at。

**新增字段**:
- `owner = ForeignKey(User, null=True, blank=True, on_delete=CASCADE, related_name="strategies")` — 内置=None。
- `template_ref = CharField(128, blank=True, default="")` — 用户策略指向的内置模板 code_ref(内置策略自身此字段可空)。
- `params = JSONField(default=dict)` — 用户调的参数(内置策略用 default_params)。
- `visibility = CharField(16, choices=[("private","private"),("public","public")], default="private")`。
- `status = CharField(16, choices=[("draft","draft"),("pending","pending"),("approved","approved"),("rejected","rejected")], default="draft")`。
- `description = TextField(blank=True, default="")`。
- `reject_reason = TextField(blank=True, default="")` — 驳回理由。
- `updated_at = DateTimeField(auto_now=True)`。
- migration。`seed_builtin_strategies` 更新:内置策略播种时设 `owner=None, status="approved", visibility="public"`。

**StrategyRun 引用不变**(strategy FK PROTECT)。run 记录天然是使用记录(user+strategy)。

## 后端 API(`backend/core/strategy/views.py` + `urls.py` + serializers inline)

**权限点**(`permissions_registry.py` strategy 组): 复用 `strategy:view/create/update/delete/run`(create/update/delete 已定义未接线),**新增 `strategy:audit`**(管理员审核,双语)。

**新增/改造视图**:
- `GET /api/strategy/marketplace`(strategy:view): `Strategy.objects.filter(Q(status="approved", visibility="public") | Q(owner=request.user) | Q(owner__isnull=True))`。商城可用集合。
- `GET /api/strategy/mine`(strategy:view): `filter(owner=request.user)`。
- `POST /api/strategy/strategies`(strategy:create): 创建参数化实例(template_ref/params/name/description/visibility),`owner=request.user, source_type="uploaded", status="draft"`。校验 template_ref 是有效内置模板。
- `GET /api/strategy/strategies/<id>`(strategy:view): 详情 + 业绩聚合(见下)。私有策略仅 owner 可见。
- `PUT /api/strategy/strategies/<id>`(strategy:update): `get_object_or_404(owner=request.user)`;改回参数/说明会重置 status→draft(若之前 approved,重编辑需重新提交)。
- `DELETE /api/strategy/strategies/<id>`(strategy:delete): `owner=request.user`;有 run 引用时(PROTECT)返回 400 提示先停运行 / 或软删(加 is_deleted)。**采用**: 拒绝删除并提示(最简,PROTECT 天然保护)。
- `POST /api/strategy/strategies/<id>/submit`(strategy:update): owner 提交审核,visibility→public, status→pending。
- `GET /api/strategy/admin/pending`(strategy:audit): status=pending 列表。
- `POST /api/strategy/admin/strategies/<id>/review`(strategy:audit): body {action: approve|reject, reason?} → status=approved / rejected(+reject_reason)。

**改造现有**:
- `StrategyListView`(现返回 all): 改为返回 marketplace 可用集合(供新建运行选策略),或前端直接用 /marketplace。**采用**: 保留 StrategyListView 但改 queryset 为可运行集合(approved+public | owner=self | 内置)。
- `StrategyRunListCreateView.post`: **新增 strategy 授权 guard**(现在零校验): 取 strategy 后校验 `strategy.owner_id in (None, request.user.id) or (strategy.visibility=="public" and strategy.status=="approved")`,否则 403。run 时容器注入 `CODE_REF = strategy.template_ref or strategy.code_ref`(用户策略用 template_ref,内置用 code_ref),`PARAMS = strategy.params or run.params`。**核对 tasks.py 注入逻辑**,确保 code_ref 取值正确(可能需在创建 run 时把 template_ref 存进 run,或 tasks 里解析)。

**业绩聚合**(详情端点): 按 strategy 聚合 StrategyRun(运行数、去重 user 数=使用人数);可选关联 template 的最近回测 metrics(Backtest.objects.filter(strategy__code_ref=template_ref).latest)。**不返回编造的收益率**。

**serializers**: StrategySerializer 扩展字段(owner_username/template_ref/params/visibility/status/description/updated_at);**私有策略的 params 对非 owner 不暴露**(商城公开策略可展示参数,私有仅 owner)。

## 前端(全部响应式 + i18n)

**菜单**(AppShell featureItems): 策略区平铺(或分组)。新增 `marketplace`(商城)、`myStrategies`(我的策略);保留 `strategy`(运行,原策略页)。权限 page:strategy(或新增 page:marketplace,**采用复用 page:strategy** 避免新页面权限点膨胀——三页都 page:strategy)。

- `frontend/src/views/strategy/Marketplace.vue`(新): 策略卡片网格(名称/来源标签[内置/用户公开]/参数摘要/使用人数);筛选 全部/内置/用户公开;点卡片→详情(抽屉或页,显示说明/参数/业绩指标/关联回测参考)+"使用此策略"→跳运行页预填。响应式卡片网格。
- `frontend/src/views/strategy/MyStrategies.vue`(新): 我的策略 ResponsiveTable(名称/模板/可见性/审核状态[draft/pending/approved/rejected 着色]/操作[编辑/删除/提交审核/看驳回理由]);"新建策略"对话框(选内置模板 el-select + 参数表单[按模板 default_params 动态生成,dual_ma 是 fast/slow/sz] + 命名 + 说明 + 可见性)。
- `frontend/src/views/strategy/Strategy.vue`(改): "我的运行"表格保留;新建运行的策略选择改用 /marketplace 可用集合(含自己的 + 内置 + 公开审核过的)。
- `frontend/src/views/admin/PermissionAdmin.vue`(改): el-tabs 加"策略审核" tab(需 strategy:audit): pending 列表 + 通过/驳回(驳回填理由)。
- `frontend/src/api/strategy.ts`(改): 新增 marketplace/mine/createStrategy/updateStrategy/deleteStrategy/submitStrategy/adminPending/reviewStrategy;Strategy interface 扩展字段。
- 路由: 新增 /marketplace、/my-strategies(meta.perm page:strategy)。
- i18n: strategy 分组大量新增(marketplace/myStrategies/visibility/status.*/template/submit/audit/review 等)zh/en 对齐。

## 错误处理

- 无权运行他人私有策略 → 403(guard)。
- 删有 run 引用的策略 → 400 提示先停运行(PROTECT)。
- 编辑已 approved 策略 → 重置 draft 需重新提交(提示用户)。
- 审核端点无 strategy:audit → 403。
- 业绩无数据 → 显示"暂无运行数据",不造假。
- template_ref 无效 → 创建 400。

## 验证

1. **后端 pytest**: 模型迁移;marketplace 过滤(公开审核+自己+内置);创建参数化实例(owner=self/source uploaded/status draft);mine 多租户;update/delete 限 owner;submit→pending;审核 approve/reject 需 strategy:audit;**run 授权 guard**(用他人私有→403,用公开审核过/内置/自己的→放行);业绩聚合;私有 params 不暴露给非 owner。OKX 打桩。
2. **前端 build**: vue-tsc + vite。
3. **端到端(需真连 OKX 切代理跑运行,但商城/我的策略/审核纯 CRUD 无需 OKX)**: 
   - 创建参数化策略(选 dual_ma 模板+调参+命名)→ 存 private → 我的策略列表显示。
   - 提交审核 → 管理员审核 tab 看到 pending → 通过 → 商城出现该策略。
   - 商城浏览 → 用他人公开策略新建运行 → 运行跑的是 template 内置代码 + 该策略参数(需切代理连 OKX 验证真跑)。
   - 手机: 商城卡片/我的策略表/审核 tab 响应式。
   - 中英文切换所有商城文案。
4. **回归**: 现有策略运行/回测/资产不破;策略运行页新建运行仍能选策略。
5. Docker 重建后验收。

## 后续(下一版独立 spec)

- 用户上传任意 Python 代码策略: DB code 字段 + 容器 exec-from-env + AST 审查(禁 os/subprocess/socket/eval) + 出站网络限制(仅 backend) + pids_limit + 执行超时。runner load_on_tick 支持 uploaded 代码。
- 付费/订阅授权中间表(StrategyGrant)、按次计费、可撤销授权。
- 真实盘 PnL 收益率(需成交回报数据源)。
