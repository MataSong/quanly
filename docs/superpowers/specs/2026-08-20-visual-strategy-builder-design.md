# 可视化策略构建器 + 回测全类型支持 设计文档

**日期**: 2026-08-20
**范围**: 用户通过可视化配置(选指标/条件/参数/止盈止损,不写代码)创建策略;规则编译成 Python 复用用户代码执行链路;回测引擎扩展支持所有 source_type(内置/参数化/用户代码/可视化)。全程 PC/手机响应式 + 中英文 + 零 mock。
**不做(后续)**: 拖拽式画布、布林带/KDJ 等更多指标、实时预览图。

## 背景与目标

策略商城已有三种来源:builtin(内置只读)、uploaded(点击式内置模板+调参)、code(用户 Python 脚本,三道安全防线)。用户要第四种:**像交易所那样可视化配置策略**——选指标+条件+参数+止盈止损,填表单/点按钮生成普通策略,不写代码。同时明确:**所有策略都要能回测**(现回测引擎只支持 3 个内置,code/visual 都不能回测,是缺口)。

已确认决策:
- 表达能力 = **完整规则引擎**(多组条件、且/或、百分比止盈止损、仓位)。
- 指标 = MA/EMA/RSI/MACD/价格/成交量(后续可加)。
- 执行方案 = **(a) 规则编译成 Python 存 code,复用 source_type=code 执行链路**(容器隔离/AST/受控exec/试运行几乎零改动)。
- 回测 = **所有策略支持**;回测在 backend 进程用受控 exec 跑(纯计算、无凭证、不触网、不下真单,受控 exec 够;不起容器,回测快)。
- 一份 spec 全做(回测扩展+规则引擎+前端UI)。

## 架构决策

1. **source_type=visual + rule_config**:新增来源 visual;新增 `rule_config` JSON 存**原始规则**(编辑器回填/可读/可演化);**编译产物存现有 `code` 字段**,复用 source_type=code 的容器 exec + 三层检测 + 安全隔离全链路。可视化只是"规则→代码"编译层。
2. **规则编译器**(rule_compiler.py):rule_config JSON → Python on_tick 源码。防注入:数值校验为数字、指标/运算符白名单枚举、指标计算内联(runner 独立容器不能 import backend)。生成代码天然过 AST(白名单内建+内联函数)。
3. **回测引擎扩展**:engine `_load_on_tick` 加分支——code/visual 用 safe_exec 受控 exec 取 on_tick(内置仍 importlib)。回测在 backend 进程受控 exec(纯计算/无凭证/内存 ctx,受控 exec + AST 已查 = 二次防护)。回测创建放开到所有 source_type。
4. **内置只读**:builtin(owner=None,系统 seed)用户不能编辑,只能商城选用/运行/回测。

## 数据模型(`backend/core/strategy/models.py`)

- source_type choices 加 `SOURCE_VISUAL = "visual"`。
- 新增 `rule_config = models.JSONField(default=dict)` — 可视化原始规则。
- 复用 `code`(编译产物)、`check_status`/`check_report`(编译后检测)。
- migration。

## 规则结构(rule_config JSON)

```json
{
  "buy":  {"logic":"and","conditions":[
            {"left":{"ind":"MA","period":5},"op":"cross_above","right":{"ind":"MA","period":20}},
            {"left":{"ind":"RSI","period":14},"op":"<","right":{"const":30}}]},
  "sell": {"logic":"or","conditions":[
            {"left":{"ind":"MA","period":5},"op":"cross_below","right":{"ind":"MA","period":20}}]},
  "risk": {"take_profit_pct":5.0,"stop_loss_pct":3.0},
  "sz": "0.001"
}
```
- **指标**(left/right):`MA`/`EMA`(period)、`RSI`(period)、`MACD`(fast/slow/signal + line:macd|signal)、`price`(收盘)、`volume`、`const`(常量)。
- **运算符 op**:`cross_above`/`cross_below`(prev/now 双点)、`>`/`<`/`>=`/`<=`。
- **逻辑 logic**:每组(buy/sell)多条件 `and`/`or`。
- **risk**(可选):`take_profit_pct`(浮盈≥X%卖)、`stop_loss_pct`(亏损≥Y%卖)。
- **sz**:每次下单量。
- **执行语义**:每 tick 算指标 → 有持仓先查止盈止损(优先) → 无持仓查 buy 组(满足→买,记买入价) → 有持仓查 sell 组(满足→卖)。持仓成本/浮盈在策略内维护(买入价 vs 当前价)。

## 规则编译器(`backend/core/strategy/rule_compiler.py` 新)

- `compile_rule(rule_config) -> str`:生成 Python on_tick 源码。
- **防注入**:
  - 数值(period/const/pct/sz)`float()`/`int()` 校验,非数字→ValueError(编译期 400)。
  - 指标名/运算符/logic 白名单枚举校验,非白名单→ValueError。
  - 生成代码只用 safe_exec 白名单内建 + 内联指标函数,不拼接任意用户字符串。
- **指标计算内联**:编译器持有 `_ma/_ema/_rsi/_macd` Python 代码模板(照 builtin/{dual_ma,rsi,macd}.py 现有纯函数),按规则用到的指标内联进生成代码(runner 独立容器不能 import backend builtin)。
- `validate_rule_config(rule_config)`:结构校验(buy/sell 至少一组有条件、字段合法),编译前先校验。
- 生成代码维护持仓状态(用 ctx 无状态,靠"当前是否持仓"——通过 ctx 查持仓 or 策略内变量?**注**:on_tick 每 tick 独立调用,需持仓状态。方案:编译代码用**模块级变量**记录持仓/买入价(runner 进程内持久),或每 tick 通过 ctx 查(ctx 无持仓查询)——**采用模块级变量**(runner 单策略单进程,模块级状态 tick 间保留;试运行/回测同理内存态)。实现时确认 runner on_tick 调用方式支持模块级状态(TrialCtx/RunnerCtx 每 tick 调同一 on_tick 函数,模块级变量保留)。

## 后端 API(`views.py`)

- StrategyCreateView 加 `visual` 分支:body {source_type:"visual", rule_config, name, description, visibility}。`validate_rule_config` → `compile_rule` 生成 code → 存 rule_config+code,source_type=visual,owner=self,status=draft → 跑 `validate_strategy_code(code)` 三层检测 → check_status。规则非法→400。
- StrategyDetailView.put:visual 类型支持改 rule_config → 重编译 code + 重跑检测(仿 code 的 PUT 重跑)。
- StrategySerializer:fields 加 rule_config;脱敏(get_rule_config)按 code/params 同规则(他人私有不暴露)。
- submit:visual 同 code,check_status 须 passed。

## 回测引擎扩展(`backend/core/backtest/engine.py` + `tasks.py` + `views.py`)

- `engine.run` / `_load_on_tick`:加 code 参数——若传 code(code/visual 策略),用 `safe_exec.exec_strategy(code)` 取 on_tick;否则内置走 _BUILTIN_MAP importlib。
- `run_backtest` task:取 strategy,若 source_type in (code, visual) 传 strategy.code 给 engine;内置/uploaded 传 code_ref(uploaded 用 template_ref 跑内置)。
- BacktestListCreateView:放开策略选择到所有可回测策略(现可能限内置)。
- 受控 exec 安全:回测纯计算(内存 BacktestContext,buy/sell 只记模拟成交,无凭证/不触网/不下真单),用 safe_exec 白名单 __builtins__ + 受控 __import__。code 已在提交时过 AST,回测 exec 是二次防护。

## 前端(`MyStrategies.vue` + 新 `RuleBuilder.vue` + api + i18n)

- MyStrategies 新建对话框来源 radio 加 `visual`(可视化构建);内置只读不在此。
- `RuleBuilder.vue`(新子组件):买入条件组(条件行增删:指标选择器[MA/EMA/RSI/MACD/价格/成交量+参数]+运算符[上穿/下穿/>/</>=/<=]+右值[指标或常量];组内 and/or)+ 卖出条件组 + 止盈止损(take_profit_pct/stop_loss_pct 数字,可空)+ sz。组装 rule_config。
- createStrategy/updateStrategy 支持 rule_config;Strategy interface 加 source_type=visual/rule_config。检测面板/check_status 列复用(放宽含 visual)。编辑回填 rule_config。
- 回测页:策略选择放开到所有 source_type。
- 响应式(手机条件行竖排)+ i18n(指标名/运算符/止盈止损/条件组等 zh/en 对齐)。

## 错误处理

- 规则非法(空条件/非法指标/非数字参数)→ 编译期 400 明确提示。
- 编译产物过不了 AST/试运行 → check_status=failed + report(理论上编译产物可控应总过,防御性)。
- 回测 code/visual exec 出错 → 回测 status=error + error_msg(现有回测错误处理)。
- 内置策略用户尝试编辑 → 403/不提供入口。
- 多租户:visual 策略 mine/CRUD 限 owner;脱敏他人私有 rule_config/code。

## 验证

1. **后端 pytest**:
   - rule_compiler:各指标(MA/EMA/RSI/MACD/price/volume)+ 运算符(cross/比较)+ and/or + 止盈止损 编译出合法 Python;数值/指标白名单防注入(非法→ValueError);编译产物过 AST。
   - create visual:存 rule_config+code+check_status;规则非法 400;PUT 改 rule_config 重编译重检测。
   - 回测扩展:code/visual 策略回测跑通(受控 exec 喂合成/历史 K 线出净值+指标);内置回测不退化;回测创建放开所有类型。
   - 脱敏:他人私有 rule_config/code 不暴露。
   - 编译产物在受控 exec 下能跑(模块级持仓状态 tick 间保留)。
2. **前端 build** 过。
3. **端到端**:可视化构建器拼一个策略(MA5上穿MA20且RSI<30买,MA5下穿MA20卖,止盈5%止损3%)→ 创建 → 检测通过 → 回测出净值曲线 → 提交审核 → 商城可见 → 实盘运行(切代理连OKX)。所有 source_type 都能回测。手机构建器可用。中英文。
4. **回归**:内置/uploaded/code 策略运行/回测/商城不破;安全链路(容器隔离/AST)不退化。
5. Docker 重建 backend+nginx(+strategy-runner 若指标模板改动) 验收。

## 执行方式

subagent-driven-development。依赖:模型→rule_compiler(编译器+指标库+防注入)→回测引擎扩展(engine受控exec)→create/put/submit API→前端RuleBuilder+回测页放开→Docker验收。重点review:rule_compiler防注入(数值校验/白名单/无字符串注入)、回测受控exec安全(backend进程跑用户代码)、编译产物过AST。
