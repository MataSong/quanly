<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  createChart,
  CandlestickSeries,
  LineSeries,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type LineData,
  type UTCTimestamp,
} from "lightweight-charts";
import client from "@/api/client";
import { useI18n } from "vue-i18n";

const props = defineProps<{ symbol: string; bar?: string; indicators?: string[] }>();
const { t: $t } = useI18n();

const container = ref<HTMLDivElement | null>(null);
const empty = ref(false);
let chart: IChartApi | null = null;
let series: ISeriesApi<"Candlestick"> | null = null;
let ws: WebSocket | null = null;
let lastTime = 0; // 最近一根 bar 的秒级时间戳,保证 update 时间单调不倒退
let closes: { time: number; close: number }[] = []; // 供指标计算
const overlays = new Map<string, ISeriesApi<"Line">>();

const IND_COLORS: Record<string, string> = {
  ma7: "#f5a623", ma25: "#4a9eff", ema12: "#bd10e0",
  boll_up: "#8e8e93", boll_mid: "#8e8e93", boll_low: "#8e8e93",
};

function sma(data: number[], period: number): (number | null)[] {
  const out: (number | null)[] = [];
  let sum = 0;
  for (let i = 0; i < data.length; i++) {
    sum += data[i];
    if (i >= period) sum -= data[i - period];
    out.push(i >= period - 1 ? sum / period : null);
  }
  return out;
}

function ema(data: number[], period: number): (number | null)[] {
  const out: (number | null)[] = [];
  const k = 2 / (period + 1);
  let prev: number | null = null;
  for (let i = 0; i < data.length; i++) {
    if (prev === null) prev = data[i];
    else prev = data[i] * k + prev * (1 - k);
    out.push(i >= period - 1 ? prev : null);
  }
  return out;
}

function toLine(values: (number | null)[]): LineData[] {
  const out: LineData[] = [];
  for (let i = 0; i < values.length; i++) {
    if (values[i] != null)
      out.push({ time: closes[i].time as UTCTimestamp, value: values[i] as number });
  }
  return out;
}

function clearOverlays() {
  for (const s of overlays.values()) chart?.removeSeries(s);
  overlays.clear();
}

function addOverlay(key: string, data: LineData[]) {
  if (!chart) return;
  const line = chart.addSeries(LineSeries, {
    color: IND_COLORS[key] || "#888", lineWidth: 1, priceLineVisible: false,
    lastValueVisible: false,
  });
  line.setData(data);
  overlays.set(key, line);
}

function applyIndicators() {
  if (!chart || closes.length === 0) return;
  clearOverlays();
  const inds = props.indicators || [];
  const arr = closes.map((c) => c.close);
  if (inds.includes("ma7")) addOverlay("ma7", toLine(sma(arr, 7)));
  if (inds.includes("ma25")) addOverlay("ma25", toLine(sma(arr, 25)));
  if (inds.includes("ema12")) addOverlay("ema12", toLine(ema(arr, 12)));
  if (inds.includes("boll")) {
    const period = 20;
    const mid = sma(arr, period);
    const up: (number | null)[] = [];
    const low: (number | null)[] = [];
    for (let i = 0; i < arr.length; i++) {
      if (i >= period - 1 && mid[i] != null) {
        const slice = arr.slice(i - period + 1, i + 1);
        const m = mid[i] as number;
        const sd = Math.sqrt(slice.reduce((a, b) => a + (b - m) ** 2, 0) / period);
        up.push(m + 2 * sd);
        low.push(m - 2 * sd);
      } else {
        up.push(null);
        low.push(null);
      }
    }
    addOverlay("boll_up", toLine(up));
    addOverlay("boll_mid", toLine(mid));
    addOverlay("boll_low", toLine(low));
  }
}

function themeColors() {
  const dark = document.documentElement.dataset.theme !== "light";
  return {
    bg: "transparent",
    text: dark ? "#9a9aa5" : "#6e6e73",
    grid: dark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.06)",
    up: "#30d158",
    down: "#ff453a",
  };
}

async function loadHistory() {
  const bar = props.bar || "1m";
  const r = await client.get(`/market/${props.symbol}/candles`, {
    params: { bar, limit: 200 },
  });
  // 按 time 升序 + 去重(同一秒时间戳只保留最后一根),防止 lightweight-charts
  // 收到重复/乱序 time 时把序列渲染成一条水平实线。
  const map = new Map<number, CandlestickData>();
  for (const c of r.data.candles as any[]) {
    const time = Math.floor(c.ts / 1000);
    map.set(time, {
      time: time as UTCTimestamp,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    });
  }
  const data = Array.from(map.values()).sort(
    (a, b) => (a.time as number) - (b.time as number)
  );
  lastTime = data.length ? (data[data.length - 1].time as number) : 0;
  empty.value = data.length === 0;
  series?.setData(data);
  closes = data.map((d) => ({ time: d.time as number, close: d.close }));
  applyIndicators();
  chart?.timeScale().fitContent();
}

function openWs() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const bar = props.bar || "1m";
  ws = new WebSocket(
    `${proto}://${location.host}/ws/market/${props.symbol}?bar=${bar}`
  );
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "candle" && series) {
      const time = Math.floor(msg.ts / 1000);
      // 时间倒退的推送丢弃;等于 lastTime 覆盖当前 bar,大于则开新 bar
      if (time < lastTime) return;
      lastTime = time;
      series.update({
        time: time as UTCTimestamp,
        open: msg.open,
        high: msg.high,
        low: msg.low,
        close: msg.close,
      });
    }
  };
}

function build() {
  if (!container.value) return;
  const c = themeColors();
  chart = createChart(container.value, {
    layout: { background: { color: c.bg }, textColor: c.text },
    grid: { vertLines: { color: c.grid }, horzLines: { color: c.grid } },
    autoSize: true,
    localization: {
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
  });
  series = chart.addSeries(CandlestickSeries, {
    upColor: c.up,
    downColor: c.down,
    borderVisible: false,
    wickUpColor: c.up,
    wickDownColor: c.down,
  });
}

function reset() {
  ws?.close();
  ws = null;
  loadHistory();
  openWs();
}

onMounted(() => {
  build();
  loadHistory();
  openWs();
});

watch(
  () => [props.symbol, props.bar],
  () => reset()
);

watch(
  () => props.indicators,
  () => applyIndicators(),
  { deep: true }
);

onBeforeUnmount(() => {
  ws?.close();
  chart?.remove();
});
</script>

<template>
  <div class="chart-wrap">
    <div ref="container" class="chart"></div>
    <div v-if="empty" class="chart-empty">{{ $t("market.noCandles") }}</div>
  </div>
</template>

<style scoped>
.chart {
  width: 100%;
  height: 460px;
}
.chart-wrap { position: relative; }
.chart-empty {
  position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  color: var(--fg-dim); font-size: 14px; pointer-events: none;
}
</style>
