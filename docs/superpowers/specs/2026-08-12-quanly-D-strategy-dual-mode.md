# 子项目 D — 策略双模式创建（可视化配置 + 在线代码编辑器）

日期：2026-08-12
父设计：`2026-08-12-quanly-strategy-page-overhaul-overview.md`
优先级：中（依赖 C 的模板库 `mode`/`visual_config` 字段）
状态：待复审

## 目标

新增两种策略创作方式，产物统一进模板库、统一被任务面板调用、多标的并行运行：
1. **简易可视化模式**：表单/下拉/开关配置 → 系统自动生成底层执行脚本。
2. **专业代码模式**：在线 Python 编辑器，语法校验 + 预运行调试。

## 关键约束（不破坏沙箱）

- 两模式产物都是 `Strategy` 记录，`source` 都是**符合现有 `on_tick(ctx)` 接口**的 Python，
  走**完全相同的容器执行路径**（runner / runner_api）。不引入第二套执行引擎。
- 可视化生成的源码可预览、可「转代码模式」手改（转后 `mode=code`，脱离表单）。

## 设计

### D1：可视化骨架模板（后端，Jinja2 生成 Python）
- 新增 `apps/strategy/visual/`：
  - `schemas.py`：4 类策略的参数 schema（字段名/类型/默认/范围/i18n label key），
    供前端渲染表单、后端校验：
    - **均线交叉**：short/long 周期、下单量、方向。
    - **网格交易**：区间上下界、格数、每格量。
    - **定投 DCA**：周期（tick 数）、每次买入额。
    - **止盈止损**：止盈%、止损%、移动止盈%、下单量。
  - `templates/`：4 个 Jinja2 `.py.j2` 骨架（参数占位），渲染出完整 `on_tick(ctx)` 源码。
    骨架逻辑对齐现有 builtins.py 里 MA_CROSS/GRID/COMPOSITE 的写法与 ctx API。
  - `generate.py`：`generate_source(kind, config) -> str`，校验 config 符合 schema 后
    渲染对应骨架；生成的源码经 `compile()` 语法自检，失败抛错。

### D2：可视化 API（后端）
- `GET /api/strategy/visual/schemas`：返回 4 类 schema（前端据此渲染表单）。
- `POST /api/strategy/visual/preview`：body `{kind, config}` → 返回生成的源码（不落库，供预览）。
- 保存：走 C 的 `Strategy` 创建，`mode=visual` + `visual_config={kind, config}` +
  `source=generate_source(...)`（保存时后端再生成一次，确保 source 与 config 一致）。
- 编辑可视化模板：回填 `visual_config` 到表单；改后重新 generate 覆盖 source。

### D3：代码模式 —— 语法校验 + 预运行调试（后端）
- `POST /api/strategy/code/validate`：body `{source}` → `compile()` 校验，返回
  语法错误位置 / OK。
- `POST /api/strategy/code/dryrun`：body `{source, symbol, bar, bars}` → **复用回测引擎**
  （`apps.backtest.engine`）跑一遍 on_tick，返回少量 tick 的执行日志 + 是否报错，
  作为「预运行调试」。不下真实单、不起容器（快速反馈）。

### D4：前端双模式编辑器
- `StrategyEditor.vue`（模板库新建/编辑入口，替换旧 inline textarea）：
  - 顶部模式切换 Tab：可视化 / 代码。
  - **可视化 Tab**：拉 `/visual/schemas` 动态渲染表单（GlassSelect/GlassNumber/开关），
    实时调 `/visual/preview` 在只读代码框预览生成的源码；「转为代码模式」把预览源码
    灌入代码 Tab 并切 `mode=code`。
  - **代码 Tab**：**CodeMirror 6** Python 编辑器（语法高亮 + 行号），
    「校验」按钮调 `/code/validate`，「预运行」调 `/code/dryrun` 显示调试输出。
  - 保存：可视化存 `{mode:visual, visual_config, source}`；代码存 `{mode:code, source}`。
- 依赖：新增 `codemirror` + `@codemirror/lang-python`（前端 package.json）。

### D5：i18n
- 新增 `strategy.editor.* / strategy.visual.*`（模式切换、4 类策略字段 label、
  预览、校验、预运行、转代码等），zh-CN / en-US 对齐。

## 涉及文件
- `backend/apps/strategy/visual/schemas.py`、`generate.py`、`templates/*.py.j2`（D1 新增）
- `backend/apps/strategy/views.py`（D2/D3 端点）
- `backend/apps/strategy/urls.py`（D2/D3 路由）
- `backend/apps/backtest/engine.py`（D3 复用；如需暴露轻量 dryrun 封装）
- `frontend/src/views/StrategyEditor.vue`（D4 新增）
- `frontend/src/api/strategy.ts`（visual/code 接口）
- `frontend/package.json`（D4 CodeMirror 依赖）
- `frontend/src/i18n/zh-CN.ts` / `en-US.ts`（D5）

## 不改动（保护边界）
- runner / runner_api / on_tick 接口不变；生成源码即普通策略。
- OKX 适配器、虚实盘 env、回测引擎核心逻辑不动（仅复用其 dryrun）。

## 验收标准（网页可测）
1. 可视化模式配置一个均线交叉策略 → 实时预览生成的 Python 源码 → 保存进模板库 →
   任务面板可选中并批量启动、正常跑。
2. 4 类骨架（均线/网格/DCA/止盈止损）均可配置生成且能启动运行。
3. 「转为代码模式」把生成源码带入代码编辑器，可手改后保存为 code 模板。
4. 代码模式：写错语法 → 校验报出错误位置；「预运行」用回测引擎返回调试输出，不下真实单。
5. 两模式产物在模板库统一列出，均可多标的并行运行。
6. 后端 pytest 全绿；zh/en key 对齐。

## 测试
- 单测：`generate_source` 4 类 × 参数校验 + 生成源码可 `compile` + 含 `on_tick`；
  preview/validate/dryrun 端点；非法 config 报错。
- TDD：先写失败测试再实现。
