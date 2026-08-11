<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { assetsApi } from "@/api/assets";
import { useAuth } from "@/stores/auth";
import Spinner from "@/components/Spinner.vue";

const auth = useAuth();
const env = ref<"sim" | "live">("sim");
const sum = ref<any>(null);
const loading = ref(false);
let timer: number | undefined;

async function load() {
  const r = await assetsApi.summary(env.value);
  sum.value = r.data;
}

// 进入页面/切换环境时,先向 OKX 拉取实时余额/持仓回填本地,再读汇总
async function syncAndLoad() {
  loading.value = true;
  try {
    try {
      await assetsApi.sync(env.value);
    } catch {
      /* 无凭证/同步失败时仍展示本地已有数据 */
    }
    await load();
  } finally {
    loading.value = false;
  }
}

function fmt(n: number | undefined): string {
  if (n === undefined || n === null) return "—";
  return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

watch(env, syncAndLoad);

onMounted(async () => {
  if (!auth.user) await auth.fetchMe();
  await syncAndLoad();
  // 每 3 秒刷新净值(浮盈随行情跳)
  timer = window.setInterval(load, 3000);
});
onBeforeUnmount(() => clearInterval(timer));
</script>

<template>
  <div class="dash">
    <div class="glass-strong hero">
      <div class="hero-top">
        <span class="welcome">
          {{ $t("dashboard.welcome") }}<span v-if="auth.user">, {{ auth.user.username }}</span>
        </span>
        <div class="env-switch">
          <button class="tab" :class="{ active: env === 'sim' }" @click="env = 'sim'">
            {{ $t("trade.sim") }}
          </button>
          <button class="tab live" :class="{ active: env === 'live' }" @click="env = 'live'">
            {{ $t("trade.live") }}
          </button>
        </div>
      </div>
      <div class="equity-label">{{ $t("dashboard.totalEquity") }} (USDT)</div>
      <div class="equity">
        <Spinner v-if="loading && !sum" :size="28" />
        <template v-else>{{ fmt(sum?.total_equity) }}</template>
      </div>
      <div class="upl" :class="(sum?.upl ?? 0) >= 0 ? 'up' : 'down'">
        {{ $t("dashboard.upl") }}: {{ fmt(sum?.upl) }}
      </div>
    </div>

    <div class="cards">
      <div class="glass card">
        <div class="card-label">{{ $t("dashboard.available") }}</div>
        <div class="card-val">{{ fmt(sum?.available) }}</div>
      </div>
      <div class="glass card">
        <div class="card-label">{{ $t("dashboard.frozen") }}</div>
        <div class="card-val">{{ fmt(sum?.frozen) }}</div>
      </div>
      <div class="glass card">
        <div class="card-label">{{ $t("dashboard.spotValue") }}</div>
        <div class="card-val">{{ fmt(sum?.spot_value) }}</div>
      </div>
      <div class="glass card">
        <div class="card-label">{{ $t("dashboard.swapValue") }}</div>
        <div class="card-val">{{ fmt(sum?.swap_value) }}</div>
      </div>
      <div class="glass card">
        <div class="card-label">{{ $t("dashboard.financeValue") }}</div>
        <div class="card-val">{{ fmt(sum?.finance_value) }}</div>
      </div>
      <div class="glass card">
        <div class="card-label">{{ $t("dashboard.loanValue") }}</div>
        <div class="card-val">{{ fmt(sum?.loan_value) }}</div>
      </div>
    </div>

    <div class="glass panel" v-if="sum?.positions_dist?.length">
      <h3>{{ $t("dashboard.positions") }}</h3>
      <div v-for="p in sum.positions_dist" :key="p.symbol + p.pos_side" class="pos-row">
        <span class="pos-name">
          {{ p.symbol }}
          <span :class="p.pos_side === 'long' ? 'up' : 'down'">
            {{ p.pos_side === "long" ? $t("trade.long") : $t("trade.short") }}
          </span>
        </span>
        <span class="pos-notional">{{ fmt(p.notional) }}</span>
        <span :class="p.upl >= 0 ? 'up' : 'down'">{{ fmt(p.upl) }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dash {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.hero {
  padding: 28px;
}
.hero-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
.welcome {
  font-size: 14px;
  color: var(--fg-dim);
}
.env-switch {
  display: flex;
  gap: 6px;
}
.tab {
  background: transparent;
  border: 1px solid var(--glass-border);
  color: var(--fg-dim);
  border-radius: 10px;
  padding: 5px 12px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}
.tab.active {
  background: var(--glass-bg-strong);
  color: var(--fg);
  border-color: var(--accent);
}
.tab.live.active {
  border-color: #ff453a;
  color: #ff453a;
}
.equity-label {
  font-size: 13px;
  color: var(--fg-dim);
}
.equity {
  font-size: 40px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  margin: 4px 0;
}
.upl {
  font-size: 14px;
  font-weight: 600;
}
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px;
}
.card {
  padding: 18px;
}
.card.muted {
  opacity: 0.6;
}
.card-label {
  font-size: 12px;
  color: var(--fg-dim);
}
.card-val {
  font-size: 22px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  margin-top: 6px;
}
.soon {
  font-size: 11px;
  color: var(--fg-dim);
  margin-top: 4px;
}
.panel {
  padding: 20px;
}
h3 {
  margin: 0 0 12px;
  font-size: 15px;
}
.pos-row {
  display: flex;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px solid var(--glass-border);
  font-size: 14px;
}
.pos-name {
  display: flex;
  gap: 8px;
}
.up {
  color: #30d158;
}
.down {
  color: #ff453a;
}
</style>
