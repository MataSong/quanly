# 交易台合页 + K线实时化 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development(推荐)或 superpowers:executing-plans 逐任务执行。步骤用 checkbox(`- [ ]`)追踪。

**Goal:** 把行情+交易合成一个"交易台"页(K线+下单同屏,共享交易对),K线实时秒级跳动 + 悬停 OHLC 详情,策略页去掉"全部策略"卡片区。全程 PC/手机响应式 + 中英文。

**Architecture:** 前端新建 `views/trade/` 交易台(父页 TradeDesk + 子组件 TradeChart/TradeOrderPanel/TradeMonitor),Pinia store 共享 symbol/bar/credential;K线加 crosshair+tooltip+区分 candle/ticker 实时更新;后端采集器改动态订阅(Redis 活跃集合协调 Consumer 与 collector)+ 订阅 tickers 频道。

**Tech Stack:** Vue3+TS+Element Plus+Pinia+vue-i18n+lightweight-charts(前端);Django Channels+Redis+websockets+OKX public WS(后端)。

## Global Constraints

- **零 mock**:实时数据只来自真实 OKX,连不上则不跳动+显示 WS 断开状态,绝不造假。
- **PC 不退化**:>768px 交易台布局/交互合理;手机(≤768px)纵向滚 K线→下单→监控。
- **响应式基建复用**:`useBreakpoint`、`ResponsiveTable`、`styles/mixins.scss`(@include mobile ≤768)、tokens 变量。
- **i18n**:新增文案走 `t()`,`zh-CN.ts`+`en-US.ts` 双语对齐(`const en: typeof zh`,漏 key build fail)。
- **权限**:合并页需 `page:market` 且 `page:trading`(不新增 page 权限点);下单仍受 `trading:place_order`;撤单 `trading:cancel`;行情 `market:view`。
- **多租户**:credential 必 `get_object_or_404(..., user=request.user)`;下单/查询按 credential 归属。
- 本地 commit 不 push;精确 git add;每步 `npm run build`(前端)/`pytest`(后端)过。
- BASE commit = 当前 HEAD(f63992f)。

---

## File Structure

**前端(新建)**
- `frontend/src/stores/tradeDesk.ts` — Pinia store:symbol/bar/credentialId/instType 共享状态。
- `frontend/src/views/trade/TradeDesk.vue` — 父页:顶部共享选择栏 + 响应式布局容器。
- `frontend/src/views/trade/TradeChart.vue` — K线图(迁移 Market.vue 逻辑 + crosshair/tooltip/实时)。
- `frontend/src/views/trade/TradeOrderPanel.vue` — 下单表单(迁移 Trading.vue 表单)。
- `frontend/src/views/trade/TradeMonitor.vue` — 持仓/委托/余额(迁移 Trading.vue 三卡)。

**前端(改)**
- `frontend/src/composables/useMarketSocket.ts` — 支持 bar 参数 + 区分 candle/ticker 回调。
- `frontend/src/api/market.ts` — 类型补 ticker(如需)。
- `frontend/src/router/index.ts` — 新增 /trade 路由;/market /trading 重定向到 /trade。
- `frontend/src/layouts/AppShell.vue` — featureItems 移除 market/trading,新增 trade。
- `frontend/src/views/strategy/Strategy.vue` — 移除"全部策略"卡片区。
- `frontend/src/locales/{zh-CN,en-US}.ts` — 新增 trade.* / layout.nav.trade。

**前端(迁移后移除)**
- `frontend/src/views/market/Market.vue`、`frontend/src/views/trading/Trading.vue`(逻辑迁移到 trade/ 子组件后删除)。

**后端(改)**
- `backend/core/market/consumers.py` — connect/disconnect 登记/注销活跃订阅到 Redis;支持 bar(从 query string 取 bar)。
- `backend/core/market/management/commands/run_market_collector.py` — 动态订阅:轮询 Redis 活跃集合 diff OKX 订阅;新增 tickers 频道;ticker 消息广播。
- `backend/core/market/consumers.py` 的 `market_update` handler — 支持转发 ticker 消息。

**后端(测试)**
- `backend/tests/test_market_realtime.py` — 活跃订阅登记/注销、diff 逻辑、ticker 广播(OKX 打桩)。

---

## Task 1: Pinia 交易台共享 store

**Files:**
- Create: `frontend/src/stores/tradeDesk.ts`

**Interfaces:**
- Produces: `useTradeDeskStore()` → `{ symbol, bar, credentialId, instType }`(reactive refs/state)+ setter actions。

- [ ] **Step 1: 写 store**

```ts
import { defineStore } from "pinia";
import { ref } from "vue";

export const useTradeDeskStore = defineStore("tradeDesk", () => {
  const symbol = ref("BTC-USDT");
  const bar = ref("1m");
  const credentialId = ref<number | null>(null);
  const instType = ref<"SPOT" | "SWAP">("SPOT");

  function setSymbol(s: string) { symbol.value = s; }
  function setBar(b: string) { bar.value = b; }
  function setCredential(id: number | null) { credentialId.value = id; }
  function setInstType(t: "SPOT" | "SWAP") { instType.value = t; }

  return { symbol, bar, credentialId, instType, setSymbol, setBar, setCredential, setInstType };
});
```

- [ ] **Step 2: build 验证**

Run: `cd frontend && npm run build`
Expected: PASS(TS 类型过)。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/stores/tradeDesk.ts
git commit -m "feat(trade): 交易台共享状态 store(symbol/bar/credential/instType)"
```

---

## Task 2: useMarketSocket 支持 bar + 区分 candle/ticker

**Files:**
- Modify: `frontend/src/composables/useMarketSocket.ts`

**Interfaces:**
- Consumes: 后端 WS 消息 `{type:"market_update", symbol, candle?}` 和(新)`{type:"market_update", symbol, ticker?:{last}}`。
- Produces: `useMarketSocket(symbol, { onCandle, onTicker })` — 回调分离;symbol 变化时重连(现在 symbol 是入参,组件切 symbol 时需重建 composable 或支持响应式 symbol)。

**说明:** 现有 useMarketSocket 用固定 symbol 入参。改为接受回调对象,onmessage 里 `if(msg.candle) onCandle(msg.candle); if(msg.ticker) onTicker(msg.ticker)`。symbol 切换由调用方(TradeChart)在 symbol 变化时 disconnect + 重新调用(或组件用 key 重建)。bar 不进 WS URL(group 按 symbol),但前端切 bar 后需通知后端订阅新 bar——**方案**:WS URL 带 bar query(`/ws/market/<symbol>/?token=&bar=<bar>`),Consumer 据此登记 (symbol,bar)。

- [ ] **Step 1: 改回调签名 + ticker 分支 + bar query**

```ts
export interface MarketSocketHandlers {
  onCandle?: (candle: Candle) => void;
  onTicker?: (ticker: { last: string }) => void;
}
export function useMarketSocket(symbol: string, bar: string, handlers: MarketSocketHandlers) {
  // url: `${WS_BASE}/ws/market/${symbol}/?token=${token}&bar=${bar}`
  // onmessage: msg.candle → handlers.onCandle?.(msg.candle); msg.ticker → handlers.onTicker?.(msg.ticker)
}
```

- [ ] **Step 2: build 验证** — `cd frontend && npm run build` PASS。
- [ ] **Step 3: Commit**

```bash
git add frontend/src/composables/useMarketSocket.ts
git commit -m "feat(trade): useMarketSocket 支持 bar + 区分 candle/ticker 回调"
```

---

## Task 3: 后端 Consumer 登记活跃订阅 + bar

**Files:**
- Modify: `backend/core/market/consumers.py`

**Interfaces:**
- Produces: connect 时 `SADD market:active "<symbol>:<bar>"` + Redis 计数 `INCR market:refcount:<symbol>:<bar>`;disconnect 时计数 DECR,归 0 则 `SREM`。bar 从 query string 取(默认 1m)。
- market_update handler 支持转发 ticker(event 里可能有 candle 或 ticker)。

- [ ] **Step 1: connect 取 bar + 登记 Redis**

connect 里:`bar = params.get("bar", ["1m"])[0]`;用 `redis`(channels-redis 已装 redis)客户端:活跃集合 key `market:active`,成员 `f"{symbol}:{bar}"`;引用计数 key `market:sub:{symbol}:{bar}`。connect INCR + 若首次则 SADD;disconnect DECR + 若归 0 则 SREM。用 `redis.asyncio` 或 `channels.layers` 底层连接。**方案**:直接用 `redis.asyncio.from_url(REDIS_URL)`(REDIS_HOST/PORT env 已有)。

- [ ] **Step 2: market_update handler 转发 ticker**

```python
async def market_update(self, event):
    payload = {"type": "market_update", "symbol": event.get("symbol")}
    if event.get("candle") is not None:
        payload["candle"] = event["candle"]
    if event.get("ticker") is not None:
        payload["ticker"] = event["ticker"]
    await self.send(text_data=json.dumps(payload))
```

- [ ] **Step 3: 单测**(mock redis)验证 connect 登记 / disconnect 注销 / 计数。
- [ ] **Step 4: pytest 过 + Commit**

```bash
git add backend/core/market/consumers.py backend/tests/test_market_realtime.py
git commit -m "feat(market): Consumer 登记活跃订阅到 Redis + 转发 ticker"
```

---

## Task 4: 采集器动态订阅 + tickers 频道

**Files:**
- Modify: `backend/core/market/management/commands/run_market_collector.py`

**Interfaces:**
- Consumes: Redis `market:active` 集合(成员 `<symbol>:<bar>`)。
- 行为:循环读活跃集合,与当前 OKX 已订阅 diff;新增 → 发 `{"op":"subscribe","args":[{channel:"candle<bar>",instId},{channel:"tickers",instId}]}`;消失 → unsubscribe。tickers 消息解析 `last` → group_send `{"type":"market.update","symbol","ticker":{"last":...}}`。

**说明:** 保留无活跃订阅时的保底(订阅默认 BTC-USDT candle1m,避免空转),但主要靠动态。tickers 频道 instId 级(不带 bar),candle 频道带 bar。diff 逻辑:维护 `subscribed: set[(channel,instId)]`,每隔 N 秒(或 Redis pub/sub 通知)读活跃集合重算目标订阅集,发送 subscribe/unsubscribe 差异。**权衡**:轮询实现简单(每 3-5s 读一次 Redis diff);pub/sub 实时但复杂。**采用轮询**(interval 3s),够用。

- [ ] **Step 1: 重构 _run 为动态订阅循环**

拆两个协程:①OKX WS 读循环(收 candle/ticker 广播);②Redis 轮询循环(每 3s 读 market:active,diff 后 send subscribe/unsubscribe)。asyncio.gather 并跑。ticker 解析:tickers 频道 data 行含 `last`,广播 ticker 消息。

- [ ] **Step 2: tickers 消息广播** — 解析 `arg.channel=="tickers"` → `{"ticker":{"last":row["last"]}}`。

- [ ] **Step 3: 单测**(打桩 OKX WS + Redis)验证 diff 生成正确的 subscribe/unsubscribe args + ticker 广播。

- [ ] **Step 4: pytest 过 + Commit**

```bash
git add backend/core/market/management/commands/run_market_collector.py backend/tests/test_market_realtime.py
git commit -m "feat(market): 采集器动态订阅活跃交易对/周期 + tickers 频道"
```

---

## Task 5: TradeChart 子组件(K线 + crosshair + 实时)

**Files:**
- Create: `frontend/src/views/trade/TradeChart.vue`

**Interfaces:**
- Consumes: `useTradeDeskStore()`(symbol/bar);`useMarketSocket`;`api/market.ts` getCandles/getSymbols。
- 迁移 Market.vue 的:图表初始化、时区格式化、REST 拉历史 200 根、分页向前 loadHistory、setData/fitContent。
- 新增:`crosshair` 配置 + `subscribeCrosshairMove` → tooltip 浮层(OHLC+时间,涨绿跌红);右上角最新价;WS onCandle → series.update;onTicker → 更新最后一根 bar close + 最新价。切 symbol/bar 时重载 + WS 重连。

- [ ] **Step 1: 迁移 Market 图表逻辑到 TradeChart** — 图表/时区/历史/分页,symbol/bar 从 store 取。
- [ ] **Step 2: 加 crosshair + tooltip** — createChart 配 crosshair;subscribeCrosshairMove 读 seriesData;浮层 DOM 显示 OHLC(i18n `trade.ohlc.*`,涨跌着色)。
- [ ] **Step 3: 接实时** — useMarketSocket(symbol, bar, {onCandle: series.update, onTicker: 更新末根close+最新价});WS 连接状态 tag。
- [ ] **Step 4: 响应式** — 图表高度手机 260/PC 420(复用 useBreakpoint + watch applyOptions,参照 R2)。
- [ ] **Step 5: build 过 + Commit**

```bash
git add frontend/src/views/trade/TradeChart.vue
git commit -m "feat(trade): TradeChart 子组件(K线+悬停OHLC+实时跳动)"
```

---

## Task 6: TradeOrderPanel + TradeMonitor 子组件

**Files:**
- Create: `frontend/src/views/trade/TradeOrderPanel.vue`、`frontend/src/views/trade/TradeMonitor.vue`

**Interfaces:**
- Consumes: `useTradeDeskStore()`(credentialId/symbol/instType);`api/trading.ts`。
- TradeOrderPanel:迁移 Trading.vue 下单表单(SPOT/SWAP、live 二次确认);inst_id 默认取 store.symbol,instType 改写回 store。
- TradeMonitor:迁移 Trading.vue 持仓/委托(撤单)/余额三张 ResponsiveTable 卡片;credentialId 取 store。

- [ ] **Step 1: TradeOrderPanel** — 迁移下单表单,credential/symbol/instType 从 store;下单后通知 TradeMonitor 刷新(store event 或 emit)。
- [ ] **Step 2: TradeMonitor** — 迁移三卡表格,ResponsiveTable 卡片化(复用现 Trading.vue 的 columns/slot)。
- [ ] **Step 3: build 过 + Commit**

```bash
git add frontend/src/views/trade/TradeOrderPanel.vue frontend/src/views/trade/TradeMonitor.vue
git commit -m "feat(trade): TradeOrderPanel 下单 + TradeMonitor 持仓委托余额子组件"
```

---

## Task 7: TradeDesk 父页 + 布局 + 路由菜单

**Files:**
- Create: `frontend/src/views/trade/TradeDesk.vue`
- Modify: `frontend/src/router/index.ts`、`frontend/src/layouts/AppShell.vue`、`frontend/src/locales/{zh-CN,en-US}.ts`

**Interfaces:**
- Consumes: 三子组件 + useTradeDeskStore。
- 顶部共享栏:symbol select(getSymbols)、bar select、时区、credential select(env 着色)。改 store。
- 布局:PC `grid 1fr 360px`(左 TradeChart、右 TradeOrderPanel)+ 下方全宽 TradeMonitor;手机纵向 chart→order→monitor(@include mobile)。

- [ ] **Step 1: TradeDesk 父页** — 共享选择栏 + 布局 grid + 挂三子组件。
- [ ] **Step 2: 路由** — 新增 `/trade`(meta.perm 组合校验 page:market+page:trading,或用现有守卫支持多 perm;若守卫只支持单 perm 则用 page:trading 主 + 组件内校验 market);`/market`、`/trading` redirect 到 `/trade`。
- [ ] **Step 3: 菜单 i18n** — AppShell featureItems 去 market/trading 加 trade;locales 加 `layout.nav.trade` + `trade.*`(标题/选择器/ohlc/latestPrice 等)zh/en 对齐。
- [ ] **Step 4: build 过 + Commit**

```bash
git add frontend/src/views/trade/TradeDesk.vue frontend/src/router/index.ts frontend/src/layouts/AppShell.vue frontend/src/locales/zh-CN.ts frontend/src/locales/en-US.ts
git commit -m "feat(trade): TradeDesk 交易台父页 + 路由菜单合并(替换行情+交易)"
```

---

## Task 8: 清理旧页 + 策略页微调

**Files:**
- Delete: `frontend/src/views/market/Market.vue`、`frontend/src/views/trading/Trading.vue`(确认逻辑已全迁移)
- Modify: `frontend/src/views/strategy/Strategy.vue`

- [ ] **Step 1: 移除旧 Market/Trading 页** — 确认无其它 import 引用(router 已改),删除文件。
- [ ] **Step 2: 策略页去掉"全部策略"卡片区** — 移除 `v-for s in strategies` 顶部卡片区;新建运行对话框保留策略选择下拉(仍需 listStrategies 供选择);页面主体只剩"我的运行"表格。
- [ ] **Step 3: build 过 + Commit**

```bash
git add frontend/src/views/strategy/Strategy.vue
git rm frontend/src/views/market/Market.vue frontend/src/views/trading/Trading.vue
git commit -m "feat(trade): 移除旧行情/交易页 + 策略页去掉全部策略卡片区"
```

---

## Task 9: Docker 重建 + 端到端验收

- [ ] **Step 1: 重建** — `./deploy.sh update`(或 `docker compose up -d --build backend celery-worker market-collector nginx`),载入采集器动态订阅 + 前端交易台。
- [ ] **Step 2: 验收**(见 Verification)。

---

## Verification(整体)

1. **build/pytest**:前端 `npm run build` 过;后端 `pytest` 过(市场实时新测 + 回归)。
2. **PC 交易台**:菜单只剩"交易台";左图右单+下方监控;切交易对→图和下单表单同步;悬停 K线显示 OHLC+时间(涨绿跌红);选 credential→下单/持仓/委托/余额可用;下单 live 二次确认。
3. **手机(375px)**:纵向滚 交易对→K线→下单→监控;图表高度 260;监控表格卡片化;下单表单 label 在上。
4. **实时(真连 OKX,切代理)**:选任意交易对/周期→采集器动态订阅→K线末根随成交跳+tickers 驱动最新价秒级跳+右上角最新价;切交易对→重订新流跳;无代理时不跳+WS 断开状态(零 mock)。
5. **i18n**:中英文切换交易台所有文案正确无缺 key。
6. **策略页**:无"全部策略"卡片区,只"我的运行"表格;新建运行仍能选策略。
7. **回归**:/market /trading 书签重定向 /trade;资产看板/回测/密钥/管理页不受影响;订阅泄漏检查(多次开关 WS 后 Redis market:active 计数正确归零)。

---

## 执行方式

subagent-driven-development:Task 1-4(store/socket/后端两个)相对独立可先做;Task 5-8 前端组件有依赖需顺序(store→socket→chart→panel→desk→清理)。每任务 review + build/pytest。做完 Docker 重建端到端(实时需切代理连 OKX)。BASE=f63992f。
