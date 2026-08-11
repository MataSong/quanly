<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from "vue";
import {
  createChart,
  LineSeries,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import { backtestApi } from "@/api/backtest";
import { strategyApi } from "@/api/strategy";
import Pagination from "@/components/Pagination.vue";
import SearchSelect from "@/components/SearchSelect.vue";
import GlassNumber from "@/components/GlassNumber.vue";
import GlassCheckbox from "@/components/GlassCheckbox.vue";
import { usePagination } from "@/composables/usePagination";

const strategies = ref<any[]>([]);
const history = ref<any[]>([]);
const {
  page: histPage, pageSize: histSize, total: histTotal,
  totalPages: histPages, paged: histPaged,
} = usePagination(history, 10);
const running = ref(false);
const metrics = ref<any>(null);
const activeId = ref<number | "current" | null>(null);

const cfg = ref({
  strategy_id: null as number | null,
  symbol: "BTC-USDT",
  bar: "1m",
  bars: 500,
  initial_capital: 10000,
  fee_rate: 0.0005,
});

const symbols = ref<string[]>(["BTC-USDT", "ETH-USDT", "SOL-USDT"]);
const strategyOptions = computed(() =>
  strategies.value.map((s) => ({ label: s.name, value: s.id }))
);
const symbolOptions = computed(() => symbols.value.map((s) => ({ label: s, value: s })));

const chartEl = ref<HTMLDivElement | null>(null);
let chart: IChartApi | null = null;
// 已叠加在图上的曲线:key -> series。key 为 backtest id 或 "current"
const drawn = new Map<number | "current", ISeriesApi<"Line">>();
// 勾选叠加对比的历史 id 集合
const compared = ref<Set<number>>(new Set());
// 结果缓存,避免重复请求
const cache = new Map<number | "current", any>();

const PALETTE = ["#0a84ff", "#30d158", "#ff9f0a", "#bf5af2", "#ff453a", "#64d2ff"];

const METRIC_DEFS = [
  { key: "total_return", pct: true, pnl: true },
  { key: "annual_return", pct: true, pnl: true },
  { key: "final_equity", pct: false, pnl: false },
  { key: "max_drawdown", pct: true, pnl: true },
  { key: "max_dd_duration", pct: false, pnl: false },
  { key: "annual_volatility", pct: true, pnl: false },
  { key: "downside_volatility", pct: true, pnl: false },
  { key: "sharpe", pct: false, pnl: true },
  { key: "sortino", pct: false, pnl: true },
  { key: "calmar", pct: false, pnl: true },
  { key: "win_rate", pct: true, pnl: false },
  { key: "profit_factor", pct: false, pnl: false },
  { key: "trade_count", pct: false, pnl: false },
  { key: "closed_trades", pct: false, pnl: false },
  { key: "win_count", pct: false, pnl: false },
  { key: "loss_count", pct: false, pnl: false },
  { key: "avg_win", pct: false, pnl: true },
  { key: "avg_loss", pct: false, pnl: true },
  { key: "max_win", pct: false, pnl: true },
  { key: "max_loss", pct: false, pnl: true },
];

function fmtMetric(def: any, v: number): string {
  if (v === undefined || v === null) return "—";
  return def.pct ? (v * 100).toFixed(2) + "%" : Number(v).toLocaleString();
}

function ensureChart() {
  if (chart || !chartEl.value) return;
  const dark = document.documentElement.dataset.theme !== "light";
  chart = createChart(chartEl.value, {
    layout: { background: { color: "transparent" }, textColor: dark ? "#9a9aa5" : "#6e6e73" },
    grid: {
      vertLines: { color: dark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.06)" },
      horzLines: { color: dark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.06)" },
    },
    autoSize: true,
    timeScale: { timeVisible: true },
  });
}

function colorFor(key: number | "current") {
  const keys = [...drawn.keys()];
  const idx = keys.indexOf(key);
  return PALETTE[(idx < 0 ? keys.length : idx) % PALETTE.length];
}

function addCurve(key: number | "current", curve: any[]) {
  ensureChart();
  if (!chart || drawn.has(key)) return;
  const s = chart.addSeries(LineSeries, { color: colorFor(key), lineWidth: 2 });
  s.setData(curve.map((p) => ({ time: (p.ts / 1000) as UTCTimestamp, value: p.equity })));
  drawn.set(key, s);
  const w = chartEl.value!.clientWidth || 600;
  chart.resize(w, 380);
  chart.timeScale().fitContent();
}

function removeCurve(key: number | "current") {
  const s = drawn.get(key);
  if (s && chart) chart.removeSeries(s);
  drawn.delete(key);
}

function clearExtraCurves(keep: number | "current") {
  for (const key of [...drawn.keys()]) {
    if (key !== keep && !(typeof key === "number" && compared.value.has(key))) {
      removeCurve(key);
    }
  }
}

async function fetchResult(key: number | "current") {
  if (cache.has(key)) return cache.get(key);
  if (key === "current") return null;
  const r = await backtestApi.detail(key);
  cache.set(key, r.data);
  return r.data;
}

// 单击历史:作为主选中,展示其指标 + 主曲线(保留已勾选的对比曲线)
async function viewHistory(id: number) {
  activeId.value = id;
  const data = await fetchResult(id);
  metrics.value = data.metrics;
  await nextTick();
  clearExtraCurves(id);
  addCurve(id, data.result.equity_curve);
}

// 勾选/取消:叠加或移除对比曲线
async function toggleCompare(id: number) {
  if (compared.value.has(id)) {
    compared.value.delete(id);
    if (id !== activeId.value) removeCurve(id);
  } else {
    compared.value.add(id);
    const data = await fetchResult(id);
    await nextTick();
    addCurve(id, data.result.equity_curve);
  }
  compared.value = new Set(compared.value);
}

async function loadStrategies() {
  const r = await strategyApi.list();
  strategies.value = r.data;
  cfg.value.strategy_id = strategies.value[0]?.id ?? null;
}

async function loadHistory() {
  const r = await backtestApi.list();
  history.value = r.data;
}

async function runBacktest() {
  running.value = true;
  try {
    const r = await backtestApi.run(cfg.value);
    const data = { result: r.data.result, metrics: r.data.metrics, name: r.data.name };
    cache.set("current", data);
    metrics.value = data.metrics;
    activeId.value = "current";
    compared.value = new Set();
    await nextTick();
    // 清掉所有曲线,只画当前
    for (const key of [...drawn.keys()]) removeCurve(key);
    addCurve("current", data.result.equity_curve);
    await loadHistory();
  } finally {
    running.value = false;
  }
}

onMounted(async () => {
  try {
    const r = await fetch("/api/market/symbols");
    const d = await r.json();
    if (Array.isArray(d.symbols) && d.symbols.length) symbols.value = d.symbols;
  } catch {
    /* 保留默认 */
  }
  await loadStrategies();
  await loadHistory();
});
</script>

<template>
  <div class="wrap">
    <div class="glass panel">
      <h2>{{ $t("backtest.title") }}</h2>
      <div class="form">
        <div class="fld">
          <label>{{ $t("backtest.strategy") }}</label>
          <SearchSelect v-model="cfg.strategy_id" :options="strategyOptions" />
        </div>
        <div class="fld">
          <label>{{ $t("trade.symbol") }}</label>
          <SearchSelect v-model="cfg.symbol" :options="symbolOptions" />
        </div>
        <div class="fld">
          <label>{{ $t("backtest.bars") }}</label>
          <GlassNumber v-model="cfg.bars" :min="1" />
        </div>
        <div class="fld">
          <label>{{ $t("backtest.capital") }}</label>
          <GlassNumber v-model="cfg.initial_capital" :min="0" />
        </div>
        <div class="fld">
          <label>{{ $t("backtest.fee") }}</label>
          <GlassNumber v-model="cfg.fee_rate" :step="0.0001" :min="0" />
        </div>
        <div class="fld btns">
          <button class="btn" :disabled="running" @click="runBacktest">
            {{ running ? $t("backtest.running") : $t("backtest.run") }}
          </button>
        </div>
      </div>
    </div>

    <div class="glass panel">
      <h3>{{ $t("backtest.equityCurve") }}</h3>
      <div ref="chartEl" class="chart"></div>
    </div>
    <div class="glass panel" v-if="metrics">
      <h3>{{ $t("backtest.metrics") }}</h3>
      <div class="metrics">
        <div v-for="d in METRIC_DEFS" :key="d.key" class="metric">
          <div class="m-label">{{ $t("backtest.m." + d.key) }}</div>
          <div class="m-val" :class="d.pnl ? (metrics[d.key] >= 0 ? 'up' : 'down') : ''">
            {{ fmtMetric(d, metrics[d.key]) }}
          </div>
        </div>
      </div>
    </div>

    <!-- 历史回测(分页表格,单击查看 / 勾选叠加对比)-->
    <div class="glass panel">
      <h3>{{ $t("backtest.history") }}</h3>
      <p class="hint">{{ $t("backtest.compareHint") }}</p>
      <table class="tbl">
        <thead>
          <tr>
            <th>{{ $t("backtest.compare") }}</th>
            <th>{{ $t("backtest.strategy") }}</th>
            <th>{{ $t("trade.symbol") }}</th>
            <th>{{ $t("backtest.bars") }}</th>
            <th>{{ $t("bills.time") }}</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="h in histPaged" :key="h.id" :class="{ active: activeId === h.id }">
            <td>
              <GlassCheckbox
                :model-value="compared.has(h.id)"
                @update:modelValue="() => toggleCompare(h.id)"
              />
            </td>
            <td>{{ h.name }}</td>
            <td>{{ h.symbol }}</td>
            <td>{{ h.bars }}</td>
            <td>{{ new Date(h.created_at).toLocaleString() }}</td>
            <td>
              <button class="btn btn-ghost sm" @click="viewHistory(h.id)">
                {{ $t("backtest.view") }}
              </button>
            </td>
          </tr>
          <tr v-if="histTotal === 0">
            <td colspan="6" class="empty">{{ $t("backtest.noHistory") }}</td>
          </tr>
        </tbody>
      </table>
      <Pagination
        v-if="histTotal > 0"
        v-model:page="histPage"
        v-model:pageSize="histSize"
        :total="histTotal"
        :totalPages="histPages"
      />
    </div>
  </div>
</template>

<style scoped>
.wrap {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.panel {
  padding: 20px;
}
h2,
h3 {
  margin: 0 0 14px;
}
.form {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: flex-end;
}
.fld {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.fld label {
  font-size: 12px;
  color: var(--fg-dim);
}
.grid {
  display: grid;
  grid-template-columns: 1fr 260px;
  gap: 16px;
}
@media (max-width: 900px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
.left {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}
.chart {
  width: 100%;
  height: 380px;
}
.metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 12px;
}
.metric {
  background: var(--glass-bg-strong);
  border-radius: 10px;
  padding: 12px;
}
.m-label {
  font-size: 12px;
  color: var(--fg-dim);
}
.m-val {
  font-size: 18px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  margin-top: 4px;
}
.up {
  color: #30d158;
}
.down {
  color: #ff453a;
}
.history {
  align-self: start;
}
.hint {
  font-size: 12px;
  color: var(--fg-dim);
  margin: 0 0 12px;
}
.tbl {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.tbl th,
.tbl td {
  text-align: left;
  padding: 9px 6px;
  border-bottom: 1px solid var(--glass-border);
}
.tbl th {
  color: var(--fg-dim);
  font-weight: 600;
}
.tbl tr.active {
  background: var(--glass-bg-strong);
}
.empty {
  text-align: center;
  color: var(--fg-dim);
  padding: 16px;
}
.sm {
  padding: 4px 10px;
  font-size: 12px;
}
.hist-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 6px;
  border-radius: 8px;
  border-bottom: 1px solid var(--glass-border);
}
.hist-row.active {
  background: var(--glass-bg-strong);
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.hist-name {
  font-size: 13px;
  cursor: pointer;
  line-height: 1.3;
}
.hist-name small {
  color: var(--fg-dim);
  font-size: 11px;
}
</style>
