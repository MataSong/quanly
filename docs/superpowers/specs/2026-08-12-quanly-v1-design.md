# Quanly 量化交易平台 — 第一版设计方案（喂给 Claude 的开工提示词）

> 本文档是 quanly 项目从零开始第一版的完整设计与实现指令。你（Claude）拿到这份文档后，应据此规划并实现代码。文档同时是「产品需求 + 技术方案 + 实现约束」。凡标注 **【硬约束】** 的条目不可自行更改；标注 **【第一版范围】** 的是本次要做的，超出范围的写占位入口即可。

---

## 0. 一句话定位

Quanly 是一个**面向中文 OKX 用户的 SaaS 量化交易平台**：用户注册后绑定自己的 OKX API key，选择或上传交易策略，先在历史数据上回测，再一键部署到 OKX 官方虚拟盘或实盘运行，并实时监控持仓、盈亏、日志。

对标竞品：SaaS 化、中文、专注 OKX、门槛更低的 Freqtrade（Freqtrade 缺多租户和模板体验；3Commas 缺自定义代码和透明度；QuantConnect 太重且不专注 crypto）。差异化 = 中文 + 专注 OKX + 既有模板又能传代码 + 策略 Docker 隔离的 SaaS。

---

## 1. 第一版纵深主线（方案 A：极简纵深切片）

**【硬约束】第一版必须把这一条主线端到端打穿，其余功能写占位：**

```
注册/登录 → 绑定 OKX API key（加密存储）
   → 从「1 个内置策略」选一个，配置参数
   → 回测（历史数据出净值曲线 + 核心指标）
   → 一键部署到 OKX（虚拟盘 或 实盘，用户选环境）
   → 策略在隔离 Docker 容器中运行，实时下单到 OKX
   → 实时监控：持仓 / 挂单 / 盈亏 / 运行日志
```

**为什么是这条线**：最快到达「策略真的把单下到 OKX 了」这个能证明产品成立的决定性时刻，风险最低，每一层都能独立测试。

**第一版明确不做（写占位入口即可）：**
- 策略模板商店（第一版只有 1 个内置策略；模板列表页可留「敬请期待」占位）
- 用户上传自定义 Python 代码（上传入口做成占位，但策略加载器架构必须预留这个扩展点）
- 多交易所（只有 OKX）
- 计费 / 订阅
- 除 OKX 现货外的复杂品类（第一版建议先做现货，永续可作为紧接着的下一层）

---

## 2. 核心架构决策 —— 【硬约束】

### 2.1 交易所接入
- **只接 OKX**，用 OKX 官方 Python SDK `python-okx`，**严禁手写 HTTP 请求**。
- **虚拟盘 + 实盘都对接 OKX 官方接口**，靠 SDK 的 `flag` 参数区分：`flag='1'` = 虚拟盘（demo trading），`flag='0'` = 实盘。加上不同的 API key。
- 数据库用 `env` 字段（`sim` / `live`）彻底隔离两条数据链路（订单、持仓、余额、策略运行都带 env）。
- **本机能连上 OKX**，第一版在本机即可真实端到端验收虚拟盘和实盘。
- mock 行情源 / mock 撮合引擎作为**可选降级开关**保留（环境变量 `MARKET_FEED=okx|mock`、`EXCHANGE_MODE=okx|mock`），断网或无 key 时可跑通全链路，但默认走真实 OKX。

### 2.2 策略隔离
- 所有策略（内置 + 未来用户上传）**一律当自定义脚本对待**，统一走**独立 Docker 容器隔离**运行。
- 落地方式 **Docker-out-of-Docker**：异步 worker 挂载宿主机 `docker.sock`，为每个策略运行动态 `docker run` 一个隔离容器（内存/CPU 限额 + `cap-drop` + `read-only`）。
- **安全【硬约束】**：策略容器内**只注入一个一次性 RUN_TOKEN**，绝不注入用户的 API key / secret / passphrase。容器通过 RUN_TOKEN 回调后端的「策略专用 API」间接下单，密钥只存在于后端。
- 策略加载器要抽象出统一接口（如 `on_tick(ctx)`），`ctx` 注入 `price / candles / buy / sell / log` 等能力。内置策略和未来的用户上传代码走同一套接口 —— 这就是「混合定位」的扩展点。

### 2.3 混合定位的架构预留
- 策略来源抽象成两类：`builtin`（内置模板，第一版只做 1 个）和 `uploaded`（用户上传，第一版占位）。数据模型和加载器要能区分并支持这两类，第一版只实现 builtin 的完整链路。

---

## 3. 技术栈 —— 全面对标 ops_hub（`/Users/C5386931/Project/ops_hub`）

> **【硬约束】前端风格、国际化、用户管理/RBAC 必须 1:1 复刻 ops_hub 的技术选型与代码风格**，让两个项目看起来像同一个团队做的。实现前请先阅读 ops_hub 对应文件作为范本（下面每项都给了路径）。

### 3.1 前端
- **Vue 3 + TypeScript + Vite 5 + Element Plus 2.7 + Pinia + Vue Router 4 + vue-i18n 9 + axios**
- Composition API + `<script setup lang="ts">`
- 布局：复刻 `ops_hub/frontend/src/layouts/AppShell.vue` —— CSS Grid，**深色顶栏（56px）+ 白色可折叠侧边栏（240px，折叠状态存 localStorage）+ 内容区独立滚动**。侧边栏菜单项按权限点过滤显示。
- 主题：复刻 `ops_hub/frontend/src/styles/tokens.scss` 的 Stripe 风格紫青配色（`--brand-primary:#635bff` 紫 / `--brand-dark:#0a2540` 深色底 / accent `#00d4ff` 青）。**无暗色模式**（和 ops_hub 一致）。
- 公共组件仿照 ops_hub：`DataTable / DetailDrawer / PageHeader / StatusPill / EmptyState / LocaleSwitcher / BrandLogo` 等。
- HTTP 封装仿 `ops_hub/frontend/src/api/http.ts`（axios 实例 + JWT 拦截器 + 刷新）。

### 3.2 国际化（i18n）—— 【硬约束】全局中英文
- 库 **vue-i18n 9，`legacy: false`**，复刻 `ops_hub/frontend/src/locales/index.ts` 的初始化。
- 语言资源用 **`.ts` 文件（不是 JSON）**：`zh-CN.ts` / `en-US.ts`，`export default { ... }` 嵌套对象。
- **两侧语言键必须完全对齐**（vue-tsc 类型检查会因单边键报错）。凡是用户可见文案一律走 i18n key，禁止硬编码中文。
- 切换：复刻 `ops_hub/frontend/src/stores/locale.ts`（Pinia store，持久化 localStorage、联动 Element Plus 自带语言包、设 `document.documentElement.lang`）+ `LocaleSwitcher.vue` 组件。

### 3.3 后端
- **Django 5 + DRF + SimpleJWT**（access 30min / refresh 7d，`ROTATE_REFRESH_TOKENS=True` + `BLACKLIST_AFTER_ROTATION=True`）。
- 认证接口复刻 `ops_hub/backend/core/auth/`（Login `/api/auth/` / Logout 加黑名单 / Me），登录响应内联用户有效权限。
- 分层约定复刻 ops_hub：每个 app 有 `apps.py / services.py / views.py / urls.py / serializers.py / models.py`，业务逻辑放 services，view 用 DRF APIView/ViewSet。
- OKX API key 等敏感凭证用 **Fernet 对称加密**存储，复刻 `ops_hub/backend/core/credentials/`（密钥走环境变量）。
- 审计装饰器 `@audit` + AuditLog 复刻 `ops_hub/backend/core/audit/`。

### 3.4 用户管理 / RBAC —— 【硬约束】颗粒度对标 ops_hub
> 复刻 `ops_hub/backend/core/accounts/` 整套。**第一版有多少功能板块，就为多少板块做权限点**，但代码写抽象、留好扩展。

- **权限点注册表**（`permissions_registry.py`）：权限点随代码硬编码（`page:*` 页面可见性 + 各模块 `view/create/update/delete`），管理员只能分配不能新造，`ALL_PERMISSION_CODES` 汇总。
- **模型**：`Role`（name + permissions JSONField + is_system）、`UserRole`（M2M）、`UserPermissionOverride`（effect grant/deny，`unique(user, permission)`）、`UserProfile`（`auth_source` local/sso 预留 SSO）。
- **有效权限合成**（`services.py`）：superuser 全放通；否则「角色权限并集 → grant 加 → deny 减 → 与合法码取交集」，带请求级缓存。
- **后端双闸门**（`drf.py`）：声明式 `view.required_permissions`（可按 HTTP method 区分）+ `HasRequiredPermissions`；命令式 `require_perm(request, "trading:place")`。
- **用户/角色管理 API**（`/api/accounts/`，IsSuperUser）：RoleViewSet、UserViewSet（action：roles/set_active/reset_password/overrides/delete_override，删除保护 + `@audit`）、PermissionsListView。
- **前端权限控制**：路由 `meta.perm` + `router/guards.ts`（beforeEach 查 perm，无权限跳第一个有权限的页，未登录跳 `/login`）+ `stores/auth.ts` 的 `hasPerm()`。管理页复刻 `src/views/admin/`（PermissionAdmin / RolePanel / UserPanel）。
- **多租户数据隔离**：每个用户只能看到自己的 API key / 策略 / 订单 / 持仓（所有业务模型带 user 外键，查询按 request.user 过滤）。
- **异步任务 = Celery**【硬约束】：broker 用 Redis。用于回测任务、策略容器编排（启动/停止）、行情采集等重任务。建议分队列（如 `backtest` / `strategy` 队列），worker 挂 `docker.sock` 做策略容器隔离。
- **实时推送 = Django Channels**【硬约束】：channel layer 用 Redis。WebSocket 用于向前端实时推送行情 K 线/tick、持仓/盈亏变动、策略运行日志。ASGI 部署（daphne/uvicorn），nginx `/ws` 反代。

**第一版的功能板块（每个板块都要有对应权限点，`page:*` + CRUD 粒度）：**
1. 仪表盘 / 资产看板（`page:dashboard`）
2. OKX 密钥管理（`page:credentials` + `credentials:view/create/update/delete`）
3. 行情（`page:market` + `market:view`）
4. 策略（`page:strategy` + `strategy:view/create/update/delete/run`）
5. 回测（`page:backtest` + `backtest:view/create`）
6. 交易/订单监控（`page:trading` + `trading:view/place/cancel`）
7. 权限管理（`page:admin`，超管专属）

### 3.5 数据库 —— 【硬约束】
- **统一用 PostgreSQL**（不照搬 ops_hub 的 SQLite）。
- 若行情时序数据量大，可后续引入时序库；第一版 K 线/tick 可先落 PG 或走内存/Redis，不强求时序库。

### 3.6 部署 —— 【硬约束】全 Docker 化
- **整个项目全部容器化 + docker-compose 编排**（ops_hub 无 Docker，quanly 在这点上更进一步）。
- 至少包含服务：`postgres`、`redis`（缓存 / Celery broker / Channels channel layer / WS pub-sub）、`backend`（Django + gunicorn/uvicorn，跑 DRF API）、`ws`（ASGI daphne/uvicorn，跑 Channels WebSocket）、`celery-worker`（Celery 异步任务，挂 `docker.sock` 用于策略容器隔离）、`celery-beat`（可选，定时任务如行情采集）、`frontend`（Vite build 产物由 nginx 或 Django 托管）、`nginx`（反向代理，含 WebSocket `/ws` 反代）。
- 提供一键 `docker compose up --build` 起全家桶 + 一键部署脚本。
- 策略运行镜像 `quanly-strategy-runner` 单独构建，worker 动态 `docker run` 它。

---

## 4. 后端 App 划分（建议）

复刻 ops_hub 的 `core/` + 业务 app 分层：

```
backend/
  config/                # Django 配置(settings/base|dev|prod, urls 含 SPA catch-all)
  core/
    auth/                # JWT 登录登出 Me
    accounts/            # RBAC(权限点注册表/Role/Override/双闸门/用户角色管理)
    credentials/         # OKX API key Fernet 加密存储(带 env: sim/live)
    audit/               # @audit + AuditLog
  apps/
    market/              # 行情(OKX 现货 K 线/tick,WS 推送前端)
    trading/             # 订单/持仓/余额/成交(带 env + user),OKX 下单封装
    strategy/            # 策略模型(builtin/uploaded)/运行/日志 + 容器编排 + 策略专用API(RUN_TOKEN鉴权)
    backtest/            # 回测引擎(复用策略 on_tick 接口)+ 指标计算 + 结果存储
    assets/              # 资产看板聚合(净值/持仓分布/账单流水)
  strategy-runner/       # 策略运行容器(Dockerfile + runner.py,注入 ctx SDK)
```

---

## 5. 关键数据流

1. **下单链路**：策略容器 `ctx.buy()` → 带 RUN_TOKEN 回调后端策略专用 API → 后端用该策略绑定的 credential + env 初始化 OKX SDK（flag 由 env 决定）→ 调 OKX Trade API 下单 → 落库（Order 带 env/user/credential）→ WS 推前端。
2. **行情链路**：market collector 从 OKX 拉 K 线/tick → 存 Redis/PG + publish 到 Redis 频道 → Channels/WS consumer 推前端图表；策略容器通过 `ctx.candles()` 走策略专用 API 取历史/最新价。
3. **回测链路**：回测引擎用历史 K 线逐 bar 喂给策略的 `on_tick(ctx)`，模拟成交扣手续费 → 算指标（总收益/年化/最大回撤/夏普/索提诺/卡玛/胜率/盈亏比等）→ 出净值曲线。回测与实盘复用同一套策略接口，只换数据源和成交方式。

---

## 6. 图表
- 前端金融图表用 **TradingView Lightweight Charts**（开源，K 线用 CandlestickSeries，净值曲线用 LineSeries）。注意 v5 API 是 `chart.addSeries(CandlestickSeries, ...)`。

---

## 7. 验收边界与已知约束

- **【验收】** 第一版验收标准 = 在本机用真实 OKX 虚拟盘：注册登录 → 绑定虚拟盘 key → 选内置策略 → 回测出曲线 → 部署到虚拟盘 → 观察策略在隔离容器中真实下单到 OKX 虚拟盘 → 前端实时看到持仓/盈亏/日志。之后切实盘 key（flag='0'）走同样流程验收实盘。
- **【安全验收】** 检查策略容器内环境变量只有 RUN_TOKEN，没有任何 API key/secret/passphrase。
- **【已知约束】** 若部署到境外受限网络的机器连不上 OKX，用 `MARKET_FEED=mock` / `EXCHANGE_MODE=mock` 降级跑通全链路，代码不用动，联网后切回。

---

## 8. 环境安装注意（本机踩过的坑）
- 装 Python 依赖时 PyPI 官方 CDN 可能挂起，用清华镜像；若 venv 里没有 pip，用 `uv`。
- 前端 `node_modules` 跨机器拷贝不可用，换机器要重新 `npm ci`。

---

## 9. 交付方式（重要）
- **【硬约束】本项目不做任何 git 操作**：不 `git add` / `commit` / `push`。所有产出写到磁盘即可。
- 建议 Claude 拿到本文档后：先输出一份「骨架优先 + 纵深主线」的分阶段实现计划（P0 骨架 → 主线逐层做深，每层网页可测），每完成一层做一次端到端验证，再进下一层。

---

## 附：与竞品的定位对照（背景参考）

| 产品 | 形态 | 面向用户 | 策略方式 | OKX | quanly 借鉴 |
|---|---|---|---|---|---|
| Freqtrade | 开源自部署 | 会写 Python | 写代码 | ✓ | Docker 化、dry-run（虚拟盘）机制、监控 UI |
| 3Commas | SaaS 订阅 | 不写代码 | 现成模板 | ✓ | 填参数就能跑的模板体验、订阅收费 |
| VN.PY | 开源本地框架 | 专业量化 | 写代码 | 弱 | 事件驱动引擎核心架构 |
| QuantConnect | 云端 SaaS | 研究者/机构 | 写 Python | ✓ | 研究→回测→实盘闭环、AI 生成策略 |

quanly 的空位：**中文 + 专注 OKX + SaaS 多用户 + 既有模板又能传代码 + 策略 Docker 隔离**，市场上无一个产品同时覆盖。
