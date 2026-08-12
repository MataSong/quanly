<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useTerminal } from "@/stores/terminal";

const t = useTerminal();
const symbols = ref<string[]>([]);
const search = ref("");
const favorites = ref<string[]>(
  JSON.parse(localStorage.getItem("terminal.favorites") || "[]")
);

const filtered = computed(() => {
  const q = search.value.trim().toUpperCase();
  const base = q ? symbols.value.filter((s) => s.toUpperCase().includes(q)) : symbols.value;
  // 自选置顶
  const fav = base.filter((s) => favorites.value.includes(s));
  const rest = base.filter((s) => !favorites.value.includes(s));
  return [...fav, ...rest];
});

function pick(sym: string) {
  t.setSymbol(sym);
}

function toggleFav(sym: string, e: Event) {
  e.stopPropagation();
  const i = favorites.value.indexOf(sym);
  if (i >= 0) favorites.value.splice(i, 1);
  else favorites.value.push(sym);
  localStorage.setItem("terminal.favorites", JSON.stringify(favorites.value));
}

async function load() {
  try {
    const r = await fetch("/api/market/symbols");
    const data = await r.json();
    // /market/symbols 返回可能是 [{instId}] 或 [string]
    symbols.value = data.map((x: any) => (typeof x === "string" ? x : x.instId || x.symbol)).filter(Boolean);
  } catch {
    symbols.value = ["BTC-USDT", "ETH-USDT", "SOL-USDT"];
  }
}

onMounted(load);
</script>

<template>
  <div class="glass symlist">
    <input class="input search" v-model="search" :placeholder="$t('terminal.search')" />
    <div class="list">
      <div
        v-for="s in filtered"
        :key="s"
        class="row"
        :class="{ active: s === t.symbol }"
        @click="pick(s)"
      >
        <span class="star" :class="{ on: favorites.includes(s) }" @click="toggleFav(s, $event)">★</span>
        <span class="sym">{{ s }}</span>
      </div>
      <div v-if="filtered.length === 0" class="empty">{{ $t("terminal.symbols") }}</div>
    </div>
  </div>
</template>

<style scoped>
.symlist {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 10px;
  overflow: hidden;
}
.search {
  margin-bottom: 8px;
}
.list {
  flex: 1;
  overflow-y: auto;
}
.row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 8px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
}
.row:hover {
  background: var(--glass-border);
}
.row.active {
  background: var(--glass-border);
  color: var(--fg);
  font-weight: 600;
}
.star {
  color: var(--fg-dim);
  opacity: 0.4;
  font-size: 12px;
}
.star.on {
  color: #f5a623;
  opacity: 1;
}
.sym {
  flex: 1;
}
.empty {
  text-align: center;
  color: var(--fg-dim);
  padding: 16px;
  font-size: 13px;
}
</style>
