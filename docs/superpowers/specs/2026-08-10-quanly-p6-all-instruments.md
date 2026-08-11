# Quanly P6 全品类 — 设计文档

> 日期:2026-08-10;依赖 P0-P5。目标:兑现 OKX 全品类,每类都有可点可测页面。
> 现实约束:本机连不上 OKX。交易类扩展 mock 撮合做实;资金操作类用 mock 数据流。

## 分层策略
**交易类(撮合)**:现货✓、永续✓(已做)、**交割 FUTURES**、**期权 OPTION**、**杠杆ETF**。
  - 扩展 trading engine + InstType,前端交易台加页签,能真实下 mock 单、看持仓/委托。
  - 交割:类永续(方向/杠杆/持仓),加交割日字段(展示用)。
  - 期权:加行权价 strike、到期日 expiry、方向 call/put;简化撮合按当前价成交,持仓记权利金。
  - 杠杆ETF:特殊现货,symbol 如 BTC3L-USDT,复用现货撮合。

**资金操作类(mock 数据流,新 app apps.finance)**:理财(活期/定期/双币/Staking)、借贷、划转、C2C 查询。
  - 模型:FinanceProduct(产品:类型/币种/年化/期限)、FinanceHolding(持仓:产品/本金/收益)、Transfer(划转记录)。
  - API:产品列表、申购(subscribe)、赎回(redeem)、持仓、划转(账户间)、C2C 查询(mock 汇率/挂单)。
  - 申购/赎回联动 trading.Balance(扣/加 USDT),收益 mock 按年化累计(或简化固定)。

## 后端
### trading 扩展
- InstType 加 FUTURES / OPTION;engine 支持:交割同永续结算;期权简化(买方付权利金=价格*sz,记 Position);杠杆ETF 走现货路径。
- Order 加 strike/expiry(期权用,可空)。
- place_order serializer 放开 inst_type 到 5 类。

### 新 app apps.finance
- 模型 FinanceProduct(seed 内置产品:USDT活期3%/BTC定期5%/双币/ETH Staking4%)、FinanceHolding(user+env)、Transfer(user+env)。
- REST:
  - GET /api/finance/products?category= (earn/loan)
  - GET /api/finance/holdings?env=
  - POST /api/finance/subscribe (product_id, amount) → 扣 Balance、建/加 Holding
  - POST /api/finance/redeem (holding_id) → 加 Balance(本金+mock收益)、平 Holding
  - POST /api/finance/transfer (ccy, amount, from_acct, to_acct) → 记 Transfer(mock,账户间;简化只记录)
  - GET /api/finance/transfers?env=
  - GET /api/finance/c2c (mock 法币挂单/汇率查询)

## 前端
- **交易台 Trade.vue**:页签扩展为 现货/永续/交割/期权/杠杆ETF。期权表单加行权价+到期+call/put;交割加交割日;ETF 选带杠杆的 symbol。下单/委托/持仓复用现有(按 inst_type 区分展示列)。
- **新页 Finance.vue** `/finance`:理财产品列表(申购)、我的持仓(赎回)、Tab 切 理财/借贷。
- **新页 Transfer.vue** `/transfer`:资金划转表单(币种/数量/账户)+ 划转记录表(分页)。
- **C2C** 并入 Finance 或单独小页:mock 法币汇率/挂单查询(只读展示)。
- 侧边栏加:理财、划转 入口。i18n zh/en 全覆盖。表格均分页(默认10)。

## 验收(mock)
1. 交易台 5 个页签都能下单;期权带行权价/到期,交割带交割日,持仓正确。
2. 理财页申购 USDT活期 → 扣余额、出现持仓;赎回 → 回余额(含 mock 收益)。
3. 借贷页展示可借/申请(mock)。
4. 划转页提交 → 记录出现在划转表。
5. C2C 查询展示 mock 数据。
6. 全部表格分页、中英文切换无残留。

## 不在范围
真实 OKX 品类接口(接通后换数据源);理财收益精确按日计息(先简化);C2C 真实撮合。
