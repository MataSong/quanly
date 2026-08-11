<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { assetsApi } from "@/api/assets";
import Pagination from "@/components/Pagination.vue";
import { usePagination } from "@/composables/usePagination";

const env = ref<"sim" | "live">("sim");
const bills = ref<any[]>([]);
const { page, pageSize, total, totalPages, paged } = usePagination(bills, 10);

async function load() {
  const r = await assetsApi.bills(env.value);
  bills.value = r.data;
}

watch(env, load);
onMounted(load);
</script>

<template>
  <div class="glass panel">
    <div class="head">
      <h2>{{ $t("bills.title") }}</h2>
      <div class="env-switch">
        <button class="tab" :class="{ active: env === 'sim' }" @click="env = 'sim'">
          {{ $t("trade.sim") }}
        </button>
        <button class="tab live" :class="{ active: env === 'live' }" @click="env = 'live'">
          {{ $t("trade.live") }}
        </button>
      </div>
    </div>
    <table class="tbl">
      <thead>
        <tr>
          <th>{{ $t("bills.time") }}</th>
          <th>{{ $t("bills.type") }}</th>
          <th>{{ $t("bills.symbol") }}</th>
          <th>{{ $t("bills.ccy") }}</th>
          <th>{{ $t("bills.amount") }}</th>
          <th>{{ $t("bills.balanceAfter") }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="b in paged" :key="b.id">
          <td>{{ new Date(b.ts).toLocaleString() }}</td>
          <td>{{ $t("bills." + b.bill_type) }}</td>
          <td>{{ b.symbol || "—" }}</td>
          <td>{{ b.ccy }}</td>
          <td :class="b.amount >= 0 ? 'up' : 'down'">
            {{ b.amount.toLocaleString(undefined, { maximumFractionDigits: 4 }) }}
          </td>
          <td>{{ b.balance_after.toLocaleString(undefined, { maximumFractionDigits: 4 }) }}</td>
        </tr>
        <tr v-if="total === 0">
          <td colspan="6" class="empty">{{ $t("bills.empty") }}</td>
        </tr>
      </tbody>
    </table>
    <Pagination
      v-if="total > 0"
      v-model:page="page"
      v-model:pageSize="pageSize"
      :total="total"
      :totalPages="totalPages"
    />
  </div>
</template>

<style scoped>
.panel {
  padding: 24px;
}
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
h2 {
  margin: 0;
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
.tbl {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.tbl th,
.tbl td {
  text-align: left;
  padding: 9px 6px;
  border-bottom: 1px solid var(--glass-border);
}
.tbl th {
  color: var(--fg-dim);
  font-weight: 600;
}
.up {
  color: #30d158;
}
.down {
  color: #ff453a;
}
.empty {
  text-align: center;
  color: var(--fg-dim);
  padding: 16px;
}
</style>
