<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { financeApi } from "@/api/finance";
import Pagination from "@/components/Pagination.vue";
import GlassSelect from "@/components/GlassSelect.vue";
import GlassNumber from "@/components/GlassNumber.vue";
import { usePagination } from "@/composables/usePagination";
import { useToast } from "@/composables/useToast";

const { t } = useI18n();
const toast = useToast();

const env = ref<"sim" | "live">("sim");
const records = ref<any[]>([]);
const { page, pageSize, total, totalPages, paged } = usePagination(records, 10);

const ACCOUNTS = ["trading", "funding", "earn"];
const form = ref({ ccy: "USDT", amount: "", from_acct: "trading", to_acct: "funding" });

const ccyOptions = [
  { label: "USDT", value: "USDT" },
  { label: "BTC", value: "BTC" },
  { label: "ETH", value: "ETH" },
];
const acctOptions = computed(() =>
  ACCOUNTS.map((a) => ({ label: t("transfer.acct." + a), value: a }))
);

async function loadRecords() {
  const r = await financeApi.transfers(env.value);
  records.value = r.data;
}

async function submit() {
  if (!form.value.amount) {
    toast.info(t("trade.enterSize"));
    return;
  }
  await financeApi.transfer({ env: env.value, ...form.value });
  form.value.amount = "";
  await loadRecords();
  toast.success(t("transfer.done"));
}

watch(env, loadRecords);
onMounted(loadRecords);
</script>

<template>
  <div class="wrap">
    <div class="glass panel">
      <div class="head">
        <h2>{{ $t("transfer.title") }}</h2>
        <div class="env">
          <button class="tab" :class="{ active: env === 'sim' }" @click="env = 'sim'">{{ $t("trade.sim") }}</button>
          <button class="tab live" :class="{ active: env === 'live' }" @click="env = 'live'">{{ $t("trade.live") }}</button>
        </div>
      </div>
      <div class="form">
        <div class="fld">
          <label>{{ $t("finance.ccy") }}</label>
          <GlassSelect v-model="form.ccy" :options="ccyOptions" />
        </div>
        <div class="fld">
          <label>{{ $t("transfer.from") }}</label>
          <GlassSelect v-model="form.from_acct" :options="acctOptions" />
        </div>
        <div class="fld">
          <label>{{ $t("transfer.to") }}</label>
          <GlassSelect v-model="form.to_acct" :options="acctOptions" />
        </div>
        <div class="fld">
          <label>{{ $t("finance.amount") }}</label>
          <GlassNumber
            :model-value="form.amount"
            @update:modelValue="(v: number) => (form.amount = String(v))"
          />
        </div>
        <div class="fld btns">
          <button class="btn" @click="submit">{{ $t("transfer.submit") }}</button>
        </div>
      </div>
    </div>

    <div class="glass panel">
      <h3>{{ $t("transfer.records") }}</h3>
      <table class="tbl">
        <thead>
          <tr>
            <th>{{ $t("bills.time") }}</th>
            <th>{{ $t("finance.ccy") }}</th>
            <th>{{ $t("finance.amount") }}</th>
            <th>{{ $t("transfer.from") }}</th>
            <th>{{ $t("transfer.to") }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="t in paged" :key="t.id">
            <td>{{ new Date(t.created_at).toLocaleString() }}</td>
            <td>{{ t.ccy }}</td>
            <td>{{ t.amount }}</td>
            <td>{{ $t("transfer.acct." + t.from_acct) }}</td>
            <td>{{ $t("transfer.acct." + t.to_acct) }}</td>
          </tr>
          <tr v-if="total === 0"><td colspan="5" class="empty">{{ $t("transfer.noRecords") }}</td></tr>
        </tbody>
      </table>
      <Pagination v-if="total > 0" v-model:page="page" v-model:pageSize="pageSize" :total="total" :totalPages="totalPages" />
    </div>
  </div>
</template>

<style scoped>
.wrap { display: flex; flex-direction: column; gap: 16px; }
.panel { padding: 20px; }
.head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
h2, h3 { margin: 0 0 14px; }
.env { display: flex; gap: 6px; }
.tab { background: transparent; border: 1px solid var(--glass-border); color: var(--fg-dim); border-radius: 10px; padding: 5px 12px; font-size: 12px; font-weight: 600; cursor: pointer; }
.tab.active { background: var(--glass-bg-strong); color: var(--fg); border-color: var(--accent); }
.tab.live.active { border-color: #ff453a; color: #ff453a; }
.form { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end; }
.fld { display: flex; flex-direction: column; gap: 4px; }
.fld label { font-size: 12px; color: var(--fg-dim); }
.tbl { width: 100%; border-collapse: collapse; font-size: 13px; }
.tbl th, .tbl td { text-align: left; padding: 9px 6px; border-bottom: 1px solid var(--glass-border); }
.tbl th { color: var(--fg-dim); font-weight: 600; }
.empty { text-align: center; color: var(--fg-dim); padding: 16px; }
</style>
