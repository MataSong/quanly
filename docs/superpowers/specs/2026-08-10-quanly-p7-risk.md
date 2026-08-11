# Quanly P7 风控与收尾 — 设计文档

> 日期:2026-08-10;依赖 P0-P6,最后一个主线阶段。目标:补齐安全与风控。

## 范围(全做,深浅有别)
1. **强平价 + 爆仓预警**(OKX 真实公式,MMR 用文档默认档位)
2. **止盈止损触发**(自动平仓)
3. **资金一致性对账**(逻辑框架 + 接口)
4. **接口限流**(DRF throttle)
5. **WS 鉴权**(TradeConsumer 加 token)
6. **并发订单幂等**(client_order_id 幂等键)

## 1. 强平价(apps.trading.risk)
OKX 逐仓 USDT 本位公式(方案 A,MMR 档位用文档默认值,接通后换 position-tiers):
```
多头强平价 = 开仓价 × (1 - 1/lever + MMR + feeRate)
空头强平价 = 开仓价 × (1 + 1/lever - MMR - feeRate)
```
- MMR 默认档位:`MMR_DEFAULT = {"BTC":0.004,"ETH":0.005, default:0.01}`(注释标明将来换 `GET /api/v5/public/position-tiers`)。
- feeRate=0.0005(taker)。
- `liq_price(pos)` 计算并写入 Position.liq_px(P0 已有字段)。
- 保证金率 = (保证金 + 未实现盈亏) / 名义价值;逼近强平(如现价距强平价 < 5%)→预警。

## 2. 爆仓预警 + 止盈止损触发(collector 每 tick)
- collector mock 循环里,对每个持仓:
  - 算 liq_price + 保证金率;距强平 <5% → publish `trade:{uid}:{env}` 一条 warning(前端弹提示)。
  - 现价触及强平价 → engine.close_position(强平)。
  - 持仓/挂单的 tp_px/sl_px 触及 → 平仓/触发。
- 新 `engine.check_risk(symbol, price)`:遍历该 symbol 持仓,处理 tp/sl/强平。

## 3. 资金对账(apps.trading.reconcile)
- `reconcile(user, env)`:重算 Balance 应有值 vs 实际(mock 下:sum(bills)+初始 == balance?),返回差异报告。
- REST `GET /api/trading/reconcile?env=` 返回对账结果(一致/差异列表)。真实模式将比对 OKX 实际余额。

## 4. 接口限流
- settings DRF DEFAULT_THROTTLE:anon 30/min,user 600/min;交易下单单独 throttle scope `trade` 120/min。
- place_order 视图加 throttle_scope。

## 5. WS 鉴权
- TradeConsumer:连接时校验 query `?token=<jwt>`,解出 user_id 必须与 url user_id 一致,否则 close。用 simplejwt 解析。
- 前端连接 WS 时带 `?token=<access>`。

## 6. 并发订单幂等
- Order 加 client_order_id(可空,唯一);place_order 若带 client_order_id 且已存在 → 返回原订单(幂等)。engine 已 select_for_update 防并发结算。

## 前端
- 爆仓预警:全局监听 trade WS 的 warning 消息 → 顶部 toast/提示。
- 对账:资产看板或账单页加"对账"按钮显示结果。
- 止盈止损:交易台下单可选填 tp/sl(合约)。
- i18n zh/en。

## 验收
1. 开合约仓 → 持仓显示强平价;价格逼近 → 收到预警;触及 → 自动强平。
2. 设止盈止损 → 触及自动平仓。
3. 对账接口返回一致/差异。
4. 高频请求触发限流 429。
5. WS 无 token/错 token 被拒。
6. 同 client_order_id 重复下单只成交一次。

## 不在范围
真实 OKX position-tiers 实时档位(接通后接);资金费率/自动减仓 ADL;跨保证金组合风险。
