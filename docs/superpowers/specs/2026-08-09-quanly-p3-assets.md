# Quanly P3 资产看板 + 账单 — 设计文档(精简)

> 日期:2026-08-09;依赖 P0-P2。目标:统一资产总看板 + 账单/资金流水,网页可测。

## 决策
- 加 `Bill` 表记资金流水(成交/平仓盈亏);撮合成交/平仓时顺带写。
- 看板先聚合**现货+合约**(有真实数据),理财/借贷卡片占位(0/未开通),P6 接入。
- 净值折算用当前 mock 行情价(币量 × 最新价)。
- 先做**实时聚合看板**(打开即算),净值曲线快照留后。

## 后端(apps.trading 扩展 + apps.assets 新建)
- **Bill 模型**(user+env):bill_type(trade/close_pnl)、ccy、amount(±)、symbol、balance_after、ts。
- 撮合引擎 `_settle_spot`/`_settle_swap`/`close_position` 里写 Bill。
- **资产聚合服务** `apps.assets.service.summarize(user, env)`:
  - 现货:各币种 total × 最新价折 USDT(USDT 本身 =1)。
  - 合约:持仓保证金 + 未实现盈亏(按最新价)。
  - 返回:total_equity、available、frozen(保证金)、upl、spot_value、swap_value、finance_value=0、loan_value=0、positions_dist(各持仓占比)。
- REST:
  - `GET /api/assets/summary?env=` → 上述聚合。
  - `GET /api/assets/bills?env=&limit=` → 账单流水。

## 前端
- **Dashboard 改造**(/dashboard):顶部总净值大数字 + 浮盈;卡片行:可用/冻结/现货市值/合约市值/理财(占位)/借贷(占位);仓位分布(简单占比条);env 切换。
- **账单页** `/assets/bills`:流水表(时间/类型/币种/金额/交易对),env 切换。侧边栏加入口。
- 复用 dataviz 配色画占比条。i18n。

## 验收
1. 现货买入后 Dashboard 总净值≈初始(买卖等值换算),现货市值反映持仓。
2. 永续开多后合约市值 = 保证金+浮盈,浮盈随行情跳。
3. 账单页看到每笔成交/平仓流水。
4. env 切换 sim/live 数据隔离。
