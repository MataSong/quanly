# 用户自写策略 + 提交检测 + 运行时隔离 设计文档

**日期**: 2026-08-19
**范围**: 策略新增支持两种来源——点击式内置模板(扩模板库) + 用户上传 Python 脚本;脚本提交三层检测(语法/AST安全/试运行);用户代码执行走「容器+AST审查+网络隔离」;runner API 版本化冻结保证重构升级不打断运行中的策略。全程 PC/手机响应式 + 中英文 + 零 mock。
**明确不做(后续/独立)**: gVisor/Firecracker 强沙箱、可视化拖拽策略构建器、付费/订阅授权、真实盘 PnL 收益率。

## 背景与目标

策略商城第一版只支持"参数化内置模板实例"(点击选模板+调参,不写代码)。本次补齐开放平台核心:
1. **点击式基础策略**:在现有"选内置模板+调参"基础上,**扩充内置模板库**(RSI 超买超卖/MACD/布林带/网格等大众策略)。
2. **用户自写 Python 脚本**:用户上传任意 Python 策略代码,提交时经**语法+AST安全+试运行**三层检测。
3. **运行时隔离**:系统热更新(重建 backend/nginx/worker)不影响运行中的用户策略容器(**现状已天然满足**——容器是 docker SDK 裸起、不属 compose);项目重构升级也不打断——**通过 runner API 版本化冻结**保证。

已确认决策:
- 简单(点击式)和复杂(脚本)策略都走「**容器 + AST 审查 + 网络隔离**」安全方案。
- 点击式 = 多加内置模板供选 + 调参(复用现有机制)。
- 提交检测三层:语法 + AST 安全 + 试运行(**同步 + 合成 K 线**,即时反馈)。
- runner API 版本化冻结(/runner/v1/*)。
- runner 镜像装 numpy + pandas(量化策略常用)。

## 架构决策

1. **策略来源三分类**(Strategy.source_type):`builtin`(官方内置,owner=None) / `template`(点击式:内置模板+参数) / `code`(用户上传 Python)。前两者跑内置代码,`code` 跑用户代码。
2. **检测与审核两个独立维度**:`check_status`(pending/passed/failed,技术能否跑)+ `status`(draft/pending/approved/rejected,管理员准否上架)。检测通过才能提交审核;审核通过才上商城。
3. **双重代码安全**:提交期 AST 静态审查(黑名单 import/危险调用/dunder 穿透 + 必须有 on_tick + 白名单库)+ 运行期网络隔离(专用 Docker network 只通 backend,即使 AST 漏网也出不去)。
4. **试运行复用回测引擎**:改造 engine `_load_on_tick` 支持从代码字符串受控 exec;喂合成 K 线跑 on_tick 验证不抛异常+能出信号。同步执行(合成数据快)。
5. **runner API v1 冻结**:/api/strategy/runner/v1/{candles,order,log},契约固化只增不改;运行中旧容器打 v1 端点,后端永远保留 → 重构不打断。

## 数据模型(`backend/core/strategy/models.py`)

Strategy 现有:name/source_type(builtin|uploaded)/code_ref/default_params/is_builtin/owner/template_ref/params/visibility/status/description/reject_reason/updated_at。

**改动**:
- `source_type` choices 加 `code`(保留 builtin;`uploaded` 语义即 template,可加常量别名 `SOURCE_TEMPLATE="uploaded"` 保持数据兼容不改历史值,或迁移改名——**采用保留 uploaded 值,代码里语义视作 template**,避免数据迁移;新增 `SOURCE_CODE="code"`)。
- `code = models.TextField(blank=True, default="")` — 用户 Python 源码(仅 source_type=code)。
- `check_status = models.CharField(max_length=16, choices=[(pending),(passed),(failed)], default="pending")`。
- `check_report = models.JSONField(default=dict)` — 三层检测详情。
- migration。

## 提交检测(`backend/core/strategy/validation.py` 新建,纯函数可单测)

三层,依次执行,任一层失败即返回该层错误:

1. **语法层**:`compile(code, "<strategy>", "exec")` 捕 SyntaxError → {line, msg}。
2. **AST 安全审查**(`ast.parse` 遍历):
   - 禁 import 黑名单:os/sys/subprocess/socket/shutil/importlib/ctypes/multiprocessing/threading/pathlib/pickle 等(触系统/触网/开进程/序列化)。
   - 禁危险调用:eval/exec/compile/__import__/open/globals/locals/vars/getattr(动态)/setattr/delattr。
   - 禁 dunder 穿透:__builtins__/__subclasses__/__globals__/__class__/__bases__/__mro__。
   - 白名单 import:math/statistics/json/datetime/decimal + numpy/pandas(镜像装了)。非白名单 import → 违规。
   - 必须定义顶层 `on_tick(ctx, params)` 函数(签名校验)。
   - 命中 → {violations: [{line, rule, detail}]}。
3. **试运行层**(复用回测引擎):
   - engine `_load_on_tick` 改造支持代码字符串:受控 exec(`__builtins__` 限为安全子集,与 runner 一致)取 on_tick。
   - 喂合成 K 线(如 150 根构造的有涨跌趋势序列,复用 test_backtest 的 `_build_crossover_candles` 风格)跑 on_tick 若干 tick。
   - 断言:不抛异常;ctx 方法被正常调用;(记录)是否产出至少一次 buy/sell 信号。
   - 抛异常 → {tick, exception};正常 → {ok, signal_count}。
- `validate_strategy_code(code) -> {check_status, check_report}`:三层组合,report 含每层结果。

## 后端 API(`views.py`/`urls.py`)

- `StrategyCreateView` 扩展:body 加 `source_type`(template|code)、`code`(code 类型必填)。code 类型:同步跑 `validate_strategy_code` → 写 check_status/check_report;**check 失败可以保存为 draft 但不能提交审核**(check_status 必须 passed 才能 submit)。
- `POST /api/strategy/strategies/<id>/check`(strategy:update):对已存策略重跑检测(改代码后)。
- `StrategySubmitView` 增校验:source_type=code 且 check_status != passed → 400。
- **runner API 版本化**:新增 `/api/strategy/runner/v1/candles|order|log`(RunTokenAuthentication,契约同现有);现有无版本 `/runner/*` 保留为 v1 别名(向后兼容运行中旧容器)。契约文档 `docs/superpowers/runner-api-v1-contract.md`(冻结,只增不改)。
- **serializer**:code 字段——他人策略(非 owner)不暴露 code(知识产权);owner 和 detail 可见(公开策略 code 是否暴露给使用者?**决策:公开策略 code 对使用者可见**——开放平台鼓励学习,与 params 可见一致;私有仅 owner)。

## runner 执行用户代码(`strategy-runner/`)

- `runner.py` `load_on_tick`:env 有 `USER_CODE` → 受控 exec(限制 __builtins__ 安全子集)取 on_tick;否则走 CODE_REF 内置分支(现状)。打 **v1** 端点(`/api/strategy/runner/v1/*`)。
- `Dockerfile`:装 numpy + pandas(pip,清华源不通用 PyPI 官方源,参照 backend Dockerfile 教训)。
- `tasks.py` 容器加固增强:
  - code 类型注入 `USER_CODE=strategy.code`。
  - **网络隔离**:策略容器接专用 Docker network(internal,不通外网),仅能访问 backend(backend 也接该 network,或该 network 桥接 backend)。禁访问 postgres/redis/其他容器/外网。
  - 加 `pids_limit`(如 128,防 fork 炸弹)。
  - 保留现有 cap_drop=ALL/read_only/no-new-privileges/mem/cpu/非root/tmpfs。
  - CODE_REF/USER_CODE 二选一,BACKEND_URL 指向 v1(或 runner.py 自己拼 /v1)。

## 内置模板库扩充

新增内置策略(RSI/MACD/布林带/网格中先做 2-3 个),每个走注册流程。**改进**:把当前分散的注册点(runner load_on_tick 硬编码、engine _BUILTIN_MAP、Dockerfile COPY)尽量收敛——runner 侧可改为遍历 builtin/ 目录动态注册(减少硬编码分支),engine 侧 _BUILTIN_MAP 可扫描目录。**本次范围**:先加 RSI + MACD 两个内置(证明扩充流程),注册点收敛为可选优化。每个内置:backend builtin/<x>.py + runner builtin/<x>.py 副本 + Dockerfile COPY + DB seed(owner=None/approved/public)。

## 前端(`MyStrategies.vue` 扩展 + 响应式 + i18n)

- "新建策略"对话框加**来源 tab/radio**:`点击式模板` / `Python 脚本`。
  - 点击式:现有流程(选内置模板+动态参数表单),模板库扩后自动多选项。
  - Python 脚本:代码编辑框(textarea 或轻量 code editor)+ on_tick 契约说明/示例模板 + "检测"按钮 → 调 check API → 展示 check_report(三层结果:语法/AST违规项/试运行信号数)。**检测 passed 才能保存提交**。
- 我的策略列表加 `check_status` 列(着色 pending灰/passed绿/failed红)+ 查看 check_report。
- 详情/编辑:code 策略显示代码(owner/公开可见)。
- 全响应式(useBreakpoint/ResponsiveTable/mixins,dialog 手机92%,代码框手机可用)+ i18n zh/en 新增 key(source类型/检测/AST违规/试运行/契约说明等)。
- api/strategy.ts:createStrategy 支持 source_type/code;新增 checkStrategy(id 或 code)。

## 错误处理

- 检测失败:check_status=failed + check_report 详情(哪层/行号/违规规则/异常);前端展示,不能提交审核。
- AST 命中黑名单:返回具体违规项(行号+规则),用户可改。
- 试运行抛异常:返回哪个 tick 抛什么异常。
- 运行期用户代码抛异常:runner 现有 consecutive_errors 机制(连续5次退出),不影响其他容器。
- 网络隔离下用户代码触网:被 Docker network 拦(连不上除 backend 外任何地址)。
- backend 重建期间:运行中容器 v1 端点回调重试(现有指数退避),v1 契约不变故恢复后继续。

## 验证

1. **后端 pytest**:validation 三层纯函数(语法错/AST黑名单各项/白名单放行/无on_tick/试运行跑通与抛异常);create code 策略写 check_status;check API;submit 要求 check passed;runner v1 端点(candles/order/log 契约同旧);他人 code 不暴露(私有)/公开可见;新内置 RSI/MACD engine 跑通。OKX/docker 打桩。
2. **前端 build**:vue-tsc + vite。
3. **AST 安全实测**:提交含 `import os`/`eval`/`__subclasses__` 的代码 → 检测 failed 返回违规项;正常 dual_ma 风格代码 → passed。
4. **试运行实测**:提交能跑通的 on_tick → passed + signal_count;提交 on_tick 里除零/未定义变量 → failed + 异常 tick。
5. **网络隔离实测(需真环境)**:用户代码尝试 `requests.get(外网)` 被拦(容器只通 backend);正常 ctx.candles/buy/sell(经 backend v1)通。
6. **runner v1 冻结**:运行中容器打 /runner/v1/* 通;无版本 /runner/* 别名仍通(旧容器兼容)。
7. **隔离/热更新实测**:起一个用户策略容器 → `deploy.sh update` 重建 backend → 容器不被杀、v1 回调恢复后继续跑。
8. **回归**:现有 template 策略/内置 dual_ma/回测/资产不破。
9. Docker 重建(backend+worker+nginx)+ 重建 quanly-strategy-runner 镜像(装 numpy/pandas)后端到端验收。

## 后续(独立 spec)

- gVisor/Firecracker 强沙箱(比 AST+网络隔离更强的内核级隔离)。
- 可视化拖拽策略构建器(条件组合生成策略)。
- 策略付费/订阅授权中间表;真实盘 PnL 收益率。
- 内置注册点完全收敛(目录自动扫描注册,消除所有硬编码分支)。
