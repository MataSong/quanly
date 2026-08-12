# 子项目 B — 部署升级不中断 + 策略进程保活

日期：2026-08-12
父设计：`2026-08-12-quanly-strategy-page-overhaul-overview.md`
优先级：高（与 A 同属基础设施救火线，A 之后做）
状态：待复审

## 目标

保障策略进程 7×24 不间断：celery-worker/backend 重启、项目部署升级重建容器时，
正在运行的策略进程**零中断**；容器/进程意外退出可自动恢复。

## 现状问题（基于当前代码）

1. **策略容器无重启策略**：`tasks.py:43` `containers.run` 未设 `restart_policy`，
   宿主 docker 重启或容器 OOM 后不会自动拉起。
2. **无重启恢复逻辑**：`apps/strategy/apps.py` 是空 AppConfig，worker 重启后不会重扫
   DB 中 `RUNNING` 的 run，孤儿容器与 DB 状态脱节。
3. **部署升级重建 worker**：`deploy/deploy.sh:96` `BACKEND_SERVICES` 含 `celery-worker`，
   `hot_update()` 会 recreate 它。当前 worker 阻塞式采集（A 修前）一断，日志/状态全丢。
4. **无健康判断字段**：无法区分「容器还活着」与「容器已死但 DB 仍 RUNNING」。

## 修复方案

### B1：策略容器自治（tasks.py）
- `containers.run` 增加 `restart_policy={"Name": "unless-stopped"}`。
  容器脱离 worker 独立存活；worker 崩溃/重建期间容器照常运行。
- 依赖 A 的修 3（worker 不再阻塞 attach），二者配合容器才能真正自治。

### B2：新增健康心跳字段（models.py + 迁移）
- `StrategyRun` 增 `last_heartbeat = DateTimeField(null=True, blank=True)`。
- runner 容器每次 `ctx.log()` / 每轮 tick 后，经 `/api/strategy-api/heartbeat`
  更新对应 run 的 `last_heartbeat`（runner_api 新增轻量端点，RUN_TOKEN 鉴权）。
- 用途：重扫时判断容器是否「活着且健康」。

### B3：worker 启动重扫恢复（新 management command + worker ready 钩子）
- 新增 `apps/strategy/recover.py`：`recover_running_runs()`
  1. 查所有 `status=RUNNING` 的 StrategyRun。
  2. 用 docker SDK 查容器 `quanly-strategy-{run_id}` 是否存在且 running：
     - 存在且 running → 保持 RUNNING（容器自治，无需动作）。
     - **不存在 / 已退出 → 自动重拉**同参数容器（复用 `run_strategy_task` 的启动逻辑），
       写恢复日志。
- 触发时机：Celery `worker_ready` 信号 连 `recover_running_runs()`；
  同时提供 `python manage.py recover_strategies` 手动命令（便于运维/测试）。
- 幂等：重扫可重复执行，已 running 的不重复起。

### B4：部署升级不碰策略容器（deploy.sh）
- 策略容器命名 `quanly-strategy-*`，**不在 compose services 内**，`compose up --build`
  天然不会 recreate 它们 → 升级时策略容器零中断（真零中断已满足）。
- `hot_update()` 重建 `celery-worker` 后，worker 启动即触发 B3 重扫：
  - 升级期间容器一直活着 → 重扫发现 running，仅重新对齐状态，不重启策略。
- 显式在 deploy.sh 注释说明：策略容器不受升级影响；仅无状态服务被重建。
- 校验：`hot_update()` 结束后打印当前 `quanly-strategy-*` 容器数，供运维确认未丢。

## 涉及文件
- `backend/apps/strategy/tasks.py`（B1 restart_policy；B3 复用启动逻辑）
- `backend/apps/strategy/models.py` + 新迁移（B2 last_heartbeat）
- `backend/apps/strategy/runner_api.py`（B2 heartbeat 端点）
- `backend/apps/strategy/urls.py`（B2 路由 `strategy-api/heartbeat`）
- `strategy-runner/runner.py`（B2 每轮上报心跳）
- `backend/apps/strategy/recover.py`（B3 新增）
- `backend/apps/strategy/apps.py` 或 `config/celery.py`（B3 worker_ready 信号）
- `backend/apps/strategy/management/commands/recover_strategies.py`（B3 手动命令）
- `deploy/deploy.sh`（B4 注释 + 升级后策略容器计数）

## 不改动（保护边界）
- OKX 适配器、虚实盘 env、回测引擎、runner_api 鉴权模型不动。
- 不引入 supervisor / 常驻进程（保持 DooD 隔离契约）。

## 验收标准（网页可测）
1. 启动一个策略 → `docker restart celery-worker` → 策略容器仍在跑，worker 重扫后
   前端状态仍 RUNNING、日志继续流。
2. 启动策略 → 执行 `./quanly deploy`（热更新）→ 全程 `quanly-strategy-*` 容器不消失、
   不重启（容器 uptime 连续），升级后前端仍显示运行中、日志不断。
3. 启动策略 → 手动 `docker kill quanly-strategy-{id}` 模拟意外 → worker 重扫（或手动
   `recover_strategies`）→ 容器被自动重拉、状态回 RUNNING。
4. `last_heartbeat` 随 tick 更新，前端任务面板可显示「最近心跳」。
5. 后端 pytest 全绿，无回归。

## 测试
- 单测：`recover_running_runs()` 三分支（活着/已死重拉/不存在重拉），mock docker client。
- 单测：heartbeat 端点更新字段、RUN_TOKEN 鉴权。
- TDD：先写失败测试再实现。
