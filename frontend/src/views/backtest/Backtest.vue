<template>
  <div class="backtest-page">
    <!-- Page header -->
    <div class="page-header">
      <h2 class="page-title">{{ t("backtest.title") }}</h2>
      <el-button type="primary" :icon="Plus" @click="openCreateDialog">
        {{ t("backtest.newBacktest") }}
      </el-button>
    </div>

    <!-- Error banner -->
    <el-alert
      v-if="pageError"
      :title="pageError"
      type="error"
      show-icon
      closable
      @close="pageError = ''"
    />

    <!-- My backtests table -->
    <div class="card">
      <div class="card-title-row">
        <span class="card-title">{{ t("backtest.title") }}</span>
        <el-button size="small" :loading="listLoading" @click="loadList">
          {{ t("common.refresh") }}
        </el-button>
      </div>
      <div class="table-scroll">
        <el-table
          :data="backtests"
          size="small"
          border
          v-loading="listLoading"
          empty-text=""
          highlight-current-row
          @current-change="onRowSelect"
        >
          <el-table-column :label="t('backtest.colStrategy')" min-width="130">
            <template #default="{ row }">{{ row.strategy_name ?? row.strategy }}</template>
          </el-table-column>
          <el-table-column :label="t('backtest.colSymbol')" width="130">
            <template #default="{ row }">{{ row.symbol }}</template>
          </el-table-column>
          <el-table-column :label="t('backtest.colBar')" width="80" align="center">
            <template #default="{ row }">{{ row.bar }}</template>
          </el-table-column>
          <el-table-column :label="t('backtest.colStatus')" width="100" align="center">
            <template #default="{ row }">
              <el-tag :type="statusTagType(row.status)" size="small">
                {{ t(`backtest.status.${row.status}`) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="t('backtest.colTotalReturn')" width="110" align="right">
            <template #default="{ row }">
              <span
                v-if="row.metrics?.total_return != null"
                :class="row.metrics.total_return >= 0 ? 'pnl-pos' : 'pnl-neg'"
              >
                {{ fmtPct(row.metrics.total_return) }}
              </span>
              <span v-else class="text-muted">—</span>
            </template>
          </el-table-column>
          <el-table-column :label="t('common.createdAt')" width="160">
            <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
          </el-table-column>
        </el-table>
      </div>
      <el-empty
        v-if="!backtests.length && !listLoading"
        :description="t('common.empty')"
        style="padding: 20px 0"
      />
    </div>

    <!-- Result area -->
    <template v-if="selectedBacktest">
      <!-- Running / pending -->
      <div v-if="selectedBacktest.status === 'pending' || selectedBacktest.status === 'running'" class="card result-running">
        <el-icon class="spinning"><Loading /></el-icon>
        <span>{{ t("backtest.running") }}</span>
      </div>

      <!-- Error -->
      <div v-else-if="selectedBacktest.status === 'error'" class="card">
        <el-alert
          :title="t('backtest.errorTitle')"
          :description="selectedBacktest.error_msg ?? ''"
          type="error"
          show-icon
          :closable="false"
        />
      </div>

      <!-- Done -->
      <template v-else-if="selectedBacktest.status === 'done' && detail">
        <!-- Metrics cards -->
        <div class="metrics-grid">
          <div class="metric-card card">
            <div class="metric-label">{{ t("backtest.metrics.totalReturn") }}</div>
            <div class="metric-value" :class="metricClass(detail.metrics?.total_return)">
              {{ fmtPct(detail.metrics?.total_return) }}
            </div>
          </div>
          <div class="metric-card card">
            <div class="metric-label">{{ t("backtest.metrics.annualizedReturn") }}</div>
            <div class="metric-value" :class="metricClass(detail.metrics?.annualized_return)">
              {{ fmtPct(detail.metrics?.annualized_return) }}
            </div>
          </div>
          <div class="metric-card card">
            <div class="metric-label">{{ t("backtest.metrics.maxDrawdown") }}</div>
            <div class="metric-value pnl-neg">
              {{ fmtPct(detail.metrics?.max_drawdown) }}
            </div>
          </div>
          <div class="metric-card card">
            <div class="metric-label">{{ t("backtest.metrics.sharpe") }}</div>
            <div class="metric-value">
              {{ fmtNum(detail.metrics?.sharpe) }}
            </div>
          </div>
          <div class="metric-card card">
            <div class="metric-label">{{ t("backtest.metrics.winRate") }}</div>
            <div class="metric-value">
              {{ fmtPct(detail.metrics?.win_rate) }}
            </div>
          </div>
          <div class="metric-card card">
            <div class="metric-label">{{ t("backtest.metrics.profitFactor") }}</div>
            <div class="metric-value">
              {{ detail.metrics?.profit_factor == null ? "∞" : fmtNum(detail.metrics.profit_factor) }}
            </div>
          </div>
          <div class="metric-card card">
            <div class="metric-label">{{ t("backtest.metrics.tradeCount") }}</div>
            <div class="metric-value">{{ detail.metrics?.trade_count ?? "—" }}</div>
          </div>
        </div>

        <!-- Equity curve chart -->
        <div class="card">
          <div class="card-title-row">
            <span class="card-title">{{ t("backtest.equityCurve") }}</span>
          </div>
          <div class="chart-wrap">
            <div v-if="!detail.equity_curve.length" class="chart-empty">
              {{ t("common.empty") }}
            </div>
            <div v-else ref="chartContainer" class="chart-container" />
          </div>
        </div>

        <!-- Trades table -->
        <div class="card">
          <div class="card-title-row">
            <span class="card-title">{{ t("backtest.trades") }}</span>
          </div>
          <ResponsiveTable
            :columns="tradesCols"
            :data="detail.trades"
            :empty-text="t('common.empty')"
          >
            <template #cell-side="{ row }">
              <el-tag :type="row.side === 'buy' ? 'success' : 'danger'" size="small">
                {{ row.side === "buy" ? t("backtest.buy") : t("backtest.sell") }}
              </el-tag>
            </template>
            <template #cell-pnl="{ row }">
              <span :class="row.pnl >= 0 ? 'pnl-pos' : 'pnl-neg'">{{ fmtNum(row.pnl) }}</span>
            </template>
          </ResponsiveTable>
        </div>
      </template>
    </template>

    <!-- Create backtest dialog -->
    <el-dialog
      v-model="createDialogVisible"
      :title="t('backtest.newBacktest')"
      :width="dialogWidth"
      :close-on-click-modal="false"
    >
      <el-form :model="form" label-width="110px" :label-position="isMobile ? 'top' : 'right'">
        <!-- Strategy -->
        <el-form-item :label="t('backtest.strategy')">
          <el-select
            v-model="form.strategy_id"
            style="width: 100%"
            :loading="strategiesLoading"
            @change="onStrategyChange"
          >
            <el-option
              v-for="s in strategies"
              :key="s.id"
              :value="s.id"
              :label="s.name"
            />
          </el-select>
        </el-form-item>

        <!-- Symbol -->
        <el-form-item :label="t('backtest.symbol')">
          <el-select
            v-if="!symbolFallback"
            v-model="form.symbol"
            filterable
            allow-create
            :loading="symbolsLoading"
            :placeholder="t('backtest.symbolPlaceholder')"
            style="width: 100%"
            default-first-option
          >
            <el-option
              v-for="sym in symbols"
              :key="sym.instId"
              :value="sym.instId"
              :label="sym.instId"
            />
          </el-select>
          <template v-else>
            <el-input v-model="form.symbol" placeholder="BTC-USDT" />
            <div class="hint-text">{{ t("backtest.symbolFallbackHint") }}</div>
          </template>
        </el-form-item>

        <!-- Bar -->
        <el-form-item :label="t('backtest.bar')">
          <el-select v-model="form.bar" style="width: 100%">
            <el-option v-for="b in BAR_OPTIONS" :key="b" :label="b" :value="b" />
          </el-select>
        </el-form-item>

        <!-- Date range -->
        <el-form-item :label="t('backtest.dateRange')">
          <el-date-picker
            v-model="form.dateRange"
            type="datetimerange"
            :range-separator="t('backtest.rangeSep')"
            :start-placeholder="t('backtest.rangeStart')"
            :end-placeholder="t('backtest.rangeEnd')"
            style="width: 100%"
            value-format="x"
          />
        </el-form-item>

        <!-- dual_ma params -->
        <template v-if="isDualMa">
          <el-form-item :label="t('strategy.fastPeriod')">
            <el-input-number
              v-model="(form.params as Record<string,number>).fast_period"
              :min="1"
              :max="200"
              style="width: 100%"
            />
          </el-form-item>
          <el-form-item :label="t('strategy.slowPeriod')">
            <el-input-number
              v-model="(form.params as Record<string,number>).slow_period"
              :min="1"
              :max="500"
              style="width: 100%"
            />
          </el-form-item>
          <el-form-item :label="t('strategy.sz')">
            <el-input v-model="(form.params as Record<string,unknown>).sz" placeholder="0.01" />
          </el-form-item>
        </template>

        <!-- Init cash -->
        <el-form-item :label="t('backtest.initCash')">
          <el-input-number
            v-model="form.init_cash"
            :min="1"
            :step="1000"
            style="width: 100%"
          />
        </el-form-item>

        <!-- Fee rate -->
        <el-form-item :label="t('backtest.feeRate')">
          <el-input-number
            v-model="form.fee_rate"
            :min="0"
            :max="0.1"
            :step="0.0001"
            :precision="4"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="createDialogVisible = false">{{ t("common.cancel") }}</el-button>
        <el-button type="primary" :loading="creating" @click="onCreateBacktest">
          {{ t("common.create") }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage } from "element-plus";
import { Loading, Plus } from "@element-plus/icons-vue";
import { createChart, LineSeries } from "lightweight-charts";
import type { IChartApi, ISeriesApi } from "lightweight-charts";
import {
  createBacktest,
  listBacktests,
  getBacktest,
  type BacktestItem,
  type BacktestDetail,
} from "@/api/backtest";
import { listStrategies, type Strategy } from "@/api/strategy";
import { getSymbols, type Symbol as MarketSymbol } from "@/api/market";
import { formatApiError } from "@/utils/errors";
import { useBreakpoint } from "@/composables/useBreakpoint";
import ResponsiveTable, { type RTColumn } from "@/components/ResponsiveTable.vue";

const { t } = useI18n();
const { isMobile } = useBreakpoint();

const dialogWidth = computed(() => isMobile.value ? '92%' : '520px');

const BAR_OPTIONS = ["1m", "5m", "15m", "1H", "4H", "1D"];

// ── List ──────────────────────────────────────────────────────────────────────

const backtests = ref<BacktestItem[]>([]);
const listLoading = ref(false);
const pageError = ref("");

async function loadList() {
  listLoading.value = true;
  try {
    backtests.value = await listBacktests();
  } catch (e) {
    pageError.value = formatApiError(e, "backtest");
  } finally {
    listLoading.value = false;
  }
}

// ── Selection + detail ────────────────────────────────────────────────────────

const selectedBacktest = ref<BacktestItem | null>(null);
const detail = ref<BacktestDetail | null>(null);

// Poll state for pending/running backtests
let pollTimer: ReturnType<typeof setInterval> | null = null;

function stopPoll() {
  if (pollTimer !== null) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

async function loadDetail(id: number) {
  try {
    const d = await getBacktest(id);
    detail.value = d;
    // Update the list row too so status tag refreshes
    const idx = backtests.value.findIndex((b) => b.id === id);
    if (idx !== -1) {
      backtests.value[idx] = { ...backtests.value[idx], status: d.status, metrics: d.metrics };
    }
    if (selectedBacktest.value?.id === id) {
      selectedBacktest.value = { ...selectedBacktest.value, status: d.status, metrics: d.metrics };
    }
    if (d.status === "done" || d.status === "error") {
      stopPoll();
      if (d.status === "done") {
        // Wait for DOM then render chart
        await nextTick();
        renderChart(d);
      }
    }
  } catch (e) {
    console.warn("loadDetail error:", e);
  }
}

function startPoll(id: number) {
  stopPoll();
  pollTimer = setInterval(() => {
    void loadDetail(id);
  }, 2000);
}

async function onRowSelect(row: BacktestItem | null) {
  stopPoll();
  detail.value = null;
  destroyChart();
  if (!row) {
    selectedBacktest.value = null;
    return;
  }
  selectedBacktest.value = row;
  if (row.status === "done" || row.status === "error") {
    await loadDetail(row.id);
  } else if (row.status === "pending" || row.status === "running") {
    startPoll(row.id);
    await loadDetail(row.id);
  }
}

// Watch for status to become "done" so we can render the chart
watch(
  () => detail.value?.status,
  async (newStatus) => {
    if (newStatus === "done" && detail.value) {
      await nextTick();
      renderChart(detail.value);
    }
  },
);

// ── Chart ─────────────────────────────────────────────────────────────────────

const chartContainer = ref<HTMLElement | null>(null);
let chart: IChartApi | null = null;
let lineSeries: ISeriesApi<"Line"> | null = null;
let resizeObserver: ResizeObserver | null = null;

function destroyChart() {
  resizeObserver?.disconnect();
  resizeObserver = null;
  if (chart) {
    chart.remove();
    chart = null;
    lineSeries = null;
  }
}

function renderChart(d: BacktestDetail) {
  if (!chartContainer.value) return;
  destroyChart();

  chart = createChart(chartContainer.value, {
    width: chartContainer.value.clientWidth,
    height: isMobile.value ? 240 : 320,
    layout: {
      background: { color: "#ffffff" },
      textColor: "#333",
    },
    grid: {
      vertLines: { color: "#f0f0f0" },
      horzLines: { color: "#f0f0f0" },
    },
    timeScale: {
      timeVisible: true,
      secondsVisible: false,
    },
  });

  lineSeries = chart.addSeries(LineSeries, {
    color: "#635bff",
    lineWidth: 2,
  });

  const chartData = d.equity_curve.map((pt) => ({
    time: Math.floor(pt.ts / 1000) as unknown as import("lightweight-charts").Time,
    value: pt.equity,
  }));

  lineSeries.setData(chartData);
  chart.timeScale().fitContent();

  resizeObserver = new ResizeObserver((entries) => {
    for (const entry of entries) {
      chart?.applyOptions({ width: entry.contentRect.width, height: isMobile.value ? 240 : 320 });
    }
  });
  resizeObserver.observe(chartContainer.value);
}

// ── Strategies + Symbols ──────────────────────────────────────────────────────

const strategies = ref<Strategy[]>([]);
const strategiesLoading = ref(false);

async function loadStrategiesList() {
  strategiesLoading.value = true;
  try {
    strategies.value = await listStrategies();
  } catch (e) {
    console.warn("loadStrategies error:", e);
  } finally {
    strategiesLoading.value = false;
  }
}

const symbols = ref<MarketSymbol[]>([]);
const symbolsLoading = ref(false);
const symbolFallback = ref(false);

async function loadSymbols() {
  symbolsLoading.value = true;
  try {
    symbols.value = await getSymbols();
    symbolFallback.value = symbols.value.length === 0;
  } catch {
    symbolFallback.value = true;
  } finally {
    symbolsLoading.value = false;
  }
}

// ── Create dialog ─────────────────────────────────────────────────────────────

const createDialogVisible = ref(false);
const creating = ref(false);

const form = reactive<{
  strategy_id: number | null;
  symbol: string;
  bar: string;
  dateRange: [number, number] | null;
  params: Record<string, unknown>;
  init_cash: number;
  fee_rate: number;
}>({
  strategy_id: null,
  symbol: "BTC-USDT",
  bar: "1H",
  dateRange: null,
  params: { fast_period: 5, slow_period: 20, sz: "0.01" },
  init_cash: 10000,
  fee_rate: 0.001,
});

const isDualMa = computed<boolean>(() => {
  const s = strategies.value.find((s) => s.id === form.strategy_id);
  return s?.code_ref === "dual_ma" || s?.name?.toLowerCase().includes("双均线") || false;
});

function onStrategyChange() {
  const s = strategies.value.find((x) => x.id === form.strategy_id);
  if (s?.default_params) {
    Object.assign(form.params, s.default_params);
  }
}

function openCreateDialog() {
  if (strategies.value.length && form.strategy_id === null) {
    form.strategy_id = strategies.value[0].id;
    onStrategyChange();
  }
  createDialogVisible.value = true;
}

async function onCreateBacktest() {
  if (!form.strategy_id) {
    ElMessage.warning(t("backtest.selectStrategyHint"));
    return;
  }
  if (!form.symbol.trim()) {
    ElMessage.warning(t("backtest.symbolRequired"));
    return;
  }
  if (!form.dateRange) {
    ElMessage.warning(t("backtest.dateRangeRequired"));
    return;
  }

  creating.value = true;
  try {
    const item = await createBacktest({
      strategy_id: form.strategy_id!,
      symbol: form.symbol.trim(),
      bar: form.bar,
      start_ts: form.dateRange[0],
      end_ts: form.dateRange[1],
      params: { ...form.params },
      init_cash: form.init_cash,
      fee_rate: form.fee_rate,
    });
    ElMessage.success(t("backtest.createSuccess"));
    createDialogVisible.value = false;
    await loadList();
    // Auto-select the new backtest and start polling
    selectedBacktest.value = item;
    detail.value = null;
    destroyChart();
    startPoll(item.id);
    await loadDetail(item.id);
  } catch (e) {
    ElMessage.error(formatApiError(e, "backtest"));
  } finally {
    creating.value = false;
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function statusTagType(status: string): "" | "success" | "danger" | "warning" | "info" {
  switch (status) {
    case "done": return "success";
    case "error": return "danger";
    case "running": return "warning";
    default: return "info"; // pending
  }
}

function metricClass(v: number | null | undefined): string {
  if (v == null) return "";
  return v >= 0 ? "pnl-pos" : "pnl-neg";
}

function fmtPct(v: number | null | undefined): string {
  if (v == null) return "—";
  return (v * 100).toFixed(2) + "%";
}

function fmtNum(v: number | null | undefined): string {
  if (v == null) return "—";
  return v.toFixed(4);
}

function formatDate(iso: string): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

function formatTs(ts: number): string {
  if (!ts) return "—";
  return new Date(ts).toLocaleString();
}

// ── Responsive table columns ──────────────────────────────────────────────────

const tradesCols = computed<RTColumn[]>(() => [
  { prop: "side", label: t("backtest.colSide"), width: 70, align: "center" },
  { prop: "ts", label: t("backtest.colTime"), width: 160,
    formatter: (row) => formatTs(row.ts) },
  { prop: "price", label: t("backtest.colPrice"), width: 120, align: "right",
    formatter: (row) => fmtNum(row.price) },
  { prop: "sz", label: t("backtest.colSz"), width: 100, align: "right",
    formatter: (row) => fmtNum(row.sz) },
  { prop: "fee", label: t("backtest.colFee"), width: 100, align: "right",
    formatter: (row) => fmtNum(row.fee) },
  { prop: "pnl", label: t("backtest.colPnl"), width: 110, align: "right" },
]);

// ── Lifecycle ─────────────────────────────────────────────────────────────────

watch(isMobile, (mobile) => {
  chart?.applyOptions({ height: mobile ? 240 : 320 });
});

onMounted(async () => {
  await Promise.all([loadList(), loadStrategiesList(), loadSymbols()]);
});

onUnmounted(() => {
  stopPoll();
  destroyChart();
});
</script>

<style scoped>
.backtest-page {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.page-title {
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: 600;
  color: var(--gray-800);
}

.card {
  background: #fff;
  border: 1px solid var(--gray-200);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
}

.table-scroll {
  overflow-x: auto;
}

.card-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-3);
}

.card-title {
  font-size: var(--font-size-md);
  font-weight: 600;
  color: var(--gray-700);
}

/* Metrics */
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: var(--space-4);
}

.metric-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-4);
  text-align: center;
}

.metric-label {
  font-size: var(--font-size-xs);
  color: var(--gray-500);
  white-space: nowrap;
}

.metric-value {
  font-size: var(--font-size-lg);
  font-weight: 700;
  color: var(--gray-800);
}

/* P&L colors */
.pnl-pos { color: #26a69a; }
.pnl-neg { color: #ef5350; }
.text-muted { color: var(--gray-400); }

/* Chart */
.chart-wrap {
  position: relative;
  min-height: 330px;
  background: #fff;
  border-radius: var(--radius-md);
  overflow: hidden;
}

@media (max-width: 768px) {
  .chart-wrap { min-height: 250px; }
}

.chart-container {
  width: 100%;
}

.chart-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
  color: var(--gray-400);
  font-size: var(--font-size-sm);
}

/* Running spinner */
.result-running {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  color: var(--gray-600);
  font-size: var(--font-size-md);
}

.spinning {
  animation: spin 1s linear infinite;
  font-size: 20px;
  color: var(--brand-primary, #635bff);
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.hint-text {
  font-size: 12px;
  color: var(--gray-400);
  margin-top: 4px;
}
</style>
