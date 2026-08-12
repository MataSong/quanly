# Quanly 页面重构 + 策略改版 + 保活升级 — 总览设计

日期：2026-08-12
状态：总览已批准，逐子项目 spec 待展开

## 背景

Quanly 已完成主线 P0–P8（骨架/行情/交易/资产/策略容器/回测/全品类/风控/真实 OKX 对接）。
本轮需求是在既有代码上做四类改造，本质是 **5 个相互独立的子系统**，各自独立
spec → plan → 实现 → 网页可测，符合既定「骨架优先 + 纵深主线、每层可测」交付契约。

## 现状关键发现

- 策略模型已是「模板 Strategy / 运行实例 StrategyRun / 日志 StrategyLog」雏形，一份模板
  已可跑多个 Run。缺：批量多标的并行编排、可视化配置模式、运行中任务总览面板。
- 前端行情页 `Market.vue` 当前**无深度盘口、无指标工具、无独立报价栏**；交易页 `Trade.vue`
  成交历史已加载数据但未渲染表格。
- 策略启动故障根因（3 个）与保活缺失已定位（见子项目 A/B）。

## 5 个子项目与依赖顺序

```
基础设施救火线(先做)            策略体验线(依赖救火稳定)         页面线(可并行)
A 策略启动故障修复  ──┐          C 策略架构改版             E 行情交易一体化页面
B 部署升级保活      ──┴────────▶ D 策略双模式创建
```

落地顺序：**A → B → C → D**，**E 独立可与 C/D 并行**。
A 修完即可立刻验证「策略起得来」，不必等全部完成。

## 各子项目设计要点

### A 策略启动故障修复（最高优先）
根因与修法：
1. **卷名/网络硬编码假设项目名 `quanly`**（`tasks.py:55` `quanly_strategy_scripts`、
   compose `STRATEGY_DOCKER_NETWORK: quanly_default`）。修：worker 启动时读自身容器
   label `com.docker.compose.project` **动态解析真实项目名**，拼正确卷名/网络名。
2. **strategy-runner 镜像不在 compose 里**，靠 deploy.sh 单独 build，漏构建即 404。
   修：镜像纳入 compose build（init/profile 服务，不常驻），随全家桶一起构建。
3. **worker 阻塞式日志采集占满并发槽**（`container.logs(follow=True)` 阻塞到容器退出）。
   修：启动 task 起容器即返回；日志采集改由独立常驻采集器/异步 attach，不占调度槽。
- 附带：`run_strategy` 视图加启动前置校验（镜像/卷/脚本可写），失败给明确 i18n 报错。

### B 部署升级不中断 + 保活（真零中断）
1. **策略容器自治**：`containers.run` 加 `restart_policy={"Name":"unless-stopped"}`。
2. **worker/backend 重启重扫恢复**：启动钩子扫 DB 中 `status=RUNNING` 的 run →
   容器活着重新 attach 日志；**容器已死则自动重拉同参数容器**。
3. **部署升级只重建无状态服务**：`hot_update()` 改为
   `compose up -d --no-deps --build backend ws worker beat frontend nginx`，
   显式不碰策略容器（本就不在 compose services 内，天然不受 recreate 影响）。
- 数据：StrategyRun 现有 `container_id/status/run_token` 已够恢复；补 `last_heartbeat` 做健康判断。

### C 策略模板库 / 任务执行面板 拆分 + 批量并行
- 模型演进（不推倒）：`Strategy` 加 `mode(code/visual)`、`visual_config(JSON)`、
  `params_schema`、`description`；`StrategyRun` 加 `batch_id`（同批共享）。
- 批量：一模板 → 多选 N 标的 → 生成 N 个 StrategyRun（共享 batch_id）→ 起 N 容器（**一标的一容器**）。
- API 两组：模板管理（CRUD/preview/参数预设）；任务执行（batch-run / tasks 总览按 batch 分组 /
  batch-stop / 单 run 启停）。
- 前端拆两页：策略模板库 `/strategies/templates`、任务执行面板 `/strategies/tasks`
  （运行中任务总览：进程/日志/实时盈亏/启停，按 batch 分组）。

### D 策略双模式创建（产物统一入模板库）
- **可视化模式**：表单配置 → 存 `visual_config` JSON → 后端 **Jinja2** 把参数填入策略骨架
  生成完整 `on_tick(ctx)` Python 源码写入 `Strategy.source`。首轮内置 4 类骨架：
  **均线交叉 / 网格交易 / 定投 DCA / 止盈止损**。可预览、可「转代码模式」手改。
- **专业代码模式**：**CodeMirror 6** 在线 Python 编辑器，语法校验 + 预运行调试（复用回测引擎）。
- 两模式产物都是 `Strategy` 记录，统一进模板库、统一被任务面板调用；**共用同一 `on_tick(ctx)`
  接口与容器执行路径**，不需第二套执行引擎，不破坏沙箱。

### E 行情交易一体化页面
- 新建单页 `/trade`（**合并替换**旧 /market + /trade），三栏专业量化终端布局：
  - 顶栏：品类页签 + 环境(sim/live) + 独立实时报价栏（新建）。
  - 左栏：币种列（搜索/自选/涨跌幅，复用 `/market/symbols` + 现货报价，新建）。
  - 中栏：K 线大区（复用 `CandleChart.vue` + 周期切换）+ **指标工具**（MA/EMA/MACD/布林，
    前端叠加计算）+ 下方页签（持仓/委托/**成交历史(补渲染)**/**深度盘口**）。
  - 右栏：下单面板固定（搬 Trade.vue 下单/杠杆/止盈止损/凭证逻辑）。
- 后端新增：`/ws/depth/{symbol}` 深度盘口 WS 频道 + mock/OKX depth 源。
- 全区块共享 symbol/env 状态（Pinia），切币种全栏联动、无跳转。

## 贯穿全部的约束
- 不破坏 OKX 适配器层 / 虚实盘 `env` 隔离 / 回测引擎。
- 适配现有 docker-compose 一键部署，改后打包重启生效。
- 所有新增文案走 i18n（zh-CN / en-US 完全对齐）。
- 前端统一 Glass 毛玻璃 + 深浅双主题。

## 已锁定决策清单
- 保活：策略容器自治（restart_policy）+ worker 重扫恢复；部署升级容器全程不停（真零中断）。
- A 卷名/网络：动态解析 compose 项目名。
- 容器死后：自动重拉。
- 批量并行：一标的一容器。
- 可视化落地：表单 → Jinja2 生成 Python 源码。
- 可视化内置模板：均线交叉 / 网格 / DCA / 止盈止损。
- 代码编辑器：CodeMirror 6。
- E 范围：全部补齐（盘口 + 指标 + 报价）。
- E 布局：左币种 | 中 K 线+持仓 | 右下单。
- E 旧页：合并替换旧两页。

## 下一步
按 A → B → C → D（+ E 并行）逐个展开独立 spec → plan → 实现 → 可测。
