<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  createChart,
  CandlestickSeries,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type UTCTimestamp,
} from "lightweight-charts";
import client from "@/api/client";
import { useI18n } from "vue-i18n";

const props = defineProps<{ symbol: string; bar?: string }>();
const { t: $t } = useI18n();

const container = ref<HTMLDivElement | null>(null);
const empty = ref(false);
let chart: IChartApi | null = null;
let series: ISeriesApi<"Candlestick"> | null = null;
let ws: WebSocket | null = null;
let lastTime = 0; // 最近一根 bar 的秒级时间戳,保证 update 时间单调不倒退

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
