# 子项目 E — 行情交易一体化页面 实现计划

> **For agentic workers:** 当前会话直接执行(用户约束:严禁 git)。后端 depth 以 pytest 检查,前端以 npm run build + 结构检查为准(无法在此跑浏览器,UI 正确性以 build 通过 + 人工核对说明)。

**Goal:** 合并 /market + /trade 为单一三栏 Terminal.vue(左币种列|中K线+指标+下方页签|右下单),补齐深度盘口/指标工具/成交历史。

**Architecture:** 新建 Terminal.vue 三栏容器,复用 CandleChart.vue,新建 SymbolList/OrderBook/IndicatorPanel;搬 Trade.vue 的下单/仓位/委托逻辑;新增 Pinia terminal store 共享 symbol/env/instType;后端加 DepthConsumer 直连 OKX books5。

**Tech Stack:** Vue3 + Pinia + lightweight-charts v5;Django Channels。

## Global Constraints

- **严禁 git 操作**;后端测试 pytest,前端 `npm run build`。
- 不破坏 trading REST/engine、OKX 适配器、虚实盘 env、风控、回测(仅前端重组 + 新增 depth WS)。
- 深度盘口走 OKX 直连 books5(与 MarketConsumer 同架构),不引入 mock 源。
- i18n zh/en 对齐;Glass 毛玻璃 + 深浅主题沿用。
- WS URL:market `/ws/market/{symbol}?bar=`;trade `/ws/trade/{uid}/{env}?token=`;depth 新增 `/ws/depth/{symbol}`。

---

## File Structure

- `backend/apps/market/consumers.py`：新增 `DepthConsumer`（仿 MarketConsumer，订阅 OKX `books5`）。
- `backend/config/ws_routing.py`：加 `/ws/depth/{symbol}`。
- `backend/apps/market/test_depth.py`（新建）：DepthConsumer 消息构造纯函数测试。
- `frontend/src/stores/terminal.ts`（新建）：symbol/env/instType 共享状态。
- `frontend/src/components/SymbolList.vue`（新建）：左栏币种列。
- `frontend/src/components/OrderBook.vue`（新建）：深度盘口。
- `frontend/src/components/IndicatorPanel.vue`（新建）：指标开关 + 计算叠加。
- `frontend/src/components/CandleChart.vue`（改）：暴露叠加指标线的接口。
- `frontend/src/views/Terminal.vue`（新建）：三栏主页面（含下单/仓位/委托/成交历史）。
- `frontend/src/api/market.ts`（新建或复用 client）：symbols。
- `frontend/src/router/index.ts`、`layouts/GlassLayout.vue`：路由合并 + 侧边栏。
- 删除 `frontend/src/views/Market.vue`、`Trade.vue`。
- `frontend/src/i18n/*`：`terminal.*`。

---

### Task 1: 后端 DepthConsumer + 路由

**Files:**
- Modify: `backend/apps/market/consumers.py`、`backend/config/ws_routing.py`
- Test: `backend/apps/market/test_depth.py`

**Interfaces:**
- Produces: `DepthConsumer`（连 `/ws/depth/{symbol}`，订阅 OKX `books5`，转发 `{"type":"depth","symbol","bids":[[px,sz]...],"asks":[[px,sz]...]}`）；模块级纯函数 `build_depth_payload(symbol, data_row) -> str` 便于单测。

- [ ] **Step 1: 写失败测试**

```python
# backend/apps/market/test_depth.py
import json


def test_build_depth_payload():
    from apps.market.consumers import build_depth_payload
    row = {"bids": [["100.5", "2", "0", "1"]], "asks": [["100.6", "3", "0", "1"]]}
    out = json.loads(build_depth_payload("BTC-USDT", row))
    assert out["type"] == "depth"
    assert out["symbol"] == "BTC-USDT"
    assert out["bids"] == [[100.5, 2.0]]
    assert out["asks"] == [[100.6, 3.0]]
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && ../.venv/bin/python -m pytest apps/market/test_depth.py -q`
Expected: FAIL（`build_depth_payload` 不存在）

- [ ] **Step 3: consumers.py 加纯函数 + DepthConsumer**

在 `consumers.py` 顶部（MarketConsumer 之后）加：

```python
def build_depth_payload(symbol, row):
    """把 OKX books5 的一档数据转成前端消息。row: {"bids":[[px,sz,..],..],"asks":[...]}"""
    def _levels(side):
        return [[float(x[0]), float(x[1])] for x in (row.get(side) or [])]

    return json.dumps(
        {"type": "depth", "symbol": symbol, "bids": _levels("bids"), "asks": _levels("asks")}
    )


class DepthConsumer(AsyncWebsocketConsumer):
    """前端连 /ws/depth/{symbol};直连 OKX 公共 WS 订阅 books5 转发买卖五档。"""

    async def connect(self):
        self.symbol = self.scope["url_route"]["kwargs"]["symbol"]
        await self.accept()
        self._closing = False
        self._task = asyncio.create_task(self._run_okx())

    async def _run_okx(self):
        from okx.websocket.WsPublicAsync import WsPublicAsync

        url = settings.OKX_PUBLIC_WS_SIM
        loop = asyncio.get_running_loop()

        def on_message(raw):
            try:
                msg = json.loads(raw)
            except (ValueError, TypeError):
                return
            data = msg.get("data")
            if not data:
                return
            symbol = msg.get("arg", {}).get("instId", self.symbol)
            payload = build_depth_payload(symbol, data[0])
            asyncio.run_coroutine_threadsafe(self.send(text_data=payload), loop)

        backoff = 1
        while not self._closing:
            try:
                ws = WsPublicAsync(url=url)
                self._ws = ws
                await ws.start()
                await ws.subscribe(
                    [{"channel": "books5", "instId": self.symbol}], callback=on_message
                )
                backoff = 1
                while not self._closing:
                    await asyncio.sleep(30)
            except asyncio.CancelledError:
                break
            except Exception:  # noqa
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

    async def disconnect(self, code):
        self._closing = True
        task = getattr(self, "_task", None)
        if task:
            task.cancel()
        ws = getattr(self, "_ws", None)
        if ws:
            try:
                await ws.close()
            except Exception:  # noqa
                pass

    async def receive(self, text_data=None, bytes_data=None):
        pass
```

`ws_routing.py`：import `DepthConsumer`，加 `re_path(r"^ws/depth/(?P<symbol>[\w-]+)$", DepthConsumer.as_asgi())`。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && ../.venv/bin/python -m pytest apps/market/ -q`
Expected: PASS（含新 depth 测试，且 market 现有测试不回归）

---

### Task 2: Pinia terminal store

**Files:**
- Create: `frontend/src/stores/terminal.ts`

**Interfaces:**
- Produces: `useTerminal()` — state `symbol`(default "BTC-USDT")、`env`("sim")、`instType`("SPOT")、`bar`("1m")；actions `setSymbol/setEnv/setInstType/setBar`。

- [ ] **Step 1: 实现 store**

```typescript
import { defineStore } from "pinia";

export const useTerminal = defineStore("terminal", {
  state: () => ({
    symbol: "BTC-USDT",
    env: "sim" as "sim" | "live",
    instType: "SPOT",
    bar: "1m",
  }),
  actions: {
    setSymbol(s: string) { this.symbol = s; },
    setEnv(e: "sim" | "live") { this.env = e; },
    setInstType(t: string) { this.instType = t; },
    setBar(b: string) { this.bar = b; },
  },
});
```

- [ ] **Step 2: 检查点**

Run: `test -f frontend/src/stores/terminal.ts && echo OK`
Expected: `OK`（build 在 Task 8 统一验证）

---

### Task 3: SymbolList.vue（左栏币种列）

**Files:**
- Create: `frontend/src/components/SymbolList.vue`

**Interfaces:**
- Consumes: `/api/market/symbols`（raw fetch 或 client）、terminal store。
- Produces: 组件，列出 symbol + 最新价（初始拉一次，可后续接 px WS）；搜索框过滤；点击 `terminal.setSymbol`；自选存 localStorage。

- [ ] **Step 1: 实现（含搜索/自选/点击联动）**

（完整组件：`onMounted` fetch `/api/market/symbols` 得 symbol 列表；`search` ref 过滤；`favorites` 从 localStorage；点击行调 `terminal.setSymbol(sym)`;当前 symbol 高亮。Glass 样式。）

- [ ] **Step 2: 检查点**

Run: `test -f frontend/src/components/SymbolList.vue && echo OK`
Expected: `OK`

---

### Task 4: CandleChart 指标叠加 + IndicatorPanel

**Files:**
- Modify: `frontend/src/components/CandleChart.vue`
- Create: `frontend/src/components/IndicatorPanel.vue`

**Interfaces:**
- Produces: CandleChart 接受 `indicators: string[]` prop（如 `["ma7","ma25","ema12","boll"]`），history 加载后在同图叠加 LineSeries（前端计算 MA/EMA/布林；MACD 用副图或省略首轮，首轮做 MA/EMA/布林三类线叠加）。IndicatorPanel 是开关工具条，`v-model` 绑定选中指标数组。

- [ ] **Step 1: CandleChart 加 indicators prop + 叠加线**

在 CandleChart 加 prop `indicators?: string[]`；`loadHistory` 拿到 candles 后，对每个选中指标计算数值并 `chart.addSeries(LineSeries, {...})` 叠加（收盘价序列算 MA/EMA/布林上中下轨）。管理叠加 series 的增删（indicators 变化时重建）。

- [ ] **Step 2: IndicatorPanel.vue**

一排开关按钮（MA7/MA25/EMA12/BOLL），点击 toggle，emit `update:modelValue` 数组。Glass 样式。

- [ ] **Step 3: 检查点**

Run: `test -f frontend/src/components/IndicatorPanel.vue && grep -n "indicators" frontend/src/components/CandleChart.vue`
Expected: 命中。

---

### Task 5: OrderBook.vue（深度盘口）

**Files:**
- Create: `frontend/src/components/OrderBook.vue`

**Interfaces:**
- Consumes: `/ws/depth/{symbol}`、terminal store。
- Produces: 订阅 depth WS，渲染卖档（上，红）+ 买档（下，绿），每档 price/size + 累计量背景色条；symbol 变化重连。

- [ ] **Step 1: 实现（WS 订阅 + 买卖档渲染 + 累计量条）**

（`watch` terminal.symbol 重连 `${proto}://${location.host}/ws/depth/${symbol}`；on message type=="depth" 更新 bids/asks；模板渲染 asks 倒序 + bids；累计量算百分比做背景宽度。onBeforeUnmount 关 WS。Glass 样式。）

- [ ] **Step 2: 检查点**

Run: `test -f frontend/src/components/OrderBook.vue && echo OK`
Expected: `OK`

---

### Task 6: Terminal.vue 三栏主页面

**Files:**
- Create: `frontend/src/views/Terminal.vue`

**Interfaces:**
- Consumes: terminal store、SymbolList、CandleChart、IndicatorPanel、OrderBook、tradingApi（搬 Trade.vue 下单/仓位/委托/成交历史逻辑）。

- [ ] **Step 1: 实现三栏布局**

- 顶栏：品类页签（SPOT/SWAP/FUTURES/OPTION/ETF）绑 `terminal.instType`；env 切换绑 `terminal.env`；报价栏（最新价，来自 px WS）。
- 左栏：`<SymbolList />`。
- 中栏：周期切换 + `<IndicatorPanel v-model="indicators" />` + `<CandleChart :symbol="t.symbol" :bar="t.bar" :indicators="indicators" />`；下方页签容器（持仓|委托|成交历史|深度）。
  - 持仓：仓位表 + 平仓（搬 `closePos`）。
  - 委托：当前委托 + 撤单（搬 `cancel`）。
  - 成交历史：渲染 `trades` 表（补现状缺失）。
  - 深度：`<OrderBook />`。
- 右栏：下单面板（搬 Trade.vue 的 form/submit/doPlaceOrder/杠杆/止盈止损/凭证/live 确认）。
- 逻辑搬运：`loadCredentials/refreshAll/submit/doPlaceOrder/cancel/closePos/openTradeWs/openPxWs` 等，symbol/env/instType 改读 terminal store（watch store 变化触发 refreshAll/openPxWs/loadMaxLever）。

（完整文件很长，实现时以 Trade.vue 为蓝本，三栏 Grid 布局重排。）

- [ ] **Step 2: 检查点**

Run: `test -f frontend/src/views/Terminal.vue && echo OK`
Expected: `OK`

---

### Task 7: 路由合并 + 侧边栏 + 删旧页

**Files:**
- Modify: `frontend/src/router/index.ts`、`frontend/src/layouts/GlassLayout.vue`
- Delete: `frontend/src/views/Market.vue`、`frontend/src/views/Trade.vue`

**Interfaces:**
- Produces: `/trade` → Terminal.vue；`/market`、`/market/:symbol` 重定向到 `/trade`；侧边栏「行情」「交易」合并为「交易终端」。

- [ ] **Step 1: router**

```typescript
        { path: "trade", component: () => import("@/views/Terminal.vue") },
        { path: "market/:symbol", redirect: "/trade" },
        { path: "market", redirect: "/trade" },
```

（移除原 Market.vue/Trade.vue 引用。）

- [ ] **Step 2: 侧边栏合并**

`navItems` 把 market + trade 两条合并为一条 `{ path: "/trade", key: "nav.terminal" }`。`isActive` 相应调整（/trade 与 /market 都归到该项）。

- [ ] **Step 3: 删除旧文件**

删除 `frontend/src/views/Market.vue`、`frontend/src/views/Trade.vue`（确认无其它 import 引用：`grep -rn "views/Market\|views/Trade" frontend/src`，应仅剩已改的 router）。

- [ ] **Step 4: 检查点**

Run: `grep -rn "views/Market\|views/Trade\b" frontend/src/router; ls frontend/src/views/Terminal.vue`
Expected: router 无旧引用（trade 指向 Terminal），Terminal 存在。

---

### Task 8: i18n + 前端 build

**Files:**
- Modify: `frontend/src/i18n/zh-CN.ts` / `en-US.ts`

**Interfaces:**
- Produces: `nav.terminal`、`terminal.*`（币种列/指标/盘口/页签标题/报价），zh/en 对齐。

- [ ] **Step 1: 加 key（zh + en 对齐）**

`nav.terminal`：中「交易终端」/ 英「Terminal」。`terminal` 分组：`symbols/search/favorites/depth/positions/orders/trades/indicators/quote/high/low/vol24h` 等，两语言对齐。（复用现有 market/trade key 减少重复。）

- [ ] **Step 2: build 通过**

Run: `cd frontend && npm run build`
Expected: 构建成功（Market.vue/Trade.vue 已删，无悬空引用）。

- [ ] **Step 3: key 对齐校验**

Run: 比对 `terminal` 分组两文件 key 集合一致。
Expected: 一致。

---

## Self-Review

**Spec coverage：** E spec E1(三栏布局)→Task6；E2(左栏币种)→Task3；E3(K线+指标)→Task4；E4(下方页签+成交历史补渲染)→Task6；E5(右栏下单)→Task6；E6(depth WS)→Task1；E7(路由/侧边栏/删旧/i18n)→Task7+8。验收 1(切币联动)→Task2+6；2(六品类下单等价)→Task6；3(成交历史)→Task6；4(指标)→Task4；5(盘口)→Task1+5;6(主题/语言)→Task8;7(重定向+build)→Task7+8。

**Placeholder scan：** 前端组件(Task3/5/6)说明结构与蓝本(Trade.vue/MarketConsumer),实现时写完整代码。后端 Task1 有完整代码。

**Type consistency：** `build_depth_payload(symbol,row)->str`(Task1)→ DepthConsumer 使用一致；terminal store `symbol/env/instType/bar`(Task2)→ Task3/5/6 读写一致；`indicators` prop(Task4)→ Task6 传递一致；depth 消息 `{type,symbol,bids,asks}`(Task1)→ OrderBook(Task5) 消费一致。

## 说明
E 以前端为主,UI 正确性无法在本环境跑浏览器验证——build 通过 + 结构检查为自动化底线,交互(切币联动/下单/盘口/指标/主题语言)需你在真实环境点测。

## Execution Handoff
计划保存至 `docs/superpowers/plans/2026-08-12-quanly-E-trade-terminal.md`,当前会话逐 task 执行。
