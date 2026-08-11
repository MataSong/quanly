# Quanly P1 行情主线 — 设计文档

> 日期:2026-08-09
> 依赖:P0 骨架已完成(Django 分层 + 适配器层 + Docker 全家桶)
> 目标:OKX 公共行情实时打通到前端 K 线图,每一步网页可测

---

## 0. 范围与决策(已敲定)

- **数据源 = OKX 公共行情**,免 API key(K线/Ticker 均公开);demo/live 同一套公共数据。
- **实时性**:后端常驻进程连 OKX 公共 WS,订阅实时 K线 + Ticker,写 InfluxDB + 转发前端。
- **交易对**:首期固定 BTC-USDT / ETH-USDT / SOL-USDT,后续再做用户自选。
- **图表**:前端 TradingView Lightweight Charts。
- 技术实锤(已侦察):`okx.websocket.WsPublicAsync(url)` → `start()` → `subscribe([{"channel":"candle1m","instId":"BTC-USDT"}], callback)`;历史 K 线 `MarketData.MarketAPI(flag).get_candlesticks(instId, bar, limit)`。

---

## 1. 数据流

```
OKX 公共 WS ──► market-collector 常驻进程(asyncio)
                   │  ├─ 写 InfluxDB(measurement=candle, tag=symbol/bar, field=ohlcv)
                   │  └─ 发布 Redis 频道 market:{symbol}:{bar}
                   ▼
         Django Channels Consumer(订阅 Redis 频道)
                   │  WSS /ws/market/{symbol}
                   ▼
         前端 CandleChart(Lightweight Charts)
            ├─ 初次:REST 拉历史 K 线铺底
            └─ 之后:WS 增量更新最后一根 K 线 + 最新价
```

- **历史 K 线**(铺底):前端进页面先调 `GET /api/market/{symbol}/candles?bar=1m&limit=200`,后端经 OKXAdapter.get_candles 拉 OKX 历史。
- **实时**:collector 收到 WS 推送 → 发 Redis → Channels 推前端 → 图表更新最后一根。

---

## 2. 后端改动

**2.1 适配器层**:实现 `OKXAdapter.get_candles(symbol, timeframe, limit)`(P0 是 NotImplementedError),调 `MarketAPI.get_candlesticks`,返回 `list[Candle]`(标准结构,时间升序)。加 `get_ticker` 已有。新增 mapping:OKX 的 timeframe 记法(如 `1m`/`1H`)与平台标准对齐。

**2.2 行情 REST**:新 app `apps.market`。
- `GET /api/market/symbols` → 返回支持的交易对列表(固定三个)。
- `GET /api/market/{symbol}/candles?bar=1m&limit=200` → 历史 K 线(标准结构 JSON)。
- 公共行情**允许匿名访问**(AllowAny),不需登录。

**2.3 InfluxDB 写入**:`apps.market.storage`,封装 influxdb-client 写 candle point(measurement=`candle`,tag=`symbol`,`bar`,field=`o/h/l/c/v`,time=K线时间)。环境变量读 INFLUX_URL/TOKEN/ORG/BUCKET。

**2.4 market-collector 常驻进程**:`apps.market.collector`,Django management command `run_collector`。asyncio 连 OKX 公共 WS,订阅三对的 `candle1m` + `tickers`,回调里:①写 InfluxDB ②`redis.publish("market:{symbol}:{bar}", json)`。断线自动重连。

**2.5 Channels WS**:`config.asgi` 接入 ProtocolTypeRouter;`apps.market.consumers.MarketConsumer`:客户端连 `/ws/market/{symbol}`,consumer 订阅 Redis 频道 `market:{symbol}:*`,收到消息推给前端。用 channels-redis 做 channel layer。

**2.6 依赖**:channels、channels-redis、daphne(P0 已装 channels/daphne,补 channels-redis)。

---

## 3. 前端改动

**3.1 依赖**:`lightweight-charts`。

**3.2 组件 `CandleChart.vue`**:封装 Lightweight Charts,props=symbol/bar。mounted 时:①REST 拉历史铺底 ②开 WS `/ws/market/{symbol}` 订阅增量,`series.update()` 刷新最后一根。unmounted 关 WS。

**3.3 页面 `/market/:symbol`(Market.vue)**:顶部交易对切换 + 最新价 + 涨跌;主体 CandleChart。默认 BTC-USDT。

**3.4 路由 + 导航**:GlassLayout 侧边栏加"行情"入口;路由加 `/market/:symbol`(默认重定向 `/market/BTC-USDT`)。

**3.5 i18n**:行情页文案 zh/en。

---

## 4. Docker 编排改动

- 新增 **ws 服务**(daphne 跑 asgi,端口 8001)+ **market-collector 服务**(跑 `python manage.py run_collector`)。
- nginx.conf 取消 `/ws/` 反代注释,指向 ws:8001。
- 新增环境变量:INFLUX_URL=http://influxdb:8086、INFLUX_TOKEN、INFLUX_ORG=quanly、INFLUX_BUCKET=market、REDIS_URL=redis://redis:6379/0。
- InfluxDB 需要一个初始 token:compose 里给 influxdb 设 `DOCKER_INFLUXDB_INIT_ADMIN_TOKEN`,后端用同一个。

---

## 5. 验收(网页可测)

1. `GET /api/market/BTC-USDT/candles` 返回真实历史 K 线 JSON。
2. 打开 `/market/BTC-USDT`,看到真实 K 线图铺底。
3. collector 运行时,图表最后一根 K 线 + 最新价随 OKX 实时跳动(WS 生效)。
4. 切换到 ETH/SOL 正常。
5. InfluxDB 里能查到写入的 candle 数据。

---

## 6. 不在 P1 范围

用户自选交易对、深度图(orderbook)、多周期切换 UI(先固定 1m,接口支持 bar 参数)、下单(P2)。
