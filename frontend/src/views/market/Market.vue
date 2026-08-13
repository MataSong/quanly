<template>
  <div class="market-page">
    <div class="page-header">
      <h2 class="page-title">{{ t("market.title") }}</h2>
    </div>

    <!-- Controls -->
    <div class="controls">
      <el-select
        v-model="selectedSymbol"
        filterable
        :placeholder="t('market.symbolPlaceholder')"
        style="width: 200px"
        :loading="symbolsLoading"
        @change="onSymbolChange"
      >
        <el-option
          v-for="s in symbols"
          :key="s.instId"
          :label="s.instId"
          :value="s.instId"
        />
      </el-select>

      <el-select
        v-model="selectedBar"
        style="width: 100px"
        @change="onBarChange"
      >
        <el-option v-for="b in BAR_OPTIONS" :key="b" :label="b" :value="b" />
      </el-select>

      <el-tag :type="wsConnected ? 'success' : 'info'" size="small">
        {{ wsConnected ? t("market.statusConnected") : t("market.statusDisconnected") }}
      </el-tag>
    </div>

    <!-- Error banner -->
    <el-alert
      v-if="fetchError"
      :title="fetchError"
      type="error"
      show-icon
      closable
      style="margin-bottom: 12px"
      @close="fetchError = ''"
    />

    <!-- Chart -->
    <div class="chart-wrap">
      <div v-if="candlesLoading" class="chart-overlay">
        <el-icon class="spinning"><Loading /></el-icon>
        <span>{{ t("common.loading") }}</span>
      </div>
      <div ref="chartContainer" class="chart-container" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from "vue";
import { useI18n } from "vue-i18n";
import { Loading } from "@element-plus/icons-vue";
import { createChart, CandlestickSeries } from "lightweight-charts";
import type { IChartApi, ISeriesApi, CandlestickData } from "lightweight-charts";
import { getCandles, getSymbols } from "@/api/market";
import type { Candle, Symbol as OkxSymbol } from "@/api/market";
import { useMarketSocket } from "@/composables/useMarketSocket";

const { t } = useI18n();

const BAR_OPTIONS = ["1m", "3m", "5m", "15m", "30m", "1H", "4H", "1D"];

const selectedSymbol = ref("BTC-USDT");
const selectedBar = ref("1m");
const symbols = ref<OkxSymbol[]>([]);
const symbolsLoading = ref(false);
const candlesLoading = ref(false);
const fetchError = ref("");
const wsConnected = ref(false);

const chartContainer = ref<HTMLElement | null>(null);
let chart: IChartApi | null = null;
let series: ISeriesApi<"Candlestick"> | null = null;

// ---------------------------------------------------------------- chart helpers

function toChartBar(c: Candle): CandlestickData {
  return {
    time: Math.floor(c.ts / 1000) as unknown as CandlestickData["time"],
    open: parseFloat(c.o),
    high: parseFloat(c.h),
    low: parseFloat(c.l),
    close: parseFloat(c.c),
  };
}

function initChart() {
  if (!chartContainer.value) return;
  if (chart) {
    chart.remove();
    chart = null;
    series = null;
  }
  chart = createChart(chartContainer.value, {
    width: chartContainer.value.clientWidth,
    height: 420,
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
  series = chart.addSeries(CandlestickSeries, {
    upColor: "#26a69a",
    downColor: "#ef5350",
    borderVisible: false,
    wickUpColor: "#26a69a",
    wickDownColor: "#ef5350",
  });
}

// ---------------------------------------------------------------- data loading

async function loadSymbols() {
  symbolsLoading.value = true;
  try {
    symbols.value = await getSymbols();
  } catch (e) {
    // non-fatal: user can still type a symbol
    console.warn("loadSymbols error:", e);
  } finally {
    symbolsLoading.value = false;
  }
}

async function loadCandles() {
  if (!series) return;
  candlesLoading.value = true;
  fetchError.value = "";
  try {
    const result = await getCandles(selectedSymbol.value, selectedBar.value, 200);
    const bars = result.data.map(toChartBar);
    series.setData(bars);
    chart?.timeScale().fitContent();
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    fetchError.value = t("market.errorLoad") + ": " + msg;
  } finally {
    candlesLoading.value = false;
  }
}

// ---------------------------------------------------------------- WS realtime

let wsDisconnect: (() => void) | null = null;

function startSocket() {
  if (wsDisconnect) {
    wsDisconnect();
    wsDisconnect = null;
    wsConnected.value = false;
  }
  const { connected, disconnect } = useMarketSocket(
    selectedSymbol.value,
    (candle: Candle) => {
      if (!series) return;
      series.update(toChartBar(candle));
    },
  );
  // Watch connected ref
  watch(connected, (v) => { wsConnected.value = v; }, { immediate: true });
  wsDisconnect = disconnect;
}

// ---------------------------------------------------------------- symbol/bar change

async function onSymbolChange() {
  startSocket();
  await loadCandles();
}

async function onBarChange() {
  await loadCandles();
}

// ---------------------------------------------------------------- resize

let resizeObserver: ResizeObserver | null = null;

function setupResize() {
  if (!chartContainer.value || !chart) return;
  resizeObserver = new ResizeObserver((entries) => {
    for (const entry of entries) {
      chart?.applyOptions({ width: entry.contentRect.width });
    }
  });
  resizeObserver.observe(chartContainer.value);
}

// ---------------------------------------------------------------- lifecycle

onMounted(async () => {
  await nextTick();
  initChart();
  setupResize();
  await loadSymbols();
  await loadCandles();
  startSocket();
});

onUnmounted(() => {
  if (wsDisconnect) wsDisconnect();
  resizeObserver?.disconnect();
  chart?.remove();
  chart = null;
  series = null;
});
</script>

<style scoped>
.market-page {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.page-header {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}

.page-title {
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: 600;
  color: var(--gray-900);
}

.controls {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.chart-wrap {
  position: relative;
  background: #fff;
  border: 1px solid var(--gray-200);
  border-radius: var(--radius-md);
  overflow: hidden;
  min-height: 430px;
}

.chart-container {
  width: 100%;
}

.chart-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  background: rgba(255, 255, 255, 0.85);
  z-index: 10;
  font-size: var(--font-size-md);
  color: var(--gray-500);
}

.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
