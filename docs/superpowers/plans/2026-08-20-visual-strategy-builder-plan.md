# 可视化策略构建器 + 回测全类型支持 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development 逐任务执行。步骤用 checkbox 追踪。

**Goal:** 用户可视化配置策略(选指标/条件/参数/止盈止损,不写代码);规则编译成 Python 复用 source_type=code 执行链路;回测引擎扩展支持所有 source_type(内置/uploaded/code/visual)。全程响应式+中英文+零 mock。

**Architecture:** 新 source_type=visual + rule_config(原始规则 JSON);rule_compiler 把规则编译成 Python 存 code(复用容器exec/AST/试运行);engine 加受控exec分支支持 code/visual 回测;前端 RuleBuilder 可视化条件构建。

**Tech Stack:** Django5+DRF;safe_exec/AST(已有);Vue3+TS+ElementPlus。

## Global Constraints

- **执行复用 code 链路**:visual 编译产物存 code,走 source_type=code 的容器隔离(cap_drop/read_only/network隔离/pids_limit)+AST三层检测+受控exec+试运行。可视化=编译层。
- **编译器防注入(安全核心)**:数值(period/const/pct/sz)float/int校验;指标名/运算符/logic白名单枚举;指标计算内联(runner独立容器不能import backend);不拼接任意用户字符串。编译产物过AST(白名单内建+内联函数)。
- **回测受控exec**:backend进程用safe_exec.exec_strategy跑code/visual(纯计算/内存ctx/无凭证/不触网/不下真单);AST已提交时查=二次防护。
- **持仓状态**:编译代码用模块级变量(exec的ns=on_tick.__globals__,跨tick保留;回测engine/runner每tick调同一on_tick保留)。实现时验证。
- **内置只读**;多租户;visual脱敏(rule_config/code他人私有不暴露);响应式;i18n zh/en。
- 本地commit不push;精确git add;每步pytest/build过。BASE=02a95e0。

## File Structure
- `backend/core/strategy/models.py`(改) — SOURCE_VISUAL + rule_config字段 + migration。
- `backend/core/strategy/rule_compiler.py`(新) — validate_rule_config + compile_rule(规则→Python)+ 指标代码模板。
- `backend/core/backtest/engine.py`(改) — run/`_load_on_tick`加code参数(受控exec)。
- `backend/core/backtest/{tasks,views}.py`(改) — run_backtest传code;创建放开所有source_type。
- `backend/core/strategy/views.py`(改) — create/put/submit visual分支;serializer加rule_config脱敏。
- `frontend/src/views/strategy/RuleBuilder.vue`(新) — 可视化条件构建器。
- `frontend/src/views/strategy/MyStrategies.vue`(改) — 来源加visual。
- `frontend/src/api/strategy.ts`(改) — rule_config;`frontend/src/views/backtest/Backtest.vue`(改) — 策略选择放开。
- locales(改)。

---

## Task 1: 模型 SOURCE_VISUAL + rule_config

**Files:** models.py(改)+migration。
- [ ] Step1: source_type choices 加 `SOURCE_VISUAL="visual"`;加 `rule_config = JSONField(default=dict)`。
- [ ] Step2: makemigrations core_strategy + migrate(export env,ENC_KEY别内联,PG 5433)。
- [ ] Step3: 跑 test_strategy 回归。Commit `feat(visual): 模型SOURCE_VISUAL+rule_config字段+migration`。

---

## Task 2: 规则编译器 + 指标库(安全核心)

**Files:** `backend/core/strategy/rule_compiler.py`(新)、`tests/test_rule_compiler.py`(新)。

**Interfaces:**
- Produces: `validate_rule_config(cfg) -> None`(非法raise ValueError);`compile_rule(cfg) -> str`(Python on_tick源码)。

- [ ] Step1: `validate_rule_config`:buy/sell至少一组有conditions;每condition的left/right指标名∈{MA,EMA,RSI,MACD,price,volume,const}、op∈{cross_above,cross_below,>,<,>=,<=}、logic∈{and,or};period/const/pct/sz可float/int化;非法raise ValueError(带原因)。
- [ ] Step2: 指标代码模板(编译器内字符串常量):`_ma(closes,n)`/`_ema(closes,n)`/`_rsi(closes,n)`/`_macd(closes,f,s,sig)`(照 builtin/{dual_ma,rsi,macd}.py 纯函数抄)。
- [ ] Step3: `compile_rule(cfg)`:生成 on_tick 源码——顶部内联用到的指标函数;模块级持仓状态(_pos/_entry_price);每tick:算指标值(cross需prev/now)→有持仓查risk止盈止损(浮盈/亏损pct)→无持仓查buy组(and/or)→有持仓查sell组→ctx.buy/sell(sz,记_entry_price)+ctx.log。**数值白名单化插值(float/int后插),指标/op枚举映射,绝不插原始字符串**。
- [ ] Step4: 测试:各指标/运算符/and/or/止盈止损编译出合法Python(compile()过);编译产物过AST(validation.check_ast ok);防注入(rule里塞恶意字符串如period="__import__('os')"被float校验挡→ValueError);cross_above/比较语义;止盈止损逻辑。
- [ ] Step5: pytest过。Commit `feat(visual): 规则编译器(JSON→Python)+指标库+防注入`。

---

## Task 3: 回测引擎扩展(受控exec支持code/visual)

**Files:** `engine.py`/`backtest/tasks.py`/`backtest/views.py`(改)、扩test_backtest。

- [ ] Step1: engine `run` 加 `code: str|None=None` 参数;`_load_on_tick` 逻辑:若code非空→`safe_exec.exec_strategy(code)`取on_tick,否则_load_on_tick(code_ref)。**关键:exec_strategy返回的on_tick持有ns作__globals__,模块级持仓状态跨bar保留**(回测逐bar调同一on_tick)。
- [ ] Step2: run_backtest task:取strategy,source_type in(code,visual)→传strategy.code给engine.run(code=...);内置/uploaded传code_ref。
- [ ] Step3: BacktestListCreateView:放开策略选择——现可能限内置,改成任意strategy(多租户:自己的+可见的,复用_runnable_qs语义)。
- [ ] Step4: 测试:code/visual策略回测跑通(受控exec喂合成K线出净值+trades+metrics);模块级持仓状态跨bar保留(止盈止损策略回测能平仓);内置回测不退化;回测创建放开。受控exec安全(回测跑含import os的code被拦——但code已过AST,防御性)。
- [ ] Step5: pytest过。Commit `feat(visual): 回测引擎受控exec支持code/visual+回测创建放开所有类型`。

---

## Task 4: 后端 API visual create/put/submit + 脱敏

**Files:** `strategy/views.py`(改)、扩test_strategy_marketplace。
- [ ] Step1: StrategyCreateView visual分支:body{source_type:"visual",rule_config,name,description,visibility}→validate_rule_config→compile_rule生成code→存rule_config+code,source_type=visual,owner=self,status=draft→validate_strategy_code(code)三层检测→check_status。规则非法400。
- [ ] Step2: StrategyDetailView.put:visual改rule_config→重编译code+重跑检测(仿code的PUT)。
- [ ] Step3: StrategySerializer:fields加rule_config;get_rule_config脱敏(他人私有={},同get_code规则)。submit:visual同code要check passed。
- [ ] Step4: 测试:create visual(存rule_config+code+check_status;规则非法400);put改rule_config重编译;脱敏他人私有rule_config;submit要passed;run guard对visual(自己的能run)。
- [ ] Step5: pytest过。Commit `feat(visual): create/put/submit visual API+rule_config脱敏`。

---

## Task 5: 前端 RuleBuilder + MyStrategies + 回测页放开

**Files:** `RuleBuilder.vue`(新)、`MyStrategies.vue`/`api/strategy.ts`/`Backtest.vue`/locales(改)。
- [ ] Step1: api:Strategy interface加source_type "visual"/rule_config;createStrategy/updateStrategy支持rule_config。
- [ ] Step2: `RuleBuilder.vue`:买入条件组(条件行增删:指标el-select[MA/EMA/RSI/MACD/价格/成交量]+参数[period等]+运算符[上穿/下穿/>/</>=/<=]+右值[指标或常量数字]+组内and/or radio)+卖出条件组+止盈止损(take_profit_pct/stop_loss_pct数字可空)+sz。v-model输出rule_config。响应式(手机条件行竖排)。
- [ ] Step3: MyStrategies来源radio加visual;visual区块挂RuleBuilder;onSave visual分支createStrategy({source_type:"visual",rule_config,...});检测面板/check_status列放宽含visual;编辑回填rule_config。
- [ ] Step4: Backtest.vue策略选择放开到所有source_type(现可能限内置)。
- [ ] Step5: i18n:指标名(MA/EMA/RSI/MACD/价格/成交量)/运算符(上穿/下穿/大于/小于等)/条件组(买入条件/卖出条件/且/或)/止盈/止损/添加条件/可视化构建 sourceVisual等,zh/en对齐。
- [ ] Step6: build过。Commit `feat(visual): 前端RuleBuilder可视化构建器+MyStrategies visual来源+回测页放开+i18n`。

---

## Task 6: Docker 重建 + 端到端验收
- [ ] Step1: 重建backend+celery-worker+nginx(+strategy-runner若指标模板动)。
- [ ] Step2: 验收(见Verification)。

---

## Verification(整体)
1. **后端pytest**:rule_compiler(各指标/运算符/and-or/止盈止损编译合法Python+过AST+防注入非数字参数被挡);create visual(rule_config+code+检测);put重编译;脱敏;回测code/visual跑通(模块级持仓跨bar+止盈止损平仓);内置回测不退化;回测放开。
2. **前端build**过。
3. **端到端**:可视化拼策略(MA5上穿MA20且RSI<30买/MA5下穿MA20卖/止盈5%止损3%)→创建→检测通过→**回测出净值曲线**→提交审核→approved商城可见→实盘运行(切代理连OKX)。所有source_type都能回测。手机构建器可用。中英文。
4. **回归**:builtin/uploaded/code运行/回测/商城/安全链路不破。
5. Docker重建后验收。

## 执行方式
subagent-driven-development。依赖:T1模型→T2编译器(安全核心)→T3回测扩展→T4 API→T5前端→T6验收。**重点review**:T2 rule_compiler防注入(数值校验/白名单/无字符串注入/编译产物过AST)、T3回测受控exec安全(backend进程跑code)+模块级持仓状态跨bar。BASE=02a95e0。
