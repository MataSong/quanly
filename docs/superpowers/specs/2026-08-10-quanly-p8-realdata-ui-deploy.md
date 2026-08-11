# P8：全面去 Mock 化、UI 统一与部署一键化 设计

日期：2026-08-10
状态：已批准（待实现）

## 背景

项目已本地部署并接入 OKX 正式接口。早期以 mock 数据开发，现要求彻底去 mock、全链路使用真实 OKX 数据，同时修复若干 UI 与体验问题，并把部署做成小白可用的一键化流程。

本 spec 是在既有系统上的修复与改造，不新建项目。技术栈保持不变：

- 前端：Vue 3 + TypeScript + glass.css 玻璃拟态
- 后端：Django + DRF + Channels(WS) + Celery + Redis + PostgreSQL + InfluxDB
- 交易所层：`OKXAdapter` 已封装 OKX REST/WS，区分实盘(flag=0)/虚拟盘(flag=1)

## 核心决策（已与用户确认）

1. **彻底去 mock 化**：删除所有 mock 数据与 mock 代码路径，OKX 成为唯一数据真相源，本地库仅作缓存与展示。
2. **数据同步方式**：实时 + 定时自动同步。新增 OKX 私有 WebSocket 推送作为主链路，REST 定时/进入页面时做全量校正。
3. **同步范围**：账户余额、持仓、历史订单/成交、账单流水。
4. **成交/持仓/强平/止盈止损事件**：以 OKX 私有 WS 推送为准，删除本地 MockEngine 的推算逻辑。
5. **行情选择器**：搜索下拉框（玻璃风）。
6. **UI 组件**：自研 Glass 组件族，不引入第三方 UI 库。
7. **C2C**：删除该功能（OKX 无公开 C2C 接口）。
8. **理财**：产品列表与申购/赎回全部接真实 OKX 理财接口。
9. **回测**：接真实历史 K 线。
10. **部署**：一键初始化 + 一键热更新 + 证书自动化 + 自动备份/恢复。

## 关键风险与约束

- **去 mock 后无假数据兜底**：OKX 连接中断时，行情与撮合会失效。块 A 需实现 WebSocket 自动重连与前端降级提示，但不再以假数据顶替。
- **MockEngine 承担真实职责**：现有本地 `check_risk`/`match_pending` 负责强平价、止盈止损、限价撮合的推算。删除后必须由 OKX 私有 WS 的真实事件替代，否则功能塌方。
- **C2C 不可去 mock**：OKX 官方 SDK/公开 API 不提供 C2C 广告/商户接口，故直接删除功能而非对接。

## 工作分块

六个低耦合块，可独立实现与验证。

---

### 块 A：去 Mock 化 + OKX 数据同步（后端，核心）

#### A1. 删除纯 mock 代码
- 删除 `backend/apps/market/mockfeed.py`
- 删除 `backend/apps/trading/engine.py` 中的 `MockEngine` 类（约 45-264 行）
- 删除 `run_collector` 的 `_run_mock()` 路径，`_run_okx()` 成为唯一路径
- 删除 `MARKET_FEED` / `EXCHANGE_MODE` 开关（settings.py），所有分支固定为 OKX
- 删除 `prices.py` 的 mockfeed 兜底：改为 Redis 缓存 + 上次缓存价，读不到则报错，不返回假数据
- 删除 `MOCK_INITIAL_USDT` 常量及其依赖

#### A2. 新增 OKX 私有 WebSocket 采集器（关键）
- 新增常驻进程（管理命令 + compose 服务），连接 `wss://ws.okx.com:8443/ws/v5/private`（虚拟盘用对应 demo 域名），以用户凭证登录
- 订阅频道：`account`（余额）、`positions`（持仓）、`orders`（订单成交/状态变更）
- 收到推送：写入本地 `Balance` / `Position` / `Order` / `Trade` 表 → 经 Redis 推送前端 `/ws/trade/{user_id}/{env}`
- 强平、止盈止损、成交以 OKX 推送为准；删除本地 `check_risk` / `match_pending` 推算逻辑
- 实现自动重连（指数退避）与连接状态上报；断线期间前端显示降级提示

#### A3. 资产 / 账单同步
- `assets/service.summarize()` 改为读取同步后的真实余额/持仓
- 进入页面/启动时做 REST 全量拉取：`get_balances`、`get_positions`、历史订单、账单流水；之后由 A2 的 WS 增量更新
- 定时任务（Celery beat，如每 10-30 秒）做 REST 校正兜底，纠正 WS 可能遗漏的增量
- `reconcile.py` 重写为对比 OKX REST 实拉余额，移除 `MOCK_INITIAL_USDT` 依赖

#### A4. OKXEngine 简化
- `OKXEngine` 不再继承 `MockEngine`；下单/撤单/平仓直调 `OKXAdapter`
- 成交结果不再本地结算，由 A2 的 WS 推送回填订单状态、持仓、余额
- `get_engine()` 直接返回 `OKXEngine`

**验证**：虚拟盘登录后，资产总览应显示 OKX 真实虚拟盘余额；下单后成交/持仓变化经 WS 实时反映。

---

### 块 B：行情交易对搜索下拉选择器（前端）

- 新建 `frontend/src/components/SymbolSelect.vue`：玻璃风下拉框，点开后顶部搜索输入实时筛选，下方列表展示匹配交易对，点选后关闭
- 替换 `Market.vue` 现有的一排平铺按钮（`.tabs` + `v-for`）
- 交易对全部从 `/market/symbols`（真实 OKX instruments）动态加载
- 复用到 Trade / StrategyDetail / Backtest 中选交易对处

**验证**：行情页交易对以可搜索下拉框呈现，输入关键词能实时筛选。

---

### 块 C：自研 Glass 表单组件族（前端）

新建与 glass.css 风格统一的组件，替换所有原生控件。全部支持深浅主题。

| 组件 | 替换目标 | 出现处 |
|---|---|---|
| `GlassSelect` | 原生 `<select>` | Trade / Transfer / Finance / StrategyDetail / Backtest / Keys，共 11 处 |
| `GlassNumber` | `<input type="number">` 及原生上下箭头 | Trade / Transfer / StrategyDetail / Backtest，共 8 处 |
| `GlassSlider` | `<input type="range">`（杠杆） | Trade，1 处 |
| `GlassCheckbox` | 原生 `<input type="checkbox">` | StrategyDetail / Backtest，共 2 处 |

- `GlassNumber` 自带样式化加减按钮，替代浏览器原生 spinner
- `GlassSelect` 统一下拉动画与玻璃背景

**验证**：全项目无裸露原生控件，深浅主题下均与玻璃风格一致。

---

### 块 D：遗留补全

- **回测接真实历史 K 线**：`backtest/engine.py` 从 `mockfeed.history_candles` 改为优先读 InfluxDB 已采集数据，不足则 OKX REST 补齐
- **删除 C2C**：删除 `finance/views.c2c()` 及路由；删除前端 C2C 页面、路由、入口
- **理财全接真实**：产品列表、申购、赎回全走 OKX 理财接口，移除本地 SEED 与本地记账
- **去硬编码交易对**：清除全项目 SYMBOLS 常量，统一从 `/market/symbols` 加载

**验证**：回测结果基于真实历史数据；理财页展示 OKX 真实产品；C2C 入口消失；无硬编码交易对残留。

---

### 块 E：加载态与错误提示（前端）

- 统一 loading 组件（骨架屏/spinner），各页面 API 请求期间显示
- 统一错误提示（toast 或 inline），`client.ts` 拦截器兜底
- OKX 报错信息透传给用户，便于排查凭证/权限/网络问题

**验证**：请求期间有加载反馈；接口报错有清晰提示而非静默失败。

---

### 块 F：部署一键化（运维脚本）

- **`init.sh` 一键初始化**：自动生成 `DJANGO_SECRET_KEY` 与 `SECRET_ENCRYPTION_KEY`；交互式询问域名/邮箱/DB 密码；生成 `.env.prod`；一键拉起全部服务
- **`update.sh` 一键热更新**：拉新代码 → 自动 `migrate` → 只滚动重建发生变更的服务 → 不中断现有服务；能检测环境差异决定是否重建
- **证书自动化**：改用 Caddy（或 nginx + certbot）自动申请/续期 Let's Encrypt，免手动放证书、免手动编辑域名
- **自动备份/恢复**：`backup.sh` 定时备份 PostgreSQL + 数据卷；`restore.sh` 一键恢复

**验证**：全新服务器执行一条 `init.sh` 命令即可完成部署；`update.sh` 可在不停机前提下完成代码迭代。

## 实施顺序建议

1. 块 A（去 mock + 数据同步）——其余块的地基
2. 块 D（遗留补全）——与 A 同属后端去 mock，可衔接
3. 块 C（Glass 组件族）——UI 基础
4. 块 B（行情选择器）——依赖 C 的组件风格
5. 块 E（加载态/错误提示）——UI 收尾
6. 块 F（部署一键化）——独立，可并行

## 超出范围

- C2C 真实商户接入（OKX 无公开接口，改为删除功能）
- 无假数据降级运行（去 mock 后不保留假数据兜底，仅做重连与提示）
