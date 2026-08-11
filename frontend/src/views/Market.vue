<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import CandleChart from "@/components/CandleChart.vue";
import SymbolSelect from "@/components/SymbolSelect.vue";
import GlassSelect from "@/components/GlassSelect.vue";

const route = useRoute();
const router = useRouter();

const symbol = ref((route.params.symbol as string) || "BTC-USDT");
const bar = ref("1m");
const barOptions = [
  { label: "1m", value: "1m" },
  { label: "5m", value: "5m" },
  { label: "15m", value: "15m" },
  { label: "1H", value: "1H" },
  { label: "4H", value: "4H" },
  { label: "1D", value: "1D" },
];
const lastPrice = ref<number | null>(null);
let tickerWs: WebSocket | null = null;

function openTicker() {
  tickerWs?.close();
  lastPrice.value = null;
  const proto = location.protocol === "https:" ? "wss" : "ws";
  tickerWs = new WebSocket(
    `${proto}://${location.host}/ws/market/${symbol.value}?bar=${bar.value}`
  );
  tickerWs.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "ticker") lastPrice.value = msg.last;
    else if (msg.type === "candle") lastPrice.value = msg.close;
  };
}

function onSymbolChange(s: string) {
  if (s === symbol.value) return;
  symbol.value = s;
  router.replace(`/market/${s}`);
}

watch([symbol, bar], () => openTicker());

onMounted(() => {
  openTicker();
});
onBeforeUnmount(() => tickerWs?.close());
</script>

<template>
  <div class="glass panel">
    <div class="head">
      <div class="head-controls">
        <SymbolSelect v-model="symbol" @update:modelValue="onSymbolChange" />
        <GlassSelect v-model="bar" :options="barOptions" />
      </div>
      <div class="price">
        <span class="sym">{{ symbol }}</span>
        <span class="last" :class="{ live: lastPrice !== null }">
          {{ lastPrice !== null ? lastPrice : "—" }}
        </span>
      </div>
    </div>
    <CandleChart :symbol="symbol" :bar="bar" />
  </div>
</template>

<style scoped>
.panel {
  padding: 20px;
}
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 12px;
}
.head-controls {
  display: flex;
  gap: 10px;
  align-items: center;
}
.price {
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.sym {
  color: var(--fg-dim);
  font-size: 13px;
}
.last {
  font-size: 22px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.last.live {
  color: var(--accent);
}
</style>
