<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { financeApi } from "@/api/finance";
import GlassNumber from "@/components/GlassNumber.vue";
import { useToast } from "@/composables/useToast";

const { t } = useI18n();
const toast = useToast();

const env = ref<"sim" | "live">("sim");
const tab = ref<"earn" | "loan">("earn");
const products = ref<any[]>([]);
const holdings = ref<any[]>([]);
const amounts = ref<Record<number, string>>({});

async function loadProducts() {
  const r = await financeApi.products(env.value, tab.value);
  products.value = r.data;
}
async function loadHoldings() {
  const r = await financeApi.holdings(env.value);
  holdings.value = r.data;
}

async function subscribe(p: any) {
  const amt = amounts.value[p.id];
  if (!amt) {
    toast.info(t("trade.enterSize"));
    return;
  }
  try {
    await financeApi.subscribe(env.value, p.id, amt);
    amounts.value[p.id] = "";
    await loadHoldings();
    toast.success(t("finance.subscribed"));
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || t("finance.failed"));
  }
}

async function redeem(h: any) {
  await financeApi.redeem(env.value, h.id);
  await loadHoldings();
  toast.success(t("finance.redeemed"));
}

watch(tab, loadProducts);
watch(env, async () => {
  await loadProducts();
  await loadHoldings();
});
onMounted(async () => {
  await loadProducts();
  await loadHoldings();
});
</script>

<template>
  <div class="wrap">
    <div class="glass bar">
      <div class="tabs">
        <button class="tab" :class="{ active: tab === 'earn' }" @click="tab = 'earn'">
          {{ $t("finance.earn") }}
        </button>
        <button class="tab" :class="{ active: tab === 'loan' }" @click="tab = 'loan'">
          {{ $t("finance.loan") }}
        </button>
      </div>
      <div class="env">
        <button class="tab" :class="{ active: env === 'sim' }" @click="env = 'sim'">
          {{ $t("trade.sim") }}
        </button>
        <button class="tab live" :class="{ active: env === 'live' }" @click="env = 'live'">
          {{ $t("trade.live") }}
        </button>
      </div>
    </div>

    <div class="glass panel">
      <h3>{{ tab === "earn" ? $t("finance.products") : $t("finance.loanProducts") }}</h3>
      <table class="tbl">
        <thead>
          <tr>
            <th>{{ $t("finance.name") }}</th>
            <th>{{ $t("finance.category") }}</th>
            <th>{{ $t("finance.ccy") }}</th>
            <th>{{ $t("finance.apr") }}</th>
            <th>{{ $t("finance.term") }}</th>
            <th>{{ $t("finance.amount") }}</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in products" :key="p.id">
            <td>{{ p.name }}</td>
            <td>{{ $t("finance.cat." + p.category) }}</td>
            <td>{{ p.ccy }}</td>
            <td class="up">{{ (p.apr * 100).toFixed(2) }}%</td>
            <td>{{ p.term_days === 0 ? $t("finance.flexible") : p.term_days + "d" }}</td>
            <td>
              <GlassNumber
                :model-value="amounts[p.id] ?? ''"
                @update:modelValue="(v: number) => (amounts[p.id] = String(v))"
                :placeholder="String(p.min_amount)"
              />
            </td>
            <td>
              <button class="btn sm" @click="subscribe(p)">
                {{ tab === "earn" ? $t("finance.subscribe") : $t("finance.borrow") }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="glass panel">
      <h3>{{ $t("finance.myHoldings") }}</h3>
      <table class="tbl">
        <thead>
          <tr>
            <th>{{ $t("finance.name") }}</th>
            <th>{{ $t("finance.ccy") }}</th>
            <th>{{ $t("finance.principal") }}</th>
            <th>{{ $t("finance.apr") }}</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="h in holdings" :key="h.id">
            <td>{{ h.product }}</td>
            <td>{{ h.ccy }}</td>
            <td>{{ h.principal }}</td>
            <td class="up">{{ (h.apr * 100).toFixed(2) }}%</td>
            <td>
              <button class="btn btn-ghost sm" @click="redeem(h)">{{ $t("finance.redeem") }}</button>
            </td>
          </tr>
          <tr v-if="holdings.length === 0">
            <td colspan="5" class="empty">{{ $t("finance.noHoldings") }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.wrap { display: flex; flex-direction: column; gap: 16px; }
.bar { display: flex; justify-content: space-between; align-items: center; padding: 12px 18px; }
.tabs, .env { display: flex; gap: 6px; }
.tab { background: transparent; border: 1px solid var(--glass-border); color: var(--fg-dim); border-radius: 10px; padding: 6px 14px; font-size: 13px; font-weight: 600; cursor: pointer; }
.tab.active { background: var(--glass-bg-strong); color: var(--fg); border-color: var(--accent); }
.tab.live.active { border-color: #ff453a; color: #ff453a; }
.panel { padding: 20px; }
h3 { margin: 0 0 14px; }
.tbl { width: 100%; border-collapse: collapse; font-size: 13px; }
.tbl th, .tbl td { text-align: left; padding: 9px 6px; border-bottom: 1px solid var(--glass-border); }
.tbl th { color: var(--fg-dim); font-weight: 600; }
.sm { padding: 4px 10px; font-size: 12px; }
.up { color: #30d158; }
.empty { text-align: center; color: var(--fg-dim); padding: 16px; }
</style>
