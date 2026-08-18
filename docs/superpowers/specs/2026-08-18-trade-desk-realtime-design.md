# 交易台合页 + K线实时化 设计文档

**日期**: 2026-08-18
**范围**: 行情+交易合并为"交易台"页 + K线实时秒级跳动 + 悬停 OHLC 详情 + 策略页微调。全程 PC/手机响应式 + 中英文 i18n。
**不在本次范围**(留独立 spec): 策略商城生态(用户自写策略、共享/私有、商城授权)。

---

## 背景与目标

quanly 当前行情(Market)和交易(Trading)是两个独立页面,用户需切换查看行情和下单。K线图无实时跳动(采集器只订阅写死的 BTC/ETH + 单一周期,切换交易对/周期不更新)、无悬停 OHLC 详情。用户希望:
1. 行情+交易合成一个"交易台"页,看盘和下单同屏,交易所式体验。
2. K线实时秒级跳动 + 鼠标悬停显示该根 OHLC 详情。
3. 策略页表格只显示自己运行/使用的策略(去掉"展示全部策略"),为将来策略商城留位。
4. 所有改动兼容 PC + 手机,遵守全局中英文切换。

已确认决策:
- 合页形态 = **交易台**(K线+下单同屏,PC 左图右单、手机纵向滚 K线→下单→监控)。
- 菜单 = **合为单项"交易台"**(替换原行情+交易两项)。
- 实时程度 = **真实时**(采集器动态订阅任意交易对/周期 + tickers 频道驱动最新价秒级跳)。

---

## 一、交易台页面(合并行情+交易)

### 路由与权限
- 新页 `/trade`,`meta.perm` 用组合校验:需要 `page:market` 且 `page:trading`(两者都有才显示菜单/可访问)。**保留** `page:market`/`page:trading` 两个权限点不新增(合并页取二者交集)。
- AppShell 菜单:移除原 `market`、`trading` 两项,新增单项 `trade`(i18n `layout.nav.trade`,图标沿用交易类)。
- 路由:移除 `/market`、`/trading` 独立路由(或保留重定向到 `/trade`,避免旧书签 404 —— 采用重定向)。

### 组件结构
新建交易台页,拆为父页 + 三个子组件(职责单一、便于维护):
- `frontend/src/views/trade/TradeDesk.vue`(父):顶部共享栏(交易对/周期/时区/凭证选择)+ 布局容器,组合三子组件。
- `frontend/src/views/trade/TradeChart.vue`:K线图(复用现 Market.vue 的图表+WS+分页历史逻辑 + 新增 crosshair/tooltip/实时,见第二节)。
- `frontend/src/views/trade/TradeOrderPanel.vue`:下单表单(复用现 Trading.vue 的 SPOT/SWAP 表单、live 二次确认)。
- `frontend/src/views/trade/TradeMonitor.vue`:持仓/委托(可撤单)/余额(复用现 Trading.vue 的三张 ResponsiveTable 卡片)。
- 原 `views/market/Market.vue`、`views/trading/Trading.vue` 逻辑迁移后移除(或保留内部逻辑抽到 composable 复用)。

### 共享状态(交易所式联动)
新建 `frontend/src/stores/tradeDesk.ts`(Pinia store):
- state: `symbol`(当前交易对,默认 BTC-USDT)、`bar`(周期,默认 1m)、`credentialId`(当前凭证)、`instType`(SPOT/SWAP)。
- 顶部选择器改这个 store;TradeChart 监听 `symbol`/`bar` 重载图表+WS;TradeOrderPanel 的 `inst_id` 默认取 store.symbol(用户仍可在表单内改);切换交易对时图表和下单表单同步。
- credential 选择也提到共享栏(交易需要,行情不需要 —— 未选 credential 时图表正常显示,下单/监控区提示选凭证)。

### 布局(响应式)
- **PC(>768px)**:`grid-template-columns: 1fr 360px` —— 左 K线图(主区)、右下单表单;下方全宽三卡监控(持仓/委托/余额)。
- **手机(≤768px)**:单列纵向滚 —— 交易对选择栏 → K线图(高度自适应,复用 R2 的 260px 手机高度) → 下单表单 → 监控三卡。
- 全部用现有基建:`useBreakpoint`、`ResponsiveTable`、`mixins.scss` 的 `@include mobile`、tokens 变量。

---

## 二、K线实时化 + 悬停 OHLC

### A. 悬停 OHLC 详情(纯前端,TradeChart.vue)
- `createChart` 增加 `crosshair` 配置(mode: Normal,显示十字光标)。
- `chart.subscribeCrosshairMove(param)` 回调:从 `param.seriesData.get(series)` 取当前悬停 K 线的 `{open,high,low,close,time}`,更新一个浮层 tooltip DOM(绝对定位跟随 `param.point`,或固定在图左上角显示)。
- tooltip 内容:开/高/低/收 + 时间,涨(close≥open)绿、跌红。文案走 i18n(`trade.ohlc.open/high/low/close`)。
- 图右上角常驻:当前最新价 + (可选)24h 涨跌幅,由实时流驱动。

### B. 实时秒级跳动(前后端)

**后端 —— 动态订阅**:
- 改 `backend/core/market/management/commands/run_market_collector.py`:不再用命令行写死 `--symbols`,改为**按活跃订阅动态订阅 OKX**。
- 协调机制:Redis 记录活跃订阅集合。`MarketConsumer`(`consumers.py`)在 `connect` 时把 `(symbol, bar)` 登记进 Redis(如 `SADD market:active <symbol>:<bar>` + 引用计数),`disconnect` 时注销(引用计数减到 0 才移除)。
- 采集器循环读取 Redis 活跃集合,与当前 OKX 已订阅集合 diff:新增的 `subscribe`(candle{bar} + tickers),消失的 `unsubscribe`。避免订阅泄漏。
- 订阅频道:除现有 `candle{bar}` 外,新增 `tickers`(拿 lastPx 最新成交价)。tickers 消息 group_send 为 `{type:"market_update", symbol, ticker:{last, ...}}`,与 candle 消息区分(candle 更新整根 bar,ticker 只更新当前 bar 的 close + 最新价显示)。

**前端 —— 实时更新**:
- `useMarketSocket` 回调区分 `msg.candle`(整根更新 `series.update(bar)`) 和 `msg.ticker`(更新最后一根 bar 的 close = ticker.last + 更新右上角最新价)。
- 切换 symbol/bar 时 WS 重连对应流(现有 useMarketSocket 已按 symbol 建连,需支持 bar 变化重连 + 后端按新 bar 订阅)。
- group 名 `market_<symbol>`,bar 维度由采集器订阅正确的 candle{bar} 保证前端收到对应周期。

**零 mock**:连不上 OKX 则无推送,图表显示 WS 连接状态(现有 el-tag),不造假数据。

---

## 三、策略页微调

- `frontend/src/views/strategy/Strategy.vue`:**移除**顶部"展示全部内置策略"的卡片区(现 `v-for s in strategies` 列出全部全局策略)。新建运行对话框里保留策略选择下拉(供选择要运行的策略)。
- 页面主体保留"我的运行"表格(现已 `listRuns()` 按用户过滤,符合"自己运行/使用的策略"语义)。
- 不改后端。为将来"策略商城""我的策略"菜单预留(本次不做)。

---

## 四、响应式 + i18n(全程约束)

- 所有新组件/UI 用 `useBreakpoint`、`ResponsiveTable`、`mixins.scss`(@include mobile ≤768)、tokens 变量。PC 不退化。
- 新增 i18n key(zh-CN.ts + en-US.ts 双语对齐,`const en: typeof zh` 强制):
  - `layout.nav.trade`(交易台 / Trade Desk)
  - `trade.*`:页面标题、选择器 label、下单/监控区标题、ohlc.open/high/low/close/time、最新价 latestPrice 等。
  - 复用现有 market.*/trading.* 已有 key(迁移时保留)。
- 移除菜单项 market/trading 后,其 i18n key 可保留(仍被迁移的组件复用)。

---

## 五、错误处理

- OKX 连不上:图表 WS 状态显示断开,不跳动,不造假(零 mock)。
- 动态订阅失败/OKX 拒订:采集器记录日志,前端图表仍显示历史(REST 拉的),只是不实时。
- 未选 credential:下单/监控区提示选凭证(现有空状态),图表不受影响正常显示行情。
- Redis 订阅登记异常:采集器降级(退回订阅默认 BTC-USDT 保底,记日志),避免整个实时链路挂掉。

---

## 六、验证

1. **build**:`cd frontend && npm run build` 过(vue-tsc + vite)。
2. **PC 交易台**:菜单只剩"交易台"单项;左图右单 + 下方监控;切交易对 → 图和下单表单同步;悬停 K线显示 OHLC;选 credential → 下单/持仓/委托/余额可用。
3. **手机**:纵向滚 K线→下单→监控;图表高度自适应;下单表单 label 在上;监控表格卡片化。
4. **实时(需真连 OKX,切代理)**:选任意交易对/周期 → 采集器动态订阅 → K线最后一根随成交跳动 + tickers 驱动最新价秒级跳;切换交易对 → 重新订阅新流跳动;右上角最新价实时。无代理时不跳,显示 WS 断开(零 mock)。
5. **i18n**:中英文切换所有交易台文案正确,无缺 key。
6. **策略页**:无"全部策略"卡片区,只有"我的运行"表格;新建运行对话框仍能选策略。
7. **回归**:旧 /market /trading 书签重定向到 /trade;其它页面不受影响。

---

## 七、后续(独立 spec,本次不做)

- **策略商城生态**:Strategy 加 owner + 可见性(公开/私有);create/update/delete API(权限点已定义未接线);授权中间表(user × strategy);runner 支持用户自写策略(source_type=uploaded 接线 + 沙箱);策略商城页 + 我的策略管理页。
