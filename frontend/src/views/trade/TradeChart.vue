<template>
  <div class="trade-chart">
    <!-- Top bar: timezone selector + WS status + latest price -->
    <div class="chart-topbar">
      <span class="control-label">{{ t("market.timezone.label") }}</span>
      <el-select
        v-model="selectedTz"
        style="width: 160px"
        size="small"
        @change="onTzChange"
      >
        <el-option value="Asia/Shanghai" :label="t('market.timezone.beijing')" />
        <el-option value="UTC" :label="t('market.timezone.utc')" />
      </el-select>

      <el-tag :type="wsConnected ? 'success' : 'info'" size="small" class="ws-tag">
        {{ wsConnected ? t("trade.wsConnected") : t("trade.wsDisconnected") }}
      </el-tag>

      <span v-if="latestPrice" class="latest-price">
        <span class="latest-price-label">{{ t("trade.latestPrice") }}</span>
        <span class="latest-price-value">{{ latestPrice }}</span>
      </span>
    </div>

    <!-- Error banner -->
    <el-alert
      v-if="fetchError"
      :title="fetchError"
      type="error"
      show-icon
      closable
      style="margin-bottom: 8px"
      @close="fetchError = ''"
    />

    <!-- Chart wrap -->
    <div class="chart-wrap">
      <div v-if="candlesLoading" class="chart-overlay">
        <el-icon class="spinning"><Loading /></el-icon>
        <span>{{ t("common.loading") }}</span>
      </div>

      <!-- OHLC tooltip (crosshair hover) -->
      <div
        v-if="tooltip.visible"
        class="ohlc-tooltip"
        :class="{ 'is-up': tooltip.isUp }"
        :style="{ left: tooltip.x + 'px', top: tooltip.y + 'px' }"
      >
        <div class="ohlc-row">
          <span class="ohlc-label">{{ t("trade.ohlc.time") }}</span>
          <span class="ohlc-val">{{ tooltip.time }}</span>
        </div>
        <div class="ohlc-row">
          <span class="ohlc-label">{{ t("trade.ohlc.open") }}</span>
          <span class="ohlc-val">{{ tooltip.open }}</span>
        </div>
        <div class="ohlc-row">
          <span class="ohlc-label">{{ t("trade.ohlc.high") }}</span>
          <span class="ohlc-val">{{ tooltip.high }}</span>
        </div>
        <div class="ohlc-row">
          <span class="ohlc-label">{{ t("trade.ohlc.low") }}</span>
          <span class="ohlc-val">{{ tooltip.low }}</span>
        </div>
        <div class="ohlc-row">
          <span class="ohlc-label">{{ t("trade.ohlc.close") }}</span>
          <span class="ohlc-val">{{ tooltip.close }}</span>
        </div>
        <div class="ohlc-row">
          <span class="ohlc-label">{{ t("trade.ohlc.change") }}</span>
          <span class="ohlc-val">{{ tooltip.change }} ({{ tooltip.changePct }})</span>
        </div>
        <div class="ohlc-row">
          <span class="ohlc-label">{{ t("trade.ohlc.amplitude") }}</span>
          <span class="ohlc-val">{{ tooltip.amplitude }}</span>
        </div>
        <div class="ohlc-row">
          <span class="ohlc-label">{{ t("trade.ohlc.vol") }}</span>
          <span class="ohlc-val">{{ tooltip.vol }}</span>
        </div>
      </div>

      <div ref="chartContainer" class="chart-container" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted, watch, nextTick } from "vue";
import { useI18n } from "vue-i18n";
import { Loading } from "@element-plus/icons-vue";
import { createChart, CandlestickSeries, CrosshairMode } from "lightweight-charts";
import type {
  IChartApi,
  ISeriesApi,
  CandlestickData,
  LogicalRange,
} from "lightweight-charts";
import { getCandles } from "@/api/market";
import type { Candle } from "@/api/market";
import { useMarketSocket } from "@/composables/useMarketSocket";
import { useBreakpoint } from "@/composables/useBreakpoint";
import { useTradeDeskStore } from "@/stores/tradeDesk";

const { t } = useI18n();
const { isMobile } = useBreakpoint();
const store = useTradeDeskStore();

const TZ_KEY = "quanly:market_tz";

const selectedTz = ref<string>(localStorage.getItem(TZ_KEY) ?? "Asia/Shanghai");
const candlesLoading = ref(false);
const historyLoading = ref(false);
const fetchError = ref("");
const wsConnected = ref(false);
const latestPrice = ref<string>("");

const chartContainer = ref<HTMLElement | null>(null);
let chart: IChartApi | null = null;
let series: ISeriesApi<"Candlestick"> | null = null;

// All loaded bars — kept in memory for prepend-merge
let allBars: CandlestickData[] = [];
// Last bar — used by onTicker to update close price
let lastBar: CandlestickData | null = null;

// ---------------------------------------------------------------- tooltip state

const tooltip = reactive({
  visible: false,
  x: 12,
  y: 12,
  time: "",
  open: "",
  high: "",
  low: "",
  close: "",
  change: "",      // 涨跌额 close-open
  changePct: "",   // 涨跌幅 %
  amplitude: "",   // 振幅 (high-low)/open %
  vol: "",         // 成交量
  isUp: true,
});

// time(秒) → 原始 candle 的成交量(vol),用于 tooltip 显示(series 只存 OHLC)。
const volMap = new Map<number, string>();

// ---------------------------------------------------------------- timezone helpers

function makeTimeFormatter(tz: string) {
  const fmt = new Intl.DateTimeFormat("en-GB", {
    timeZone: tz,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  return (ts: number) => fmt.format(new Date(ts * 1000));
}

function makeTickMarkFormatter(tz: string) {
  const dateFmt = new Intl.DateTimeFormat("en-GB", {
    timeZone: tz,
    month: "2-digit",
    day: "2-digit",
  });
  const timeFmt = new Intl.DateTimeFormat("en-GB", {
    timeZone: tz,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  return (ts: number, _tickType: unknown) => {
    const d = new Date(ts * 1000);
    const timeStr = timeFmt.format(d);
    if (timeStr === "00:00") return dateFmt.format(d);
    return timeStr;
  };
}

function applyTimezone() {
  if (!chart) return;
  const tz = selectedTz.value;
  chart.applyOptions({
    localization: {
      timeFormatter: makeTimeFormatter(tz),
    },
    timeScale: {
      tickMarkFormatter: makeTickMarkFormatter(tz),
      timeVisible: true,
      secondsVisible: false,
    },
  });
}

// ---------------------------------------------------------------- chart helpers

function toChartBar(c: Candle): CandlestickData {
  const time = Math.floor(c.ts / 1000);
  // 记录成交量供 tooltip 显示(series 只存 OHLC,vol 单独存)
  if (c.vol != null) volMap.set(time, String(c.vol));
  return {
    time: time as unknown as CandlestickData["time"],
    open: parseFloat(c.o),
    high: parseFloat(c.h),
    low: parseFloat(c.l),
    close: parseFloat(c.c),
  };
}

function formatPrice(v: number): string {
  // auto-precision: if price >= 100 use 2 decimals, else more
  if (v >= 1000) return v.toFixed(2);
  if (v >= 1) return v.toFixed(4);
  return v.toFixed(8);
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
    height: isMobile.value ? 260 : 420,
    layout: {
      background: { color: "#ffffff" },
      textColor: "#333",
    },
    grid: {
      vertLines: { color: "#f0f0f0" },
      horzLines: { color: "#f0f0f0" },
    },
    crosshair: {
      mode: CrosshairMode.Normal,
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
  applyTimezone();
  subscribeRangeChange();
  subscribeCrosshair();
}

// ---------------------------------------------------------------- crosshair / tooltip

function subscribeCrosshair() {
  if (!chart || !series) return;
  const s = series;
  chart.subscribeCrosshairMove((param) => {
    if (
      !param.point ||
      param.point.x < 0 ||
      param.point.y < 0 ||
      !param.time
    ) {
      tooltip.visible = false;
      return;
    }
    const bar = param.seriesData.get(s) as CandlestickData | undefined;
    if (!bar) {
      tooltip.visible = false;
      return;
    }

    // Position tooltip: try to follow crosshair but clamp so it stays inside
    const containerW = chartContainer.value?.clientWidth ?? 0;
    const tooltipW = 160;
    const rawX = param.point.x + 16;
    const x = rawX + tooltipW > containerW ? param.point.x - tooltipW - 8 : rawX;
    const rawY = param.point.y - 80;
    const y = rawY < 8 ? 8 : rawY;

    tooltip.x = Math.max(8, x);
    tooltip.y = Math.max(8, y);
    const o = bar.open as number;
    const h = bar.high as number;
    const l = bar.low as number;
    const c = bar.close as number;
    tooltip.open = formatPrice(o);
    tooltip.high = formatPrice(h);
    tooltip.low = formatPrice(l);
    tooltip.close = formatPrice(c);
    // 涨跌额/涨跌幅/振幅(对标 OKX)
    const chg = c - o;
    tooltip.change = (chg >= 0 ? "+" : "") + formatPrice(chg);
    tooltip.changePct = o !== 0 ? (chg >= 0 ? "+" : "") + ((chg / o) * 100).toFixed(2) + "%" : "—";
    tooltip.amplitude = o !== 0 ? (((h - l) / o) * 100).toFixed(2) + "%" : "—";
    const ts = param.time as unknown as number;
    tooltip.vol = volMap.get(ts) ?? "—";
    tooltip.isUp = c >= o;

    // Format time using selected timezone
    const fmt = new Intl.DateTimeFormat("en-GB", {
      timeZone: selectedTz.value,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
    tooltip.time = fmt.format(new Date(ts * 1000));
    tooltip.visible = true;
  });
}

// ---------------------------------------------------------------- history pagination

function subscribeRangeChange() {
  if (!chart) return;
  chart
    .timeScale()
    .subscribeVisibleLogicalRangeChange((range: LogicalRange | null) => {
      if (!range) return;
      if (range.from <= 2 && !historyLoading.value && allBars.length > 0) {
        void loadHistory();
      }
    });
}

async function loadHistory() {
  if (!series || historyLoading.value) return;
  historyLoading.value = true;
  try {
    const oldestBar = allBars[0];
    if (!oldestBar) return;
    const afterTs = (oldestBar.time as unknown as number) * 1000;
    const result = await getCandles(store.symbol, store.bar, 100, afterTs);
    if (!result.data.length) return;
    const newBars = result.data.map(toChartBar);
    const merged = [...newBars, ...allBars];
    const seen = new Set<number>();
    const deduped = merged.filter((b) => {
      const t = b.time as unknown as number;
      if (seen.has(t)) return false;
      seen.add(t);
      return true;
    });
    deduped.sort(
      (a, b) => (a.time as unknown as number) - (b.time as unknown as number),
    );
    allBars = deduped;
    series.setData(allBars);
  } catch (e) {
    console.warn("loadHistory error:", e);
  } finally {
    historyLoading.value = false;
  }
}

// ---------------------------------------------------------------- data loading

async function loadCandles() {
  if (!series) return;
  candlesLoading.value = true;
  fetchError.value = "";
  allBars = [];
  lastBar = null;
  latestPrice.value = "";
  try {
    const result = await getCandles(store.symbol, store.bar, 200);
    allBars = result.data.map(toChartBar);
    series.setData(allBars);
    if (allBars.length > 0) {
      lastBar = allBars[allBars.length - 1];
      latestPrice.value = formatPrice(lastBar.close as number);
    }
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
let stopConnectedWatch: (() => void) | null = null;

function startSocket() {
  if (wsDisconnect) {
    wsDisconnect();
    wsDisconnect = null;
    wsConnected.value = false;
  }
  // 停掉上一次的 connected watcher,避免每次切 symbol/bar 累积 watcher(泄漏)
  if (stopConnectedWatch) {
    stopConnectedWatch();
    stopConnectedWatch = null;
  }
  const { connected, disconnect } = useMarketSocket(store.symbol, store.bar, {
    onCandle: (candle: Candle) => {
      if (!series) return;
      const bar = toChartBar(candle);
      series.update(bar);
      // Keep lastBar in sync with incoming candle update
      lastBar = bar;
      latestPrice.value = formatPrice(bar.close as number);
      // Also update allBars tail for history-prepend correctness
      if (
        allBars.length > 0 &&
        (allBars[allBars.length - 1].time as unknown as number) ===
          (bar.time as unknown as number)
      ) {
        allBars[allBars.length - 1] = bar;
      } else if (
        allBars.length === 0 ||
        (allBars[allBars.length - 1].time as unknown as number) <
          (bar.time as unknown as number)
      ) {
        allBars.push(bar);
      }
    },
    onTicker: (ticker) => {
      if (!series || !lastBar) return;
      const closeVal = parseFloat(ticker.last);
      const updated: CandlestickData = {
        ...lastBar,
        close: closeVal,
        // also extend high/low if price moved outside current bar range
        high: Math.max(lastBar.high as number, closeVal),
        low: Math.min(lastBar.low as number, closeVal),
      };
      lastBar = updated;
      series.update(updated);
      latestPrice.value = formatPrice(closeVal);
    },
  });
  stopConnectedWatch = watch(connected, (v) => {
    wsConnected.value = v;
  }, { immediate: true });
  wsDisconnect = disconnect;
}

// ---------------------------------------------------------------- watch store changes

watch(
  () => store.symbol,
  async () => {
    tooltip.visible = false;
    await loadCandles();
    startSocket();
  },
);

watch(
  () => store.bar,
  async () => {
    tooltip.visible = false;
    await loadCandles();
    startSocket();
  },
);

// ---------------------------------------------------------------- responsive

watch(isMobile, (mobile) => {
  chart?.applyOptions({ height: mobile ? 260 : 420 });
});

// ---------------------------------------------------------------- timezone change

function onTzChange() {
  localStorage.setItem(TZ_KEY, selectedTz.value);
  applyTimezone();
}

// ---------------------------------------------------------------- resize

let resizeObserver: ResizeObserver | null = null;

function setupResize() {
  if (!chartContainer.value || !chart) return;
  resizeObserver = new ResizeObserver((entries) => {
    for (const entry of entries) {
      chart?.applyOptions({
        width: entry.contentRect.width,
        height: isMobile.value ? 260 : 420,
      });
    }
  });
  resizeObserver.observe(chartContainer.value);
}

// ---------------------------------------------------------------- lifecycle

onMounted(async () => {
  await nextTick();
  initChart();
  setupResize();
  await loadCandles();
  startSocket();
});

onUnmounted(() => {
  if (wsDisconnect) wsDisconnect();
  if (stopConnectedWatch) stopConnectedWatch();
  resizeObserver?.disconnect();
  chart?.remove();
  chart = null;
  series = null;
});
</script>

<style lang="scss" scoped>
@use "@/styles/mixins" as *;

.trade-chart {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.chart-topbar {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;

  @include mobile {
    gap: var(--space-2);
  }
}

.control-label {
  font-size: var(--font-size-sm);
  color: var(--gray-600);
}

.ws-tag {
  flex-shrink: 0;
}

.latest-price {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-left: auto;

  @include mobile {
    margin-left: 0;
  }
}

.latest-price-label {
  font-size: var(--font-size-sm);
  color: var(--gray-500);
}

.latest-price-value {
  font-size: var(--font-size-md);
  font-weight: 600;
  color: var(--gray-900);
  font-variant-numeric: tabular-nums;
}

.chart-wrap {
  position: relative;
  background: #fff;
  border: 1px solid var(--gray-200);
  border-radius: var(--radius-md);
  overflow: hidden;
  min-height: 430px;

  @include mobile {
    min-height: 270px;
  }
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

// OHLC crosshair tooltip
.ohlc-tooltip {
  position: absolute;
  z-index: 20;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid var(--gray-200);
  border-radius: var(--radius-sm);
  padding: 6px 10px;
  pointer-events: none;
  font-size: 12px;
  line-height: 1.6;
  min-width: 140px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);

  &.is-up {
    .ohlc-val { color: #26a69a; }
  }

  &:not(.is-up) {
    .ohlc-val { color: #ef5350; }
  }
}

.ohlc-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.ohlc-label {
  color: var(--gray-500);
  flex-shrink: 0;
}

.ohlc-val {
  font-variant-numeric: tabular-nums;
  font-weight: 500;
}
</style>
