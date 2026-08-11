# Quanly P4 策略系统 — 设计文档

> 日期:2026-08-09;依赖 P0-P3。目标:策略托管中心 + Docker 容器隔离运行,网页可测。

## 决策(已敲定)
- 直接上 **Docker-out-of-Docker(D-a)**:celery worker 挂宿主机 `/var/run/docker.sock`,为每个策略运行动态 `docker run` 一个隔离容器。
- **轮询型**执行模型。
- **文件式 + 填空式统一容器运行**:runner 检测用户脚本——有 `on_tick(ctx)` 则 runner 负责轮询循环;否则直接执行脚本并注入 `quanly` SDK。
- **安全核心**:策略容器**拿不到真实 API key**。策略通过后端"策略专用 API"(带 run-token)拿行情、下单;下单经后端鉴权代理,用 order 关联的 credential(P2b)去撮合。
- 容器约束:`--network` 限内网只能访问后端、`--memory`/`--cpus` 限额、`--cap-drop ALL`、`--read-only`、无 docker.sock、超时 kill。

## 架构 / 数据流
```
前端 策略中心 ──REST──► Strategy/StrategyRun 表
   启动 ──► Celery live_strategy_q 任务 ──► docker run strategy-runner 容器
                                              │(env: RUN_TOKEN, RUN_ID, BACKEND_URL)
   strategy-runner:
     - 加载用户脚本(检测 on_tick / 主循环)
     - 每 tick 调 quanly SDK → 后端 /api/strategy-api/*（带 RUN_TOKEN）
        · GET price / positions / balances
        · POST order（后端校验 token→找到 run→用其 credential+env 走撮合）
     - stdout 日志 → docker logs → celery 采集 → redis → WS 推前端
   停止 ──► docker stop / kill
```

## 后端
### 模型 apps.strategy
- `Strategy`(user):name、language(python)、source(脚本文本)、kind(builtin/uploaded)、created_at。
- `StrategyRun`(user):strategy_fk、env(sim/live)、credential_fk(用哪套 key)、symbol、interval_sec、status(pending/running/stopped/error)、container_id、run_token(唯一,随机)、started_at、stopped_at。
- `StrategyLog`(run_fk):level、message、ts(也可只 redis,DB 存关键)。

### 策略专用 API `apps.strategy.runner_api`(用 RUN_TOKEN 鉴权,非 JWT)
- `GET /api/strategy-api/market?symbol=` → 最新价(读 redis lastpx)。
- `GET /api/strategy-api/positions` / `/balances` → 该 run 的 user+env 持仓/余额。
- `POST /api/strategy-api/order` → 下单:校验 token→取 run→用 run.credential+env 建 Order 走 engine.place。
- token 校验:查 StrategyRun.run_token 且 status=running。

### 管理 API `apps.strategy.views`(JWT)
- CRUD `Strategy`;`POST /api/strategies/{id}/run`(body: env, credential_id, symbol, interval)→建 StrategyRun + 发 celery 任务;`POST /api/strategy-runs/{id}/stop`;`GET /api/strategy-runs`、`GET /api/strategy-runs/{id}/logs`。

### Celery
- 新增 celery app(config/celery.py),broker=redis。
- 任务 `run_strategy(run_id)`(live_strategy_q / sim_strategy_q 按 env):docker run strategy-runner,传 env vars;轮询容器状态;采集 logs → redis 频道 `strategy:{run_id}` → WS。
- 任务 `stop_strategy(run_id)`:docker stop。
- 服务:celery-worker(挂 docker.sock)、celery-beat(P4 可不用)。

## strategy-runner 镜像(新目录 strategy-runner/)
- 精简 python + `quanly` SDK(封装 strategy-api 调用:ctx.price/buy/sell/position/balance/log)。
- entrypoint:读 env(RUN_TOKEN/RUN_ID/BACKEND_URL/SYMBOL/INTERVAL/USER_SCRIPT_PATH),加载脚本;有 on_tick→循环调;否则 exec 脚本注入 ctx。
- 用户脚本通过 volume 或环境传入(P4:后端把 source 写入挂载卷,容器读)。

## 前端 策略中心
- `/strategies` 列表:内置示例(均线/网格)+ 用户策略;新建/编辑(代码编辑器 textarea 起步)、删除。
- `/strategies/:id` 详情:启动配置(env/密钥/交易对/间隔)、启停按钮、运行状态、**实时日志流(WS)**、该 run 的持仓/盈亏。
- 侧边栏加"策略"入口;i18n。

## Docker 编排
- 新增 celery-worker 服务(build backend,command celery worker,挂 `/var/run/docker.sock:/var/run/docker.sock`,加入 compose 网络)。
- strategy-runner 镜像随 compose build(或首次 worker 内 build);容器 run 时 `--network quanly_default` 连回 backend。
- 环境:CELERY_BROKER_URL=redis://redis:6379/0、BACKEND_INTERNAL_URL=http://backend:8000。

## 验收(网页可测,mock 撮合)
1. 策略中心看到内置均线/网格示例。
2. 选 env+密钥+交易对+间隔,启动 → 状态 running,日志流实时刷出。
3. 策略自动下单(经 strategy-api)→ 交易页/资产看板能看到它产生的订单/持仓。
4. 停止 → 容器 kill、状态 stopped。
5. 上传一个自定义 on_tick 脚本能跑;上传一个带主循环的脚本也能跑。
6. 安全:策略容器内无法读到真实 secret(只有 run_token)。

## 不在 P4 范围
策略回测(P5);多策略并发资源调度上限(后续);策略市场/分享。
