# Quanly P5 回测引擎 — 设计文档

> 日期:2026-08-09;依赖 P0-P4。目标:事件驱动回测 + 完整绩效指标 + 回测控制台。

## 决策
- 回测**复用策略 on_tick(ctx) 接口**:同一脚本实盘/回测通用。回测 ctx 提供 price/symbol/buy/sell/log,但用历史 bar + 模拟成交,不落真实订单表。
- 数据源先用 **mockfeed 生成历史 K 线**(指定根数/周期);将来接 InfluxDB 真实历史,引擎不变。
- **同步跑**(后端进程内,秒级),不进 celery。
- 指标做全(市面主流)。

## 引擎 apps.backtest.engine
- `run_backtest(source, symbol, bar, bars, initial_capital, fee_rate)`:
  1. 生成/取历史 K 线(mockfeed.history_candles)。
  2. 构造 BacktestContext(内部持仓/现金/成交记录),exec 策略源,取 on_tick。
  3. 逐 bar:ctx 当前价=该 bar close,调 on_tick;ctx.buy/sell 按当前价+滑点/手续费模拟成交,更新持仓/现金,记 trade + equity 点。
  4. 收尾按最后价平掉持仓估值。
  5. 算指标,返回 {equity_curve, trades, metrics, logs}。
- **模拟成交**:市价按当前 bar close 成交,扣手续费(fee_rate);现货多头模型(买入持币、卖出得现金)。

## 指标 apps.backtest.metrics(基于 equity_curve + trades)
- 收益:total_return、annual_return、final_equity。
- 风险:max_drawdown、max_dd_duration、annual_volatility、downside_volatility。
- 风险调整:sharpe、sortino、calmar。
- 交易:win_rate、profit_factor、trade_count、win/loss count、avg_win/avg_loss、max_win/max_loss。

## 后端模型 + API
- `Backtest`(user):strategy_fk(可空,也可直接传 source)、symbol、bar、bars、initial_capital、fee_rate、status、created_at;结果 JSON 字段(metrics、equity_curve 引用)。
- 简化:同步跑,结果直接存 Backtest.result_json(TextField)。
- REST(JWT):
  - `POST /api/backtests/run`(body: strategy_id 或 source, symbol, bar, bars, initial_capital, fee_rate)→ 同步跑 → 存 + 返回结果。
  - `GET /api/backtests`、`GET /api/backtests/{id}` → 历史回测。

## 前端 回测控制台 /backtest
- 配置表单:选策略(下拉,取策略列表)、交易对、周期、历史根数、初始资金、手续费率。
- 运行按钮 → 调 run → 展示:
  - **收益曲线**(Lightweight Charts line series,equity_curve)。
  - **指标卡片网格**(全部指标,dataviz 配色,盈亏红绿)。
  - 成交列表(可折叠)。
- 历史回测列表。i18n。侧边栏加"回测"入口。

## 验收
1. 选内置均线策略,配 500 根 1m、初始 10000,运行 → 秒级出收益曲线 + 指标。
2. 指标合理(胜率 0-100%、最大回撤负值、夏普有值)。
3. 换网格策略/换参数重跑,结果变化。
4. 历史回测可回看。

## 不在 P5 范围
真实历史数据(接 OKX 后);多标的组合回测;参数寻优/网格搜索(后续)。
