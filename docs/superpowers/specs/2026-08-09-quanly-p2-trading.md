# Quanly P2 交易主线 — 设计文档

> 日期:2026-08-09
> 依赖:P0 骨架、P1 行情(mock feed 已跑通)
> 目标:现货 + 永续下单/撤单/止盈止损/平仓,网页可测。走 mock 撮合(本机连不上 OKX),将来切真实 OKX 不动代码。

---

## 0. 决策(已敲定)

- **交易模式开关** `EXCHANGE_MODE`(okx/mock),与 P1 的 MARKET_FEED 同思路。本机连不上 OKX,首轮 `EXCHANGE_MODE=mock`。
- **mock 撮合**:市价单立即按当前行情价成交;限价单价格未到挂 pending,行情触及再成交。
- **撮合价来源**:复用 P1 mock 行情价(collector 每秒推的 close);撮合器读 Redis 里最新价。
- **前端**:`/trade` 操作台,现货 + 永续两个页签。
- **数据**:PostgreSQL 建 Order/Trade/Position 表,带 env(SIM/LIVE)+ user。mock 与真实写同样的表。

---

## 1. 架构:交易适配 + 撮合分层

```
前端 /trade ──REST──► DRF trading views ──► 订单编排(trading.service)
                                               │
                                     ┌─────────┴─────────┐
                            EXCHANGE_MODE=okx      EXCHANGE_MODE=mock
                                     │                    │
                          OKXAdapter.place_order   MockExchange.place_order
                          (调 OKX SDK)              (虚拟撮合,读行情价)
                                     └─────────┬──────────┘
                                        写 Order/Trade/Position (PostgreSQL)
                                        成交/状态变更 → 发 Redis → WS 推前端
```

- 订单编排层 `apps.trading.service`:与模式无关,负责校验、落库、调用引擎、发推送。
- **引擎抽象**:`TradingEngine` 接口(place/cancel/close/amend);`OKXEngine`(用 OKXAdapter)和 `MockEngine`(虚拟撮合)两实现,按 `EXCHANGE_MODE` 选。
  - 复用 P0 的 `ExchangeAdapter.place_order` 等抽象,mock 也实现同签名 → 上层完全一致。

---

## 2. 数据表(apps.trading,均带 env + user)

- `Order`:local_id、exchange_order_id、inst_type(SPOT/SWAP)、symbol、side(buy/sell)、pos_side(long/short,仅合约)、ord_type(market/limit)、px、sz、td_mode(cash/cross/isolated)、lever(合约)、state(pending/live/filled/canceled)、filled_sz、avg_px、created_at。
- `Trade`:order_fk、price、sz、ts(一单可多笔;mock 一次成交即一笔)。
- `Position`:inst_type、symbol、pos_side、qty、avg_px、lever、margin、upl(未实现盈亏,按最新价实时算)、liq_px(mock 简化估算)。现货持仓用 balance 表示(见下)。
- `Balance`:ccy、total、available、frozen(mock 模式初始给每个 env 一笔虚拟 USDT,如 100000)。

## 3. 后端 API(apps.trading,均需登录 + env 参数)

- `POST /api/trading/orders` 下单(body: env, inst_type, symbol, side, ord_type, sz, px?, td_mode?, lever?, pos_side?)
- `GET  /api/trading/orders?env=&state=` 委托列表
- `POST /api/trading/orders/{id}/cancel` 撤单
- `POST /api/trading/orders/{id}/tpsl` 设止盈止损(简化:附加 tp_px/sl_px)
- `GET  /api/trading/positions?env=` 持仓
- `POST /api/trading/positions/{id}/close` 一键平仓(市价反向)
- `GET  /api/trading/balances?env=` 余额
- `GET  /api/trading/trades?env=` 成交记录

## 4. MockEngine 撮合(apps.trading.mock_engine)

- **下单**:市价 → 读 Redis 最新价立即成交,写 Trade,更新 Position/Balance;限价 → 若价格立即可成交则成交,否则 state=pending 挂起。
- **挂单撮合**:collector(或新增 matcher 协程)每次行情更新时,扫 pending 限价单,触及即成交。首轮简化:在 `run_collector` 的 mock 循环里,每 tick 调 `mock_engine.match_pending(symbol, price)`。
- **现货**:买单扣 USDT、加币;卖单加 USDT、扣币。
- **永续**:开仓建/加 Position,平仓减/清 Position 并结算盈亏到 USDT。upl 按最新价实时算(前端可算,后端持仓接口也返回)。
- **止盈止损**:pending 的 tp/sl,行情触及触发市价平仓。
- 成交后发 Redis 频道 `trade:{user_id}:{env}` → WS 推前端刷新委托/持仓。

## 5. 前端 /trade 操作台

- 页签:现货 / 永续。顶部 env 切换(模拟盘/实盘)。
- **下单面板** `OrderForm`:symbol 选择、买/卖、市价/限价、数量、价格(限价)、合约加杠杆/多空/保证金模式。LIVE 下单二次确认。
- **当前委托** `OrderTable`:列出 pending/live,可撤单。
- **持仓** `PositionTable`(合约)/ 余额卡(现货):可一键平仓,显示浮盈。
- **成交记录**:最近成交。
- WS 订阅 `trade` 频道,成交/状态变更实时刷新。
- i18n zh/en。

## 6. Docker / 配置

- 加 `EXCHANGE_MODE`(.env.test=mock);compose 共享 env 加。
- matcher 复用 market-collector 进程(mock 循环里撮合 pending 单),不新增服务。

## 7. 验收(网页可测,mock 模式)

1. 现货市价买 BTC → 委托立即成交,USDT 减、BTC 增,成交记录出现。
2. 现货限价买(低于市价)→ 挂 pending;行情跌到价位 → 自动成交。
3. 撤销 pending 单 → 状态变 canceled。
4. 永续开多 → 持仓出现,浮盈随行情跳动;一键平仓 → 持仓清空、盈亏结算。
5. env 切 SIM/LIVE 数据隔离(各自独立余额/持仓)。

## 8. 不在 P2 范围

交割/期权/杠杆ETF/理财 前端(P6);真实资金一致性对账(P7);爆仓强平自动执行(P7,mock 先只估算 liq_px 展示)。
