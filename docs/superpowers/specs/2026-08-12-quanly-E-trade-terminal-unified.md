# 子项目 E — 行情交易一体化页面

日期：2026-08-12
父设计：`2026-08-12-quanly-strategy-page-overhaul-overview.md`
优先级：独立（可与 C/D 并行；纯前端 + 少量后端 WS）
状态：待复审

## 目标

合并现有独立的行情页(`/market`)与交易页(`/trade`)为**单一一体化主页面**，
专业量化终端三栏布局，看盘 + 交易一体、无需跳转，功能完整保留并补齐缺失项。

## 现状（基于当前代码）

- `Market.vue`：仅 K 线(`CandleChart.vue`) + 周期切换 + 顶栏最新价。
  **无深度盘口、无指标工具、无独立报价栏**。
- `Trade.vue`：单文件含 品类页签/环境切换/下单面板/杠杆/止盈止损/仓位+平仓/余额/
  委托+撤单；**成交历史 trades 已加载但模板未渲染表格**。
- WS 三路：`/ws/market/{symbol}`、`/ws/trade/{uid}/{env}`、`/ws/strategy/{runId}`。
  **无深度盘口 WS**。
- lightweight-charts v5、全自研 Glass 组件、Pinia、i18n、data-theme 深浅主题。

## 设计

### E1：三栏布局主页面（新建 `views/Terminal.vue`，替换 /market + /trade）
```
顶栏: 品类页签(SPOT/SWAP/FUTURES/OPTION/MARGIN/ETF) + 环境(sim/live) + 报价栏
┌──────────┬─────────────────────────────────┬──────────────────┐
│ 左:币种列 │ 中: K线大区(周期切换 + 指标工具)      │ 右: 下单面板(固定) │
│  搜索/自选│    下方页签: 持仓|委托|成交历史|深度   │                  │
└──────────┴─────────────────────────────────┴──────────────────┘
```
- 全区块共享 symbol / env / instType 状态：新增 Pinia store `terminal.ts`，
  切币种/品类全栏联动，无跳转。

### E2：左栏币种列（新建组件 SymbolList.vue）
- 复用 `/market/symbols`（按 instType 过滤）+ 现货报价，列出 symbol / 最新价 / 24h 涨跌%。
- 搜索框过滤；自选（localStorage 收藏）；点击切 store.symbol → 全栏刷新。

### E3：中栏 K 线 + 指标工具
- 复用现有 `CandleChart.vue`（周期切换保留）。
- **新增指标工具**（IndicatorPanel + 在 CandleChart 叠加）：MA / EMA / MACD / 布林带，
  纯前端基于已拉取 K 线计算，用 lightweight-charts 叠加 Line/Histogram series。
  指标开关工具条，可多选叠加。
- 下方页签容器：持仓 | 委托 | **成交历史** | 深度盘口。

### E4：下方页签（搬 Trade.vue 区块 + 补齐）
- **持仓**：仓位表 + 平仓（搬现有 closePosition）。
- **委托**：当前委托 + 撤单（搬现有）。
- **成交历史**：**补渲染**现有已加载的 trades（现状缺表格）。
- **深度盘口**：新建 OrderBook.vue，订阅新 depth WS，买卖档位 + 累计量色条。

### E5：右栏下单面板（搬 Trade.vue 下单逻辑，固定不滚动）
- 凭证选择、限价/市价、买卖、数量/价格、杠杆滑块(SWAP/FUTURES)、
  止盈止损、期权行权价/到期、live 二次确认。逻辑整体迁移，样式适配右栏固定卡片。

### E6：后端深度盘口 WS（新增）
- 新增 depth 数据源：mock 模式在 collector 里按最新价生成买卖档（随机游走 spread），
  publish 到 redis 频道 `depth:{symbol}`；okx 模式订阅 OKX 公共 depth（books5）。
- 新增 `DepthConsumer`（channels，`/ws/depth/{symbol}`），订阅 redis 转发前端。
- `MARKET_FEED` okx/mock 分流，与现有行情源一致。

### E7：路由 / 侧边栏 / i18n
- 新路由 `/terminal`（或复用 `/trade` 路径指向 Terminal.vue）；`/market`、`/market/:symbol`、
  旧 `/trade` 重定向到一体化页。侧边栏「行情」「交易」两项合并为一项「交易终端」。
- 旧 `Market.vue` / `Trade.vue` 删除（合并替换）；`CandleChart.vue` 保留复用。
- i18n：新增 `terminal.*`（币种列/指标/盘口/页签标题等），复用现 market/trade key，
  zh-CN / en-US 对齐。

## 涉及文件
- `frontend/src/views/Terminal.vue`（E1 新增，主页面）
- `frontend/src/components/SymbolList.vue`、`IndicatorPanel.vue`、`OrderBook.vue`（新增）
- `frontend/src/components/CandleChart.vue`（E3 叠加指标）
- `frontend/src/stores/terminal.ts`（E1 新增共享状态）
- `frontend/src/router/index.ts` + `GlassLayout.vue`（E7）
- 删除 `frontend/src/views/Market.vue`、`Trade.vue`（E7）
- `backend/apps/market/`（E6 depth 源 + mock）、`consumers.py`（DepthConsumer）、
  `ws_routing`（/ws/depth）
- `nginx/nginx.conf`（若 depth 走同 /ws 前缀则无需改，确认即可）
- `frontend/src/i18n/zh-CN.ts` / `en-US.ts`（E7）

## 不改动（保护边界）
- trading REST/engine、OKX 适配器、虚实盘 env、风控、回测均不动（仅前端重组 + 新增 depth WS）。

## 验收标准（网页可测）
1. 一体化页：切换币种，左栏/K线/报价/下单/持仓全栏联动，无跳转。
2. 六大品类页签均可切换，下单/杠杆/止盈止损/平仓/委托/撤单功能与旧页等价无缺失。
3. 成交历史表格正确渲染（修复现状缺失）。
4. 指标工具 MA/EMA/MACD/布林 可叠加显示。
5. 深度盘口实时更新（mock 与 okx 两源）。
6. 深浅主题、中英文切换全页正确；Glass 毛玻璃风格统一。
7. 旧 /market /trade 访问重定向到一体化页；前端 build 通过。

## 测试
- 前端 build 通过；关键交互浏览器实测（切币联动、下单、盘口、指标、主题/语言切换）。
- 后端：DepthConsumer / mock depth 源单测；pytest 全绿。
