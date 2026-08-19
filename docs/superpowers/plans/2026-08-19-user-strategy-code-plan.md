# 用户自写策略 + 提交检测 + 运行时隔离 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development 逐任务执行。步骤用 checkbox 追踪。

**Goal:** 策略新增支持点击式内置模板(扩库) + 用户上传 Python 脚本;脚本提交经语法+AST安全+试运行三层检测;用户代码执行走容器+AST审查+网络隔离;runner API v1 版本化冻结保证重构不打断运行中策略。全程响应式+中英文+零 mock。

**Architecture:** Strategy 加 source_type=code/code/check_status/check_report;validation.py 三层检测(语法compile+AST黑白名单+复用回测引擎受控exec试运行合成K线);runner load_on_tick 支持 USER_CODE 受控exec,打v1端点;tasks 网络隔离(专用internal network只通backend)+pids_limit+USER_CODE注入;runner API 加v1前缀+旧路径别名+契约文档;扩内置RSI/MACD;前端来源tab(模板/脚本)+代码框+检测。

**Tech Stack:** Django5+DRF+Celery+Docker SDK;strategy-runner(python:3.12-slim+numpy+pandas);Vue3+TS+ElementPlus。

## Global Constraints

- **代码安全双重**:AST 静态审查(提交期,黑名单import/危险调用/dunder穿透+必须on_tick+白名单库) + 网络隔离(运行期,专用Docker network只通backend)。
- **检测/审核两维度**:check_status(pending/passed/failed技术能否跑) 独立于 status(审核)。code策略 check必须passed才能submit审核。
- **runner API v1 冻结**:/api/strategy/runner/v1/* 契约只增不改;旧无版本路径保留为v1别名(兼容运行中旧容器);契约文档。
- **零 mock**:试运行用合成K线(验证逻辑,非真实行情,合理);运行/回测真连OKX。
- **多租户/隔离**:mine/CRUD限owner;他人私有code不暴露,公开策略code可见(学习);密钥永不进容器(仅RUN_TOKEN)。
- **PC不退化+手机响应式+i18n zh/en对齐**。
- 本地commit不push;精确git add;每步pytest/build过。
- BASE=当前HEAD(6235237)。

## File Structure

**后端**
- `core/strategy/models.py`(改) — source_type加code常量+code/check_status/check_report字段+migration。
- `core/strategy/validation.py`(新) — 三层检测纯函数。
- `core/strategy/safe_exec.py`(新) — 受控exec(限制__builtins__安全子集,runner与试运行共用逻辑参照)。
- `core/backtest/engine.py`(改) — _load_on_tick支持代码字符串受控exec(用于试运行)。
- `core/strategy/views.py`(改) — create支持source_type/code+同步检测;check端点;submit校验check_status;serializer code脱敏;runner视图加v1路由。
- `core/strategy/urls.py`(改) — runner v1路由+旧别名+check端点。
- `core/strategy/tasks.py`(改) — USER_CODE注入+网络隔离+pids_limit。
- `core/strategy/builtin/{rsi,macd}.py`(新) — 内置策略。
- `tests/test_strategy_validation.py`(新)、扩test_strategy_marketplace/test_backtest。

**runner**
- `strategy-runner/runner.py`(改) — load_on_tick支持USER_CODE受控exec;端点改v1。
- `strategy-runner/Dockerfile`(改) — 装numpy+pandas;COPY新内置。
- `strategy-runner/builtin/{rsi,macd}.py`(新) — backend副本。

**前端**
- `frontend/src/views/strategy/MyStrategies.vue`(改) — 来源tab(模板/脚本)+代码框+检测按钮+check_status列。
- `frontend/src/api/strategy.ts`(改) — createStrategy支持source_type/code+checkStrategy。
- `frontend/src/locales/{zh-CN,en-US}.ts`(改)。

**文档**
- `docs/superpowers/runner-api-v1-contract.md`(新) — v1契约冻结。

---

## Task 1: 模型扩展 + migration

**Files:** `models.py`(改)+migration。

- [ ] Step1: Strategy 加 `SOURCE_CODE="code"` 到 source_type choices(保留 builtin/uploaded);加字段 `code=TextField(blank,default="")`、`check_status=CharField(choices pending/passed/failed,default="pending")`、`check_report=JSONField(default=dict)`。常量 CHECK_PENDING/PASSED/FAILED。
- [ ] Step2: makemigrations core_strategy + migrate(用 POSTGRES_PORT=5433 export env,QUANLY_CREDENTIALS_ENC_KEY 用 export 避免 idna)。
- [ ] Step3: 跑 test_strategy 回归。Commit `feat(usercode): 模型加 source_type=code+code+check_status+check_report`。

---

## Task 2: AST 安全审查 + 受控 exec(纯函数,可单测)

**Files:** `core/strategy/safe_exec.py`(新)、`core/strategy/validation.py`(新,先做语法+AST层)、`tests/test_strategy_validation.py`(新)。

**Interfaces:**
- Produces: `safe_exec.build_safe_builtins() -> dict`(安全 __builtins__ 子集:abs/min/max/len/range/sum/round/sorted/enumerate/zip/float/int/str/list/dict/tuple/bool/print等,禁 open/eval/exec/__import__/globals);`safe_exec.exec_strategy(code) -> on_tick`(受控 exec 取 on_tick,__builtins__限安全子集)。
- `validation.check_syntax(code) -> {ok, error?}`;`validation.check_ast(code) -> {ok, violations}`(黑名单import/危险调用/dunder/白名单/必须on_tick)。

- [ ] Step1: 写 safe_exec(build_safe_builtins + exec_strategy受控exec,白名单import在exec层也拦——通过限制__builtins__.__import__为白名单校验版)。
- [ ] Step2: 写 validation 语法层(compile捕SyntaxError)+AST层(ast.parse遍历:Import/ImportFrom黑名单+白名单math/statistics/json/datetime/decimal/numpy/pandas;Call黑名单eval/exec/open等;Attribute黑名单__subclasses__/__globals__等dunder;顶层FunctionDef须含on_tick且参数(ctx,params))。
- [ ] Step3: 测试:import os/socket→违规;eval/__subclasses__→违规;白名单numpy放行;无on_tick→违规;正常dual_ma风格→通过。语法错→报行号。
- [ ] Step4: pytest过。Commit `feat(usercode): AST安全审查+受控exec(safe_exec+validation语法/AST层)`。

---

## Task 3: 试运行层(复用回测引擎)

**Files:** `core/backtest/engine.py`(改)、`core/strategy/validation.py`(补试运行层)、扩测试。

- [ ] Step1: engine `_load_on_tick` 改造:支持传"代码字符串"来源(新增 `run_code(code, params, candles, ...)` 或 `_load_on_tick` 接受 code 参数走 safe_exec.exec_strategy),不破坏现有 _BUILTIN_MAP importlib 路径。
- [ ] Step2: validation `check_trial_run(code) -> {ok, signal_count, error?}`:生成合成K线(参照 test_backtest `_build_crossover_candles` 造有涨跌趋势的~150根)→ safe_exec 取 on_tick → 复用 engine 跑 → 捕异常返 {tick,exception};正常返 {ok, signal_count}。
- [ ] Step3: `validate_strategy_code(code) -> {check_status, check_report}`:组合语法+AST+试运行三层,任一失败即 failed + 该层 report。
- [ ] Step4: 测试:能跑通on_tick→passed+signal_count;on_tick除零/未定义变量→failed+异常tick;三层组合。
- [ ] Step5: pytest过。Commit `feat(usercode): 试运行层(复用回测引擎合成K线)+validate_strategy_code三层组合`。

---

## Task 4: 后端 API — create/check/submit + serializer

**Files:** `views.py`/`urls.py`(改)、扩 test_strategy_marketplace。

- [ ] Step1: StrategyCreateView 扩展:接 source_type(template默认|code)、code。code类型:同步跑 validate_strategy_code 写 check_status/check_report。template 类型走现有逻辑。
- [ ] Step2: `POST /strategies/<id>/check`(strategy:update,owner):对已存code策略重跑检测更新check_status/report。
- [ ] Step3: StrategySubmitView:source_type=code且check_status!=passed→400。
- [ ] Step4: StrategySerializer:加 source_type/code/check_status/check_report;**code脱敏**:他人私有不返code(params同规则);公开+approved 或 owner 或内置 可见code。
- [ ] Step5: 测试:create code跑检测;check端点;submit要求passed;他人私有code不暴露;公开可见。
- [ ] Step6: pytest过。Commit `feat(usercode): create/check/submit API+code脱敏`。

---

## Task 5: runner API v1 版本化冻结 + 契约文档

**Files:** `urls.py`(改)、`docs/superpowers/runner-api-v1-contract.md`(新)、`strategy-runner/runner.py`(改端点)。

- [ ] Step1: urls 加 `runner/v1/candles|order|log` 指向现有 Runner*View(契约不变);保留旧 `runner/candles|order|log` 作别名(同View)。
- [ ] Step2: runner.py 端点改 `/api/strategy/runner/v1/*`(candles/order/log 三处)。
- [ ] Step3: 契约文档 runner-api-v1-contract.md:v1 三端点请求/响应结构冻结,标注"只增不改,变更走v2",CLAUDE.md/记忆提醒。
- [ ] Step4: 测试:v1端点契约同旧(candles/order/log);旧别名仍通。pytest过。Commit `feat(usercode): runner API v1版本化冻结+旧路径别名+契约文档`。

---

## Task 6: runner 执行用户代码 + 镜像 numpy/pandas

**Files:** `strategy-runner/runner.py`(改load_on_tick)、`strategy-runner/Dockerfile`(改)、`strategy-runner/builtin/`(新内置副本 Task8)。

- [ ] Step1: runner.py load_on_tick:env 有 USER_CODE → 受控exec(限__builtins__安全子集,与safe_exec同款逻辑,runner内独立实现一份因runner无backend依赖)取on_tick;否则CODE_REF内置分支(现状)。
- [ ] Step2: Dockerfile:pip装 numpy+pandas(PyPI官方源,参照backend不用清华源);COPY runner的safe builtins逻辑(runner.py内联或加个safe_exec.py到runner)。
- [ ] Step3: runner离线测试(无需backend):USER_CODE exec出on_tick;禁import被拦(runner层exec也限__builtins__)。
- [ ] Step4: 重建镜像 `docker build -t quanly-strategy-runner strategy-runner/` 成功。Commit `feat(usercode): runner支持USER_CODE受控exec+镜像装numpy/pandas`。

---

## Task 7: tasks 网络隔离 + pids_limit + USER_CODE 注入

**Files:** `core/strategy/tasks.py`(改)、`docker-compose.yml`(可能加隔离network)。

- [ ] Step1: code类型注入 `USER_CODE=strategy.code` 到 container_env(template类型不注入,走CODE_REF)。
- [ ] Step2: 网络隔离:创建/使用专用 Docker network(internal=true 不通外网),策略容器接该network,backend也接入(或该network能到backend)。禁postgres/redis/外网。**方案**:tasks 起容器用独立 network(如 quanly_strategy_isolated,internal),backend 也 attach 该 network;或用现有network但加firewall——**采用独立internal network + backend attach**。docker-compose 定义该 network + backend 接入。
- [ ] Step3: 加 pids_limit=128。保留现有 cap_drop/read_only/no-new-privileges/mem/cpu/tmpfs。
- [ ] Step4: 测试(mock docker):code策略注入USER_CODE;network参数正确;pids_limit。Commit `feat(usercode): tasks网络隔离(internal network只通backend)+pids_limit+USER_CODE注入`。

---

## Task 8: 扩内置模板 RSI + MACD

**Files:** `core/strategy/builtin/{rsi,macd}.py`(新)、`strategy-runner/builtin/{rsi,macd}.py`(副本)、engine `_BUILTIN_MAP`(加)、runner load_on_tick(加分支或目录扫描)、Dockerfile COPY、seed。

- [ ] Step1: 写 backend builtin/rsi.py + macd.py(on_tick+compute_signal纯函数,参照dual_ma)。
- [ ] Step2: runner/builtin 放副本;Dockerfile COPY;runner load_on_tick 加分支(或改目录扫描注册减少硬编码);engine _BUILTIN_MAP 加。
- [ ] Step3: seed_builtin_strategies 加 rsi/macd(owner=None/approved/public)。
- [ ] Step4: 测试:engine 跑 rsi/macd 出信号;seed。pytest过。重建镜像。Commit `feat(usercode): 内置策略RSI+MACD`。

---

## Task 9: 前端 — 来源tab+代码框+检测+check_status

**Files:** `MyStrategies.vue`(改)、`api/strategy.ts`(改)、`locales`(改)。

- [ ] Step1: api/strategy.ts:Strategy interface加source_type/code/check_status/check_report;createStrategy payload支持source_type/code;新增 checkStrategy(id)。
- [ ] Step2: MyStrategies 新建对话框加来源radio(点击式模板/Python脚本);模板走现有;脚本显示代码框(textarea+契约说明+示例)+检测按钮→checkStrategy→展示check_report(语法/AST违规/试运行信号数);check passed才能保存提交。
- [ ] Step3: 列表加check_status列(着色);详情code策略显示代码(owner/公开)。
- [ ] Step4: i18n zh/en新增(source类型/代码/检测/AST违规/试运行/契约说明等)。响应式(dialog手机92%/代码框可用)。
- [ ] Step5: build过。Commit `feat(usercode): 前端来源tab+代码框+检测+check_status`。

---

## Task 10: Docker 重建 + 端到端验收

- [ ] Step1: 重建 backend+celery-worker+nginx + 重建 quanly-strategy-runner 镜像(numpy/pandas)。
- [ ] Step2: 验收(见 Verification)。

---

## Verification(整体)

1. **后端pytest**:validation三层(语法/AST各黑名单项/白名单/无on_tick/试运行跑通与异常);create code写check;check端点;submit要求passed;code脱敏(他人私有不暴露/公开可见);runner v1契约+旧别名;RSI/MACD engine跑通。OKX/docker打桩。
2. **前端build**过。
3. **AST安全实测**:提交import os/eval/__subclasses__→failed返违规项;正常→passed。
4. **试运行实测**:能跑on_tick→passed+signal_count;除零→failed+异常tick。
5. **网络隔离实测(真环境)**:用户代码requests外网被拦;ctx经backend v1通。
6. **v1冻结**:运行中容器打v1通;旧别名通。
7. **隔离/热更新实测**:起用户策略容器→deploy.sh update重建backend→容器不被杀+v1回调恢复继续。
8. **回归**:template策略/dual_ma/回测/资产不破。
9. Docker+镜像重建后端到端。

## 执行方式

subagent-driven-development。依赖:T1模型→T2 AST/exec→T3试运行→T4 API→T5 v1冻结→T6 runner exec→T7网络隔离→T8内置→T9前端→T10验收。**重点review**:T2/T3(AST审查+受控exec的安全正确性,沙箱逃逸手法)、T7(网络隔离真隔离)、T4(code脱敏)。BASE=6235237。
