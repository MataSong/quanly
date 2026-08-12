# 子项目 A — 策略启动故障修复

日期：2026-08-12
父设计：`2026-08-12-quanly-strategy-page-overhaul-overview.md`
优先级：最高（C/D 均依赖策略能稳定启动）
状态：待复审

## 目标

修复 Docker 环境下策略任务「创建后无法正常启动运行」，使策略可正常
创建 → 启动 → 运行 → 输出日志。修完即可网页端验证。

## 根因分析（基于当前代码）

### 根因 1：卷名 / 网络名硬编码假设 compose 项目名为 `quanly`
- `backend/apps/strategy/tasks.py:55` 挂载卷写死 `"quanly_strategy_scripts"`。
- `docker-compose.yml:21` `STRATEGY_DOCKER_NETWORK: quanly_default`。
- compose 默认给卷/网络加**项目名前缀**（项目名默认取部署目录名，或被 `-p` 覆盖）。
  若真实项目名 ≠ `quanly`，实际卷名是 `<项目名>_strategy_scripts`、网络是 `<项目名>_default`，
  `containers.run` 报 `no such volume` / `network not found` → 启动失败。

### 根因 2：strategy-runner 镜像不在 compose 内
- 镜像靠 `deploy/deploy.sh` 的 `build_strategy_runner()` 单独 `docker build -t quanly-strategy-runner`。
- 换机器 / 首次 / 漏构建 → `containers.run(settings.STRATEGY_RUNNER_IMAGE)` 找不到镜像 →
  ImageNotFound → 启动即失败（对应历史 commit「避免启动策略 404」）。

### 根因 3：worker 阻塞式日志采集占满并发槽
- `tasks.py:76` `for line in container.logs(stream=True, follow=True)` 阻塞到容器退出。
- 一个 `run_strategy_task` 占用一个 worker 并发槽直到策略停止。默认 worker 并发有限，
  跑几个长期策略后槽位耗尽，后续 `run_strategy_task` 永久排队 → 表现为「点了启动没反应」。

### 附带问题：启动失败对用户不可见
- `run_strategy`（views.py:39）只在 celery 派发异常时返回错误；容器层失败（卷/网络/镜像）
  发生在 worker 内，仅写一条 error 日志，前端无明确提示。

## 修复方案

### 修 1：动态解析 compose 项目名（tasks.py）
- 新增 `_compose_project()`：worker 启动时读自身容器信息拿
  label `com.docker.compose.project`（用 docker SDK：`client.containers.get(socket.gethostname())`
  或读 `/proc/self/cgroup` 兜底），得到真实项目名 `proj`。
- 卷名 = `f"{proj}_strategy_scripts"`，网络名 = `f"{proj}_default"`。
- 结果缓存到模块级变量，避免每次 run 重复解析。
- 解析失败兜底：回退到环境变量 `STRATEGY_DOCKER_NETWORK` / 约定卷名，并写警告日志。

### 修 2：runner 镜像纳入 compose 构建
- `docker-compose.yml` 新增一次性构建服务 `strategy-runner-build`（或用 profile）：
  `build: ./strategy-runner`、`image: quanly-strategy-runner`、`command: ["true"]`、
  不加入 `depends_on` 常驻链路，仅确保 `compose build` / `up --build` 时镜像被构建。
- `deploy/deploy.sh`：保留 `build_strategy_runner()` 作兜底，但主链路改由 compose 保证。
- `settings.STRATEGY_RUNNER_IMAGE` 保持 `quanly-strategy-runner` 不变。

### 修 3：拆分启动与日志采集，解除 worker 阻塞
- `run_strategy_task`：起容器 → 写 `container_id`、置 `RUNNING` → **立即返回**（不再 follow 日志）。
- 日志采集改由 **strategy-runner 容器主动上报**：runner 的 `ctx.log()` 已 POST 到
  `/api/strategy-api/log`（runner_api 已落库 + redis publish）。因此容器内 `print` → stdout
  的旁路采集不再是唯一来源；**将日志采集职责收敛到 runner 主动上报**，worker 不再 attach。
  - 对于只 `print` 不调用 `ctx.log()` 的脚本：在 runner `main()` 里把 stdout 重定向/包装，
    使 `print` 也走一次 `ctx.log()` 上报（保证「输出日志」需求不丢）。
- 结果：`run_strategy_task` 秒级返回，worker 槽立即释放，可并发启动多策略（支撑子项目 C 批量）。

### 修 4：启动前置校验 + 明确报错（views.py + tasks.py）
- `run_strategy` 派发前轻量校验：credential（若传）归属、symbol 非空、interval 合理。
- `run_strategy_task` 内 `containers.run` 用 try/except 分类捕获
  （ImageNotFound / 卷 / 网络 / 其他），写**带类型的 error 日志**并置 `status=error`。
- 前端 StrategyDetail / 任务面板轮询 run 状态，error 时展示该日志（i18n key）。

## 涉及文件
- `backend/apps/strategy/tasks.py`（修 1/3/4，主改）
- `docker-compose.yml`（修 2：新增 runner 构建服务）
- `deploy/deploy.sh`（修 2：兜底保留）
- `strategy-runner/runner.py`（修 3：print → 上报包装）
- `backend/apps/strategy/views.py`（修 4：前置校验/报错）
- i18n：`frontend/src/i18n/zh-CN.ts` / `en-US.ts`（strategy 启动报错 key，对齐）

## 不改动（保护边界）
- OKX 适配器层、虚实盘 `env` 隔离、回测引擎、runner_api 鉴权模型：均不动。
- StrategyRun/Strategy/StrategyLog 表结构本子项目不动（`last_heartbeat` 留给子项目 B）。

## 验收标准（网页可测）
1. 用非 `quanly` 名的 compose 项目名部署，点击启动内置策略 → 容器成功起、状态转 RUNNING。
2. 首次部署（未手动 build runner）→ 启动策略不再 ImageNotFound。
3. 连续启动 5+ 个策略实例 → 全部进入 RUNNING（worker 不再卡队列）。
4. 策略日志实时流出现在前端终端框（print 与 ctx.log 都可见）。
5. 故意用不存在的镜像名 → 前端显示明确 i18n 报错，而非静默无反应。
6. 后端 pytest 全绿；OKX/虚实盘/回测相关测试不回归。

## 测试
- 单测：`_compose_project()` 解析（mock docker client label）、卷/网络名拼接、
  `containers.run` 异常分类映射到 error 日志。
- 沿用 TDD：先写失败测试，再实现。
