<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useTerminal } from "@/stores/terminal";

const t = useTerminal();
const bids = ref<number[][]>([]);
const asks = ref<number[][]>([]);
let ws: WebSocket | null = null;

const maxSize = computed(() => {
  const all = [...bids.value, ...asks.value].map((l) => l[1]);
  return all.length ? Math.max(...all) : 1;
});

function pct(sz: number) {
  return Math.min(100, (sz / maxSize.value) * 100);
}

function open() {
  close();
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws/depth/${t.symbol}`);
  ws.onmessage = (ev) => {
    const m = JSON.parse(ev.data);
    if (m.type === "depth") {
      bids.value = m.bids || [];
      asks.value = m.asks || [];
    }
  };
}

function close() {
  ws?.close();
  ws = null;
}

watch(
  () => t.symbol,
  () => open()
);

onMounted(open);
onBeforeUnmount(close);
</script>

<template>
  <div class="ob">
    <div class="side asks">
      <div v-for="(l, i) in asks.slice().reverse()" :key="'a' + i" class="row">
        <span class="bar ask" :style="{ width: pct(l[1]) + '%' }"></span>
        <span class="px down">{{ l[0] }}</span>
        <span class="sz">{{ l[1] }}</span>
      </div>
    </div>
    <div class="side bids">
      <div v-for="(l, i) in bids" :key="'b' + i" class="row">
        <span class="bar bid" :style="{ width: pct(l[1]) + '%' }"></span>
        <span class="px up">{{ l[0] }}</span>
        <span class="sz">{{ l[1] }}</span>
      </div>
    </div>
    <div v-if="bids.length === 0 && asks.length === 0" class="empty">
      {{ $t("terminal.depth") }}
    </div>
  </div>
</template>

<style scoped>
.ob {
  font-family: ui-monospace, "SF Mono", monospace;
  font-size: 12px;
  padding: 6px;
}
.row {
  position: relative;
  display: flex;
  justify-content: space-between;
  padding: 2px 6px;
}
.bar {
  position: absolute;
  right: 0;
  top: 0;
  bottom: 0;
  opacity: 0.14;
  z-index: 0;
}
.bar.ask {
  background: #ff453a;
}
.bar.bid {
  background: #30d158;
}
.px,
.sz {
  position: relative;
  z-index: 1;
}
.up {
  color: #30d158;
}
.down {
  color: #ff453a;
}
.sz {
  color: var(--fg-dim);
}
.empty {
  text-align: center;
  color: var(--fg-dim);
  padding: 16px;
}
</style>
