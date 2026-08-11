# Quanly P9 前端修复实现计划(行情K线 + 下拉框统一 + 金额输入 + 可搜索筛选)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** 修复行情K线切换空白 + 时区、消除"框框套框框"的双边框、放大理财/借贷/划账金额输入、给交易/回测/策略的交易对与策略选择加可搜索筛选。

**Architecture:** 公共行情后端统一走 OKX 实盘(免鉴权,只读)以获得完整K线;前端把误用的 `class="input"` 从所有 Glass* 组件上移除(组件自带玻璃样式,外再套 `.input` 造成双边框);新增一个通用可搜索下拉 `SearchSelect.vue`,替换交易/回测/策略里的交易对、回测策略选择器;金额输入组件支持更宽尺寸。

**Tech Stack:** Vue 3 + TS + Vite,现有 GlassSelect/GlassNumber/SymbolSelect 组件,glass.css 主题变量,Django DRF 后端 market 视图。

**约束:**
- 项目**非 git 仓库** → 无 commit 步骤,用 `bash -n`/构建/浏览器验证。
- 前端**无测试框架** → 用 `npm run build`(vue-tsc 类型检查)+ 容器重建 + 浏览器实测。
- 公共行情改实盘**不需要也不填任何实盘 key**(MarketData/PublicData 免鉴权);私有下单/账户/资产仍走用户填的模拟盘 key。
- 保持 Apple/Ghostty 玻璃拟态风格,全站视觉一致。

**参考文件(实现前已读):**
- `frontend/src/components/GlassSelect.vue`(自带 `.gs-trigger` 边框)
- `frontend/src/components/SymbolSelect.vue`(已有的可搜索+品类页签下拉,是 SearchSelect 的样式蓝本)
- `frontend/src/components/GlassNumber.vue`(inline-flex,两侧 34px 按钮)
- `frontend/src/styles/glass.css`(`.input` 定义在 101 行)
- `frontend/src/views/Market.vue`、`Trade.vue`、`Backtest.vue`、`StrategyDetail.vue`、`Transfer.vue`、`Finance.vue`
- `frontend/src/components/CandleChart.vue`(timeScale 在 89 行)
- `backend/apps/market/views.py`(candles/symbols/instrument 视图,当前用 `Env.SIM`)

---

## File Structure

| 文件 | 职责 | 改动 |
|------|------|------|
| `backend/apps/market/views.py` | 公共行情 | candles/symbols/instrument 三个视图的适配器从 `Env.SIM` 改 `Env.LIVE` |
| `frontend/src/components/CandleChart.vue` | K线图 | 时区改中国时间(UTC+8);空数据显示提示 |
| `frontend/src/components/SearchSelect.vue`(新增) | 通用可搜索下拉 | 复用 SymbolSelect 样式,接受 options + 可搜索 |
| `frontend/src/views/Trade.vue` | 交易 | 去 `class="input"`;交易对改 SearchSelect 并按 instType 过滤 |
| `frontend/src/views/Backtest.vue` | 回测 | 去 `class="input"`;策略、交易对改 SearchSelect |
| `frontend/src/views/StrategyDetail.vue` | 策略 | 去 `class="input"`;交易对改 SearchSelect |
| `frontend/src/views/Transfer.vue` | 划账 | 去 `class="input"`;金额加宽 |
| `frontend/src/views/Finance.vue` | 理财/借贷 | 去金额的 `class="input"`;金额加宽 |
| `frontend/src/components/GlassNumber.vue` | 数字输入 | 支持 `wide` 尺寸(min-width 更大,数字左对齐) |

**依赖顺序:** 后端 views.py → CandleChart → GlassNumber → SearchSelect → 各 view

---

## Task 1: 公共行情后端改用实盘数据(免 key)

**Files:**
- Modify: `backend/apps/market/views.py:32`(`_load_instruments`)、`:94`(`candles`)

- [ ] **Step 1: 把 instruments 加载改用 LIVE**

`backend/apps/market/views.py` 第 32 行:

```python
    adapter = AdapterFactory.create("okx", Env.LIVE, credential=None)
```

(原为 `Env.SIM`。公共 instruments 免鉴权,实盘品类/K线更全。)

- [ ] **Step 2: 把 candles 视图改用 LIVE**

`backend/apps/market/views.py` 第 88-96 行整体:

```python
@api_view(["GET"])
@permission_classes([AllowAny])
def candles(request, symbol):
    bar = request.query_params.get("bar", DEFAULT_BAR)
    limit = int(request.query_params.get("limit", 200))
    # 公共行情免鉴权,统一用 LIVE:OKX 模拟盘对多数合约(尤其 FUTURES)无 K线历史。
    adapter = AdapterFactory.create("okx", Env.LIVE, credential=None)
    data = [asdict(c) for c in adapter.get_candles(symbol, bar, limit)]
    return Response({"symbol": symbol, "bar": bar, "candles": data})
```

- [ ] **Step 3: 清 instruments 缓存并验证 FUTURES 有 K线**

Run:
```bash
cd /c/App/Project/quanly
docker compose -f docker-compose.yml -f docker-compose.local.yml --env-file .env.prod exec -T redis redis-cli DEL market:instruments:v2
docker compose -f docker-compose.yml -f docker-compose.local.yml --env-file .env.prod exec -T backend python manage.py shell -c "
from apps.exchanges.factory import AdapterFactory
from apps.exchanges.types import Env
a=AdapterFactory.create('okx',Env.LIVE,credential=None)
raw=a._public.get_instruments(instType='FUTURES').get('data',[])
sym=raw[0]['instId']
print('FUTURES', sym, 'candles=', len(a.get_candles(sym,'1m',5)))
"
```
Expected: `FUTURES <sym> candles= 5`(非 0)

---

## Task 2: K线图中国时区 + 空数据提示

**Files:**
- Modify: `frontend/src/components/CandleChart.vue`

- [ ] **Step 1: 时间轴显示为中国时间(UTC+8)**

lightweight-charts 的 time 是 UTC 秒;要显示成北京时间,给 `timeScale` 配 `tickMarkFormatter`,并给 series 配本地时间的 `localization`。在 `build()` 的 `createChart` options 里,把第 89 行 `timeScale` 替换为:

```javascript
    localization: {
      // 时间轴与十字光标统一显示北京时间(UTC+8)
      timeFormatter: (t: number) =>
        new Date((t as number) * 1000).toLocaleString("zh-CN", {
          timeZone: "Asia/Shanghai",
          hour12: false,
          month: "2-digit", day: "2-digit",
          hour: "2-digit", minute: "2-digit",
        }),
    },
    timeScale: {
      timeVisible: true,
      secondsVisible: false,
      tickMarkFormatter: (t: number) =>
        new Date((t as number) * 1000).toLocaleString("zh-CN", {
          timeZone: "Asia/Shanghai",
          hour12: false,
          month: "2-digit", day: "2-digit",
          hour: "2-digit", minute: "2-digit",
        }),
    },
```

- [ ] **Step 2: 空数据显示提示,避免切到无 K线的合约时纯空白**

在 `<script setup>` 顶部(第 19 行 `let lastTime` 附近)加:

```javascript
const empty = ref(false);
```

`loadHistory()` 里,在 `series?.setData(data)` 之前设置 empty 状态(替换第 53-55 行):

```javascript
  lastTime = data.length ? (data[data.length - 1].time as number) : 0;
  empty.value = data.length === 0;
  series?.setData(data);
  chart?.timeScale().fitContent();
```

模板(第 124-126 行)改为:

```html
<template>
  <div class="chart-wrap">
    <div ref="container" class="chart"></div>
    <div v-if="empty" class="chart-empty">{{ $t("market.noCandles") }}</div>
  </div>
</template>
```

样式块追加:

```css
.chart-wrap { position: relative; }
.chart-empty {
  position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  color: var(--fg-dim); font-size: 14px; pointer-events: none;
}
```

> 注:`$t` 在 `<script setup>` 需通过 `useI18n`。CandleChart 目前未引入 i18n,故 Step 3 补 import。

- [ ] **Step 3: 引入 useI18n**

`CandleChart.vue` `<script setup>` 顶部(第 11 行 `import client` 之后)加:

```javascript
import { useI18n } from "vue-i18n";
const { t: $t } = useI18n();
```

- [ ] **Step 4: 补 i18n 文案 `market.noCandles`**

在 `frontend/src/locales/zh.*`(或对应 zh 语言文件)`market` 段加键 `noCandles: "该合约暂无 K 线数据"`;en 文件加 `noCandles: "No candlestick data for this instrument"`。
先定位文件:`Grep "selectSymbol" frontend/src/locales`,在同段落追加。

- [ ] **Step 5: 构建通过**

Run: `cd /c/App/Project/quanly/frontend && npm run build 2>&1 | tail -15`
Expected: 构建成功,无 vue-tsc 类型报错。

---

## Task 3: 通用可搜索下拉 SearchSelect.vue

**Files:**
- Create: `frontend/src/components/SearchSelect.vue`

- [ ] **Step 1: 写 SearchSelect.vue 完整内容**

以 SymbolSelect 的样式为蓝本,去掉品类页签,改为纯 options + 关键字搜索的通用组件。接口:`modelValue`、`options: {label,value}[]`、`placeholder?`。

`frontend/src/components/SearchSelect.vue`:

```vue
<script setup lang="ts">
import { ref, computed, nextTick, onBeforeUnmount } from "vue";
import { useI18n } from "vue-i18n";

interface Option { label: string; value: string | number }
const props = defineProps<{
  modelValue: string | number | null;
  options: Option[];
  placeholder?: string;
}>();
const emit = defineEmits<{ "update:modelValue": [string | number] }>();
const { t } = useI18n();

const open = ref(false);
const keyword = ref("");
const trigger = ref<HTMLElement | null>(null);
const panelStyle = ref<Record<string, string>>({});

const current = computed(
  () => props.options.find((o) => o.value === props.modelValue)?.label
    ?? props.placeholder ?? t("common.select")
);

const filtered = computed(() => {
  const kw = keyword.value.toLowerCase();
  return kw
    ? props.options.filter((o) => String(o.label).toLowerCase().includes(kw))
    : props.options;
});

function place() {
  const el = trigger.value;
  if (!el) return;
  const r = el.getBoundingClientRect();
  panelStyle.value = {
    position: "fixed",
    top: `${r.bottom + 6}px`,
    left: `${r.left}px`,
    width: `${Math.max(r.width, 200)}px`,
  };
}
async function toggle() {
  open.value = !open.value;
  if (open.value) {
    keyword.value = "";
    await nextTick();
    place();
    window.addEventListener("scroll", place, true);
    window.addEventListener("resize", place);
  } else detach();
}
function detach() {
  window.removeEventListener("scroll", place, true);
  window.removeEventListener("resize", place);
}
function pick(o: Option) {
  emit("update:modelValue", o.value);
  open.value = false;
  keyword.value = "";
  detach();
}
onBeforeUnmount(detach);
</script>

<template>
  <div class="search-select" :class="{ open }">
    <button ref="trigger" type="button" class="ss-trigger" @click="toggle">
      <span>{{ current }}</span>
      <span class="ss-arrow">▾</span>
    </button>
    <Teleport to="body">
      <transition name="ss-fade">
        <div v-if="open" class="ss-panel" :style="panelStyle">
          <input v-model="keyword" class="ss-search" :placeholder="t('common.search')" />
          <ul class="ss-list">
            <li v-if="!filtered.length" class="ss-empty">{{ t("common.noMatch") }}</li>
            <li
              v-for="o in filtered"
              :key="o.value"
              class="ss-item"
              :class="{ active: o.value === modelValue }"
              @click="pick(o)"
            >
              {{ o.label }}
            </li>
          </ul>
        </div>
      </transition>
      <div v-if="open" class="ss-backdrop" @click="open = false; detach()" />
    </Teleport>
  </div>
</template>

<style scoped>
.search-select { position: relative; display: inline-block; min-width: 160px; }
.ss-trigger {
  width: 100%; display: flex; justify-content: space-between; align-items: center;
  gap: 8px; padding: 8px 12px; border-radius: 10px;
  background: var(--glass-bg); border: 1px solid var(--glass-border);
  color: var(--fg); cursor: pointer; backdrop-filter: blur(12px);
}
.ss-arrow { opacity: .7; transition: transform .2s; }
.search-select.open .ss-arrow { transform: rotate(180deg); }
.ss-fade-enter-active, .ss-fade-leave-active { transition: opacity .15s, transform .15s; }
.ss-fade-enter-from, .ss-fade-leave-to { opacity: 0; transform: translateY(-4px); }
</style>

<style>
/* teleport 到 body,需全局样式 */
.search-select ~ * .ss-panel, .ss-panel {
  z-index: 9999; background: var(--glass-bg-strong); border: 1px solid var(--glass-border);
  border-radius: 12px; padding: 8px; backdrop-filter: blur(20px);
  box-shadow: 0 8px 32px rgba(0,0,0,.25);
}
.ss-search {
  width: 100%; box-sizing: border-box; padding: 8px 10px; margin-bottom: 6px;
  border-radius: 8px; background: var(--glass-bg); border: 1px solid var(--glass-border);
  color: var(--fg); outline: none;
}
.ss-list { list-style: none; margin: 0; padding: 0; max-height: 240px; overflow-y: auto; }
.ss-item { padding: 8px 10px; border-radius: 8px; color: var(--fg); cursor: pointer; }
.ss-item:hover { background: rgba(255,255,255,.08); }
.ss-item.active { background: var(--accent); color: #fff; }
.ss-empty { padding: 10px; text-align: center; opacity: .6; color: var(--fg); }
.ss-backdrop { position: fixed; inset: 0; z-index: 9998; }
</style>
```

> 注:`.ss-*` class 名与 SymbolSelect 全局样式同名且样式一致,不冲突(值相同)。为避免与 SymbolSelect 的全局 `.ss-panel` 定义重复冲突,本组件的全局块保持相同属性值即可(CSS 后者覆盖前者但值一致,无副作用)。

- [ ] **Step 2: 确认 i18n 键 `common.search` 存在**

Run: `Grep "\"search\"|search:" frontend/src/locales`
若缺,在 zh 加 `search: "搜索"`,en 加 `search: "Search"`(与 `common.select`/`common.noMatch` 同段)。

- [ ] **Step 3: 构建通过**

Run: `cd /c/App/Project/quanly/frontend && npm run build 2>&1 | tail -15`
Expected: 成功。

---

## Task 4: GlassNumber 支持加宽尺寸

**Files:**
- Modify: `frontend/src/components/GlassNumber.vue`

- [ ] **Step 1: 加 `wide` 尺寸支持,金额场景数字左对齐、更宽**

在 GlassNumber `.glass-number` 样式补一个可选宽度。最简做法:给根 div 一个可控 min-width,并让金额输入不居中截断。修改样式块(第 38-52 行)为:

```css
.glass-number {
  display: inline-flex; align-items: stretch; border-radius: 10px; overflow: hidden;
  background: var(--glass-bg); border: 1px solid var(--glass-border);
  backdrop-filter: blur(12px); min-width: 160px;
}
.gn-btn {
  width: 34px; flex: none; border: none; background: transparent; color: var(--fg);
  font-size: 18px; cursor: pointer; transition: background .15s;
}
.gn-btn:hover { background: rgba(255,255,255,.1); }
.gn-input {
  flex: 1; min-width: 0; width: 100%; border: none; background: transparent; color: var(--fg);
  text-align: center; padding: 8px 6px; outline: none;
  font-variant-numeric: tabular-nums;
}
```

> 关键:`min-width: 160px` 保证两侧 34px 按钮后仍有 ~90px 显示数字;`gn-btn { flex: none }` 防止按钮被压缩。

- [ ] **Step 2: 构建通过**

Run: `cd /c/App/Project/quanly/frontend && npm run build 2>&1 | tail -15`
Expected: 成功。

---

## Task 5: Trade.vue — 去双边框 + 交易对可搜索 + 按 instType 过滤

**Files:**
- Modify: `frontend/src/views/Trade.vue`

- [ ] **Step 1: 引入 SearchSelect**

第 8 行 `import GlassSelect` 之后加:

```javascript
import SearchSelect from "@/components/SearchSelect.vue";
```

- [ ] **Step 2: symbolOptions 按 instType 过滤**

当前 `symbolOptions`(206-208 行)对非 ETF 一律用全量 `SYMBOLS.value`,应按品类后缀过滤。需要品类分组数据:改 onMounted 里的拉取,保存 by_type。在第 25 行 `SYMBOLS` 附近加:

```javascript
const SYMBOLS_BY_TYPE = ref<Record<string, string[]>>({});
```

onMounted 拉取(258-264 行)改为:

```javascript
  try {
    const r = await fetch("/api/market/symbols");
    const d = await r.json();
    if (d.by_type) {
      const bt: Record<string, string[]> = {};
      for (const k of Object.keys(d.by_type)) bt[k] = d.by_type[k].map((x: any) => x.instId);
      SYMBOLS_BY_TYPE.value = bt;
    }
    if (Array.isArray(d.symbols) && d.symbols.length) SYMBOLS.value = d.symbols;
  } catch {
    /* 保留默认 */
  }
```

`symbolOptions`(206-208 行)改为按品类:

```javascript
const symbolOptions = computed(() => {
  if (instType.value === "ETF") return ETF_SYMBOLS.map((s) => ({ label: s, value: s }));
  const list = SYMBOLS_BY_TYPE.value[instType.value] ?? SYMBOLS.value;
  return list.map((s) => ({ label: s, value: s }));
});
```

`watch(instType)`(226-230 行)里把 list 也改成分品类:

```javascript
watch(instType, (t) => {
  const list = t === "ETF" ? ETF_SYMBOLS : (SYMBOLS_BY_TYPE.value[t] ?? SYMBOLS.value);
  if (list.length && !list.includes(form.value.symbol)) form.value.symbol = list[0];
});
```

- [ ] **Step 3: 交易对换成 SearchSelect,并去掉所有 `class="input"`**

第 332 行交易对:

```html
        <SearchSelect v-model="form.symbol" :options="symbolOptions" />
```

第 320-325 行下单密钥的 GlassSelect 去掉 `class="input"`:

```html
        <GlassSelect
          v-if="credentials.length"
          v-model="credId"
          :options="credOptions"
        />
```

其余本文件中所有 `<GlassSelect ... class="input" />` 一律删掉 ` class="input"`。用 Grep 核对:`Grep 'class="input"' frontend/src/views/Trade.vue`,GlassSelect/GlassNumber/GlassSlider 上的都删。

> GlassNumber 上的 `class="input"` 也要删(它自带边框,`.input` 造成双框)。删后由组件 min-width 决定宽度。

- [ ] **Step 4: 构建通过**

Run: `cd /c/App/Project/quanly/frontend && npm run build 2>&1 | tail -15`
Expected: 成功,无类型错误。

---

## Task 6: Backtest.vue — 策略 + 交易对可搜索 + 去双边框

**Files:**
- Modify: `frontend/src/views/Backtest.vue`

- [ ] **Step 1: 引入 SearchSelect**

在 Backtest.vue 的 `import GlassSelect` 行之后加 `import SearchSelect from "@/components/SearchSelect.vue";`(先 `Grep "import GlassSelect" frontend/src/views/Backtest.vue` 定位行号)。

- [ ] **Step 2: 策略与交易对改 SearchSelect,去 `class="input"`**

第 209 行策略:

```html
          <SearchSelect v-model="cfg.strategy_id" :options="strategyOptions" />
```

第 213 行交易对:

```html
          <SearchSelect v-model="cfg.symbol" :options="symbolOptions" />
```

- [ ] **Step 3: 去掉本文件其余 Glass* 上的 `class="input"`**

`GlassNumber`(217/221/225 行)上的 `class="input"` 删掉。核对:`Grep 'class="input"' frontend/src/views/Backtest.vue` 应无残留(保留非 Glass 原生 input 的除外——本文件金额等都用 GlassNumber,故应全删)。

- [ ] **Step 4: 构建通过**

Run: `cd /c/App/Project/quanly/frontend && npm run build 2>&1 | tail -15`
Expected: 成功。

---

## Task 7: StrategyDetail.vue — 交易对可搜索 + 去双边框

**Files:**
- Modify: `frontend/src/views/StrategyDetail.vue`

- [ ] **Step 1: 引入 SearchSelect**

`import SearchSelect from "@/components/SearchSelect.vue";`(定位现有 import GlassSelect 行后插入)。

- [ ] **Step 2: 交易对改 SearchSelect,环境/密钥保持 GlassSelect 但去 `class="input"`**

第 144 行交易对:

```html
          <SearchSelect v-model="cfg.symbol" :options="symbolOptions" />
```

第 136 行环境、140 行密钥:删掉 ` class="input"`(保持 GlassSelect):

```html
          <GlassSelect v-model="cfg.env" :options="envOptions" />
          ...
          <GlassSelect v-model="cfg.credential_id" :options="credOptions" />
```

- [ ] **Step 3: 去掉本文件其余 Glass* 上的 `class="input"`**

`Grep 'class="input"' frontend/src/views/StrategyDetail.vue`,GlassNumber(如 interval_sec 的 148 行)等一并删。

- [ ] **Step 4: 构建通过**

Run: `cd /c/App/Project/quanly/frontend && npm run build 2>&1 | tail -15`
Expected: 成功。

---

## Task 8: Transfer.vue — 去双边框 + 金额加宽

**Files:**
- Modify: `frontend/src/views/Transfer.vue`

- [ ] **Step 1: 去掉三个 GlassSelect 与金额 GlassNumber 的 `class="input"`**

第 63/67/71 行(币种/转出/转入)与第 75-79 行金额 GlassNumber 上的 ` class="input"` 全删。改后:

```html
          <GlassSelect v-model="form.ccy" :options="ccyOptions" />
          ...
          <GlassSelect v-model="form.from_acct" :options="acctOptions" />
          ...
          <GlassSelect v-model="form.to_acct" :options="acctOptions" />
          ...
          <GlassNumber
            :model-value="form.amount"
            @update:modelValue="(v: number) => (form.amount = String(v))"
          />
```

- [ ] **Step 2: 构建通过**

Run: `cd /c/App/Project/quanly/frontend && npm run build 2>&1 | tail -15`
Expected: 成功。

---

## Task 9: Finance.vue — 金额加宽 + 去双边框

**Files:**
- Modify: `frontend/src/views/Finance.vue`

- [ ] **Step 1: 金额 GlassNumber 去 `class="input sm"`,改用组件自带宽度**

第 101-106 行:

```html
              <GlassNumber
                :model-value="amounts[p.id] ?? ''"
                @update:modelValue="(v: number) => (amounts[p.id] = String(v))"
                :placeholder="String(p.min_amount)"
              />
```

- [ ] **Step 2: 删除失效的 `.input.sm` 宽度约束**

第 161 行 `.input.sm { width: 110px; padding: 6px 8px; }` 删除(已无引用)。若 `.sm`(162 行)仍被按钮 `btn sm` 使用则保留。

- [ ] **Step 3: 构建通过**

Run: `cd /c/App/Project/quanly/frontend && npm run build 2>&1 | tail -15`
Expected: 成功。

---

## Task 10: 重建前端容器 + 后端热更 + 浏览器实测

**Files:** 无(集成验证)

- [ ] **Step 1: 重建前端与后端镜像并起来**

Run:
```bash
cd /c/App/Project/quanly
docker compose -f docker-compose.yml -f docker-compose.local.yml --env-file .env.prod up -d --no-deps --build frontend backend
docker compose -f docker-compose.yml -f docker-compose.local.yml --env-file .env.prod exec -T redis redis-cli DEL market:instruments:v2
```
Expected: frontend/backend 重建并 Up。

- [ ] **Step 2: 验证 candles 接口对 FUTURES 有数据**

Run:
```bash
curl -s "http://localhost:8080/api/market/symbols" | python -c "import sys,json;d=json.load(sys.stdin);print('FUTURES first=', d['by_type']['FUTURES'][0]['instId'])"
```
取到 sym 后:
```bash
curl -s "http://localhost:8080/api/market/<FUTURES-sym>/candles?bar=1m&limit=5" | python -c "import sys,json;print('candles=', len(json.load(sys.stdin)['candles']))"
```
Expected: `candles= 5`(非 0)。

- [ ] **Step 3: 浏览器实测清单(逐条勾)**

打开 `http://localhost:8080` 登录后:
- 行情:切换 SPOT/SWAP/FUTURES/OPTION 不同交易对,K线都能显示;无数据的合约显示"该合约暂无 K线数据"提示;时间轴显示北京时间。
- 交易:下单密钥、交易对不再是"框套框";交易对可搜索;切品类交易对列表随之变化。
- 策略:环境/密钥/交易对不再双框;交易对可搜索。
- 回测:策略、交易对可搜索;无双框。
- 划账:币种/转出/转入不再双框;金额框够宽显示完整数字。
- 理财+借贷:两个 tab 的金额框够宽,输入 10000.5678 能看全。
- API 页:模拟盘/实盘切换(本就是按钮,非嵌套框)确认外观与其他一致。

- [ ] **Step 4: 交付核验报告**

逐条汇总 4 个需求达成情况,向用户报告。

---

## Self-Review

**1. Spec coverage:**
- 需求1 K线切换空白 → Task 1(实盘数据)+ Task 2(空数据提示)✅;中国时间 → Task 2 ✅
- 需求2 各板块下拉"框套框" → Task 5-9 去 `class="input"` ✅;API 模拟/实盘切换本是按钮非嵌套,Task 10 Step 3 目视确认 ✅
- 需求3 理财/借贷金额框太小 → Task 4(GlassNumber min-width)+ Task 9 去 sm 约束 ✅
- 需求4 交易/回测/策略交易对+回测策略可搜索 → Task 3(SearchSelect)+ Task 5/6/7 ✅

**2. Placeholder scan:** 无 TBD;每个改动含完整代码/命令与预期输出。i18n 键 Task 2 Step 4、Task 3 Step 2 均给出定位与兜底添加方式。

**3. 命名一致性:**
- `SearchSelect` 组件名、props(`modelValue/options/placeholder`)在 Task 3 定义,Task 5-7 引用一致。
- `SYMBOLS_BY_TYPE`(Task 5 新增)在 symbolOptions/watch 引用一致。
- 后端 `Env.LIVE` 三处一致(Task 1)。
- CandleChart 的 `empty` ref + `market.noCandles` 键 Task 2 内自洽。

**风险点:** SearchSelect 与 SymbolSelect 共用 `.ss-*` 全局 class 名。二者样式值相同,浏览器合并无副作用;但若后续改其一样式需注意另一处。Task 3 Step 1 注释已标注。
