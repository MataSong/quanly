# Quanly 加密量化交易平台 — 系统设计文档

> 日期:2026-08-09
> 技术栈:Python Django(后端)+ Vue 3(前端)+ OKX V5 官方 SDK
> 交付策略:**骨架优先 + 纵深主线**,每一层网页端可真实测试

---

## 0. 核心决策速览(恢复会话先读这里)

| 维度 | 决策 |
|------|------|
| OKX 接入 | 官方 `python-okx` SDK,严禁手写 HTTP。模拟盘/实盘**都对接 OKX 官方接口**,靠 `flag`('1'=demo,'0'=live)+ 不同 API key 区分。**不自建撮合引擎**。 |
| 环境隔离 | `env` = SIM / LIVE,贯穿密钥、数据表、Celery 队列、适配器 flag。 |
| 用户体系 | 多用户,完整注册/登录/权限 + 多租户数据隔离。 |
| 策略运行 | 所有策略(内置示例 + 用户上传)统一走**独立 Docker 容器隔离**(Docker-out-of-Docker,worker 挂 docker.sock 动态 run)。 |
| 数据库 | PostgreSQL(业务)+ InfluxDB(K线/Tick)+ Redis(缓存/broker/WS/限流)。 |
| Celery | 三队列:backtest_q / sim_strategy_q / live_strategy_q。 |
| 前端 | Vue3+Vite+TS+Pinia+vue-i18n;毛玻璃 UI(Apple/Ghostty);TradingView Lightweight Charts;中英双语;深浅双主题。 |
| 全品类交付契约 | **后端首轮全品类覆盖;前端交易页按品类顺序逐个可测交付,最终全覆盖。** |
| Git | 本项目不执行任何 git 操作。 |

---

## 1. 整体分层架构

```
┌─────────────────────────────────────────────────────────────┐
│  Vue 前端(毛玻璃终端)  Nginx 静态托管                          │
│  路由/双语/主题 · Lightweight Charts · Pinia · WS 客户端       │
└───────────────┬─────────────────────────────┬───────────────┘
                │ HTTPS REST(JWT)             │ WSS
┌───────────────▼─────────────────────────────▼───────────────┐
│  Django 网关层(前端只连这里,绝不直连 OKX)                     │
│  DRF ViewSet · SimpleJWT 鉴权 · Channels(WS)· 限流/权限       │
├───────────────────────────────────────────────────────────────┤
│  领域业务层(与交易所无关)                                       │
│  账户/资产聚合 · 订单编排 · 策略托管 · 回测 · 账单归档            │
├───────────────────────────────────────────────────────────────┤
│  ★ 交易所抽象层(核心解耦点)                                    │
│  ExchangeAdapter 抽象接口(所有品类方法签名与交易所无关)         │
│  OKXAdapter(实现类)── 内部调 python-okx SDK,屏蔽 SDK 细节     │
│  未来:BinanceAdapter / BybitAdapter 只新增实现类,上层不改      │
├───────────────────────────────────────────────────────────────┤
│  Celery 异步层(三隔离队列)                                     │
│  backtest_q · sim_strategy_q · live_strategy_q                 │
│  + beat 定时:资产同步/账单归档/行情落库                         │
│  策略执行 → Docker-out-of-Docker 动态起隔离容器                 │
├───────────────────────────────────────────────────────────────┤
│  数据层                                                         │
│  PostgreSQL(业务)· InfluxDB(K线/Tick)· Redis(缓存/broker/WS)│
└───────────────────────────────────────────────────────────────┘
```

**数据流 · 实时行情**:OKX WS → Celery 行情采集 → 写 InfluxDB + 发 Redis 频道 → Django Channels 订阅 Redis → 推前端 WS → Lightweight Charts 刷新。

**数据流 · 下单**:前端 → DRF → 订单编排层 → `adapter.place_order(env=sim/live)` → OKXAdapter 调 SDK(带对应 flag)→ 回包落 PostgreSQL → WS 推订单状态。

---

## 2. 交易所抽象层(核心解耦点)

**抽象接口 `ExchangeAdapter`**(纯抽象基类,方法签名与交易所无关,使用平台标准数据结构):

```python
class ExchangeAdapter(ABC):
    def __init__(self, credential: Credential, env: Env): ...   # env=SIM/LIVE

    # 公共行情(无需密钥)
    def get_candles(symbol, timeframe, ...) -> list[Candle]
    def get_ticker(symbol) -> Ticker
    def get_orderbook(symbol, depth) -> OrderBook
    async def stream_market(symbols, channels) -> AsyncIterator[MarketEvent]

    # 交易(全品类统一签名)
    def place_order(req: OrderRequest) -> Order
    def cancel_order(order_id) -> Order
    def amend_order(...) -> Order
    def close_position(...) -> Order
    def set_tp_sl(...) -> Order

    # 账户/资产
    def get_balances() -> list[Balance]
    def get_positions() -> list[Position]
    def get_bills(...) -> list[Bill]

    # 资金/理财/借贷(全品类)
    def transfer(...) / get_savings(...) / subscribe_earn(...) / get_loan(...) ...
```

**设计原则**
- 上层业务只依赖 `ExchangeAdapter` 抽象类型,拿到的永远是平台标准结构(`Order`/`Balance`/`Position`…),看不到 OKX 原始 JSON。
- `OKXAdapter` 内部把 SDK 的 `Trade`/`Account`/`Funding`/`PublicData`/`MarketData`/`Finance` 模块调用**翻译**成标准结构;`instType`/`tdMode`/`posSide` 等 OKX 专有概念在适配器内部消化。
- **工厂 + 注册表**:`AdapterFactory.create(exchange='okx', env, credential)`。新增交易所 = 写一个实现类注册进去,上层零改动。
- **能力声明**:`adapter.supports(Capability.OPTIONS)`,前端据此显示/隐藏品类页签。
- `flag` 在构造时按 `env` 注入(SIM→'1',LIVE→'0'),一处控制。
- SDK 报错统一翻译成平台标准异常(`ExchangeError` 子类:限流/鉴权/余额不足/参数错),上层只 catch 标准异常。

---

## 3. PostgreSQL 核心数据表设计

所有交易数据带 `env`(SIM/LIVE)物理隔离,所有业务数据带 `user` 多租户隔离。

**用户/权限**:`User`(邮箱、双语偏好、主题偏好)、`UserProfile`、`Role`、`Permission`。

**密钥**:`ExchangeCredential`(user_fk、exchange、env、api_key_enc、secret_enc、passphrase_enc 全 Fernet 加密、permissions、label;唯一约束 (user,exchange,env,label);前端仅回显 api_key 后四位,secret/passphrase 永不返回)。

**交易**(带 env+user):
- `Order`:本地/交易所订单号、inst_type(现货/杠杆/永续/交割/期权)、方向、类型、价格、数量、td_mode、状态、成交均价/量、时间戳
- `Trade`:成交明细
- `Position`:方向、开仓均价、杠杆、保证金、未实现盈亏、强平价
- `AlgoOrder`:止盈止损/条件单

**资产**(带 env+user):
- `AssetSnapshot`:定时快照,总净值、按品类聚合、浮盈、冻结、可用
- `Balance`:分币种余额
- `Bill`:账单/资金流水归档

**策略**(带 env+user):
- `Strategy`:名称、脚本引用、语言、入参 schema、状态、运行环境、关联密钥
- `StrategyRun`:运行实例、容器 ID、启停时间、状态、资源用量
- `StrategyLog`:关键事件日志
- `StrategyPnl`:盈亏时序快照

**回测**(带 user):
- `Backtest`:标的、周期、初始资金、风控参数、状态
- `BacktestResult`:收益曲线引用、最大回撤、胜率、夏普、总收益
- `BacktestTrade`:模拟成交明细

**时序数据**:K线/Tick 存 InfluxDB(measurement 按 symbol+timeframe,tag=symbol/exchange,field=ohlcv),不进 PostgreSQL。

---

## 4. 隔离 / 沙箱 / 回测 / 调度

**虚实盘隔离**:①密钥独立 ②数据表 env 字段强制过滤 ③Celery 队列物理分开 ④适配器 flag。策略切换环境 = 换 StrategyRun + 换队列 + 换密钥。LIVE 下单前端二次确认 + 后端权限校验。

**策略沙箱(D-a)**:worker 通过挂载的 docker.sock 动态 `docker run` `strategy-runner` 容器。约束:网络白名单(只能访问后端网关,策略碰不到真实密钥,下单走后端鉴权代理)、memory/cpus 限额、read-only 根 fs、cap-drop ALL、无 docker.sock、超时 kill。日志经 stdout→采集→Redis→WS 推前端。内置示例与用户脚本走相同路径。

**回测引擎**:事件驱动。从 InfluxDB 拉历史 K 线逐 bar 喂策略 → 模拟成交器(滑点/手续费)→ 记 BacktestTrade。跑在 backtest_q,复用 strategy-runner 注入回测数据源。绩效指标:总收益率、年化、最大回撤、胜率、夏普、盈亏比、交易次数。

**Celery**:三队列(backtest_q CPU 密集 / sim_strategy_q / live_strategy_q 隔离)。Beat:资产快照同步、账单归档、行情落库健康检查。常驻:OKX WS 行情采集进程。

---

## 5. 前端(Vue 毛玻璃终端)

**技术栈**:Vue3 + Vite + TS + Pinia + Vue Router + vue-i18n + Lightweight Charts + 原生 WS。

**路由/页面**
```
/login /register              登录注册
/dashboard                    统一资产总看板
/market/:symbol               行情盯盘(K线+深度+Ticker,WS 实时)
/trade                        一体化交易操作台(按品类页签)
                              现货/永续/交割/期权/杠杆·ETF;下单/撤单/止盈止损/一键平仓/加减仓
/strategies                   策略托管中心(列表/上传/启停/环境切换)
/strategies/:id               策略详情:盯盘控制台(状态/日志流/持仓/盈亏走势)
/backtest                     回测控制台(参数 + 收益曲线/回撤/指标)
/finance                      理财/借贷/Staking/双币
/assets/bills                 账单与资金流水归档
/settings/keys                API 密钥管理
/settings                     语言/主题/账户
```

**组件拆分**
- 布局:GlassLayout / GlassPanel / GlassModal
- 图表:CandleChart(封装 Lightweight Charts+WS)/ DepthChart / PnlChart
- 策略编辑器:StrategyEditor / LogStream
- 回测控制台:BacktestConfigForm / PerformanceReport
- 资金订单:OrderForm(按品类动态表单)/ OrderTable / PositionTable / AssetSummaryCards

**毛玻璃**:`backdrop-filter: blur(20px) saturate(180%)` + rgba 半透明 + 柔和边框 + 悬浮阴影;CSS 变量 + `data-theme` 双主题,偏好存 localStorage。用 frontend-design + dataviz skill 保证视觉一致。

**双语**:vue-i18n,zh-CN / en-US 全覆盖(导航/表单/指标/弹窗/报错/回测标签),偏好存 localStorage。

**实时通讯**:所有请求走 Django 网关(不直连 OKX);WS 三类订阅——行情、策略日志、资金/仓位。

---

## 6. 安全风控 + Docker 部署

**安全风控**
- 密钥加密:Fernet,密钥来自环境变量 `SECRET_ENCRYPTION_KEY`;secret/passphrase 永不返回前端。
- 策略沙箱:见第 4 段。
- 爆仓预警:Beat 周期算保证金率,逼近强平价 → WS 推警告(阈值可配)。
- 并发订单冲突:DB 行锁 + 状态机(pending→live→filled/canceled)+ 幂等键(client_order_id)。
- 资金一致性:下单前校验本地余额快照 + OKX 回包为准;定时对账 AssetSnapshot vs OKX 实际,偏差告警。
- 接口限流:DRF throttle + Redis 令牌桶(公共/交易分级);适配器层对 OKX 限流防频控封禁。

**Docker(测试/生产共用一套,靠 .env 区分)**
```
nginx            反代 + Vue 静态 + WS 转发
backend          Django(gunicorn)
ws               Channels(daphne)
celery-beat      定时调度
celery-backtest  worker → backtest_q
celery-sim       worker → sim_strategy_q   ┐挂 docker.sock
celery-live      worker → live_strategy_q  ┘动态起策略容器
market-collector OKX WS 行情采集常驻
postgres / influxdb / redis   持久化数据卷
strategy-runner  策略容器镜像(被动态 run)
```
- Dockerfile:后端(多阶段,清华镜像)/ 前端(多阶段 build→nginx)/ strategy-runner(精简 Python + quanly-strategy 库)。
- 环境区分:`.env.test` / `.env.prod`,只改环境变量,镜像本体不变。
- 持久化:postgres/influxdb/redis 数据 + 用户策略文件挂 named volume。
- 一键启动:`docker compose --env-file .env.test up -d`。

---

## 7. 首期迭代优先级排期

```
P0 骨架:Docker 全家桶起得来 + 注册登录 + 密钥管理 + 适配器抽象层 + OKXAdapter 骨架
P1 行情:OKX WS 采集 → InfluxDB → Channels → 前端 K 线实时
P2 交易:现货下单/撤单/止盈止损/平仓(能成交)→ 永续合约
P3 资产:全品类资产看板 + 账单流水归档
P4 策略:托管中心 + 容器化运行 + 实时盯盘控制台
P5 回测:回测引擎 + 绩效报告
P6 补全:交割/期权/杠杆ETF/理财/借贷/Staking/划转 逐品类前端
P7 风控打磨:爆仓预警/对账/限流/双语与主题收尾
```
