<template>
  <div class="trade-monitor">
    <!-- No credential selected -->
    <div v-if="!store.credentialId" class="no-cred">
      <el-empty :description="t('trading.selectCredentialHint')" :image-size="80" />
    </div>

    <template v-else>
      <!-- Balance -->
      <div class="monitor-card card" v-loading="balanceLoading">
        <div class="card-title-row">
          <span class="card-title">{{ t("trading.balance") }}</span>
          <el-button size="small" :loading="balanceLoading" @click="reloadBalance">
            {{ t("common.refresh") }}
          </el-button>
        </div>
        <ResponsiveTable
          :columns="balanceCols"
          :data="balance"
          :empty-text="t('common.empty')"
        />
      </div>

      <!-- Positions (SWAP only) -->
      <div v-if="store.instType === 'SWAP'" class="monitor-card card" v-loading="posLoading">
        <div class="card-title-row">
          <span class="card-title">{{ t("trading.positions") }}</span>
          <el-button size="small" :loading="posLoading" @click="reloadPositions">
            {{ t("common.refresh") }}
          </el-button>
        </div>
        <ResponsiveTable
          :columns="positionsCols"
          :data="positions"
          :empty-text="t('common.empty')"
        />
      </div>

      <!-- Open orders -->
      <div class="monitor-card card" v-loading="ordersLoading">
        <div class="card-title-row">
          <span class="card-title">{{ t("trading.openOrders") }}</span>
          <el-button size="small" :loading="ordersLoading" @click="reloadOrders">
            {{ t("common.refresh") }}
          </el-button>
        </div>
        <ResponsiveTable
          :columns="ordersCols"
          :data="orders"
          :empty-text="t('common.empty')"
        >
          <template #cell-side="{ row }">
            <span :class="row.side === 'buy' ? 'buy-text' : 'sell-text'">
              {{ row.side === "buy" ? t("trading.buy") : t("trading.sell") }}
            </span>
          </template>
          <template #cell-actions="{ row }">
            <el-button
              size="small"
              type="danger"
              :loading="cancellingId === row.ordId"
              @click="onCancelOrder(row as OrderItem)"
            >
              {{ t("trading.cancel") }}
            </el-button>
          </template>
        </ResponsiveTable>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage } from "element-plus";
import { useTradeDeskStore } from "@/stores/tradeDesk";
import {
  getBalance,
  getPositions,
  getOrders,
  cancelOrder,
  type BalanceItem,
  type PositionItem,
  type OrderItem,
} from "@/api/trading";
import { formatApiError } from "@/utils/errors";
import ResponsiveTable, { type RTColumn } from "@/components/ResponsiveTable.vue";

const { t } = useI18n();
const store = useTradeDeskStore();

// ── Balance ──────────────────────────────────────────────────────────────────
const balance = ref<BalanceItem[]>([]);
const balanceLoading = ref(false);

async function reloadBalance() {
  if (!store.credentialId) return;
  balanceLoading.value = true;
  try {
    balance.value = await getBalance(store.credentialId);
  } catch (e) {
    ElMessage.error(formatApiError(e, "trading"));
  } finally {
    balanceLoading.value = false;
  }
}

// ── Positions ────────────────────────────────────────────────────────────────
const positions = ref<PositionItem[]>([]);
const posLoading = ref(false);

async function reloadPositions() {
  if (!store.credentialId) return;
  posLoading.value = true;
  try {
    positions.value = await getPositions(store.credentialId, store.instType);
  } catch (e) {
    ElMessage.error(formatApiError(e, "trading"));
  } finally {
    posLoading.value = false;
  }
}

// ── Open orders ──────────────────────────────────────────────────────────────
const orders = ref<OrderItem[]>([]);
const ordersLoading = ref(false);
const cancellingId = ref<string | null>(null);

async function reloadOrders() {
  if (!store.credentialId) return;
  ordersLoading.value = true;
  try {
    orders.value = await getOrders(store.credentialId, store.instType);
  } catch (e) {
    ElMessage.error(formatApiError(e, "trading"));
  } finally {
    ordersLoading.value = false;
  }
}

async function onCancelOrder(row: OrderItem) {
  if (!store.credentialId) return;
  cancellingId.value = row.ordId;
  try {
    await cancelOrder({
      credential_id: store.credentialId,
      inst_id: row.instId,
      ord_id: row.ordId,
    });
    ElMessage.success(t("trading.cancelSuccess"));
    await reloadOrders();
  } catch (e) {
    ElMessage.error(formatApiError(e, "trading"));
  } finally {
    cancellingId.value = null;
  }
}

// ── Reload all three panels ──────────────────────────────────────────────────
function reloadAll() {
  reloadBalance();
  reloadPositions();
  reloadOrders();
}

/** Exposed so parent (TradeDesk) can call after a successful order */
defineExpose({ reload: reloadAll });

// Reload when credential changes
watch(
  () => store.credentialId,
  (id) => {
    if (id != null) reloadAll();
    else {
      balance.value = [];
      positions.value = [];
      orders.value = [];
    }
  },
);

// Reload positions+orders when instType changes
watch(
  () => store.instType,
  () => {
    if (store.credentialId) {
      reloadPositions();
      reloadOrders();
    }
  },
);

onMounted(() => {
  if (store.credentialId) reloadAll();
});

// ── Table column definitions ─────────────────────────────────────────────────
const balanceCols = computed<RTColumn[]>(() => [
  { prop: "ccy", label: t("trading.ccy"), width: 80 },
  { prop: "bal", label: t("trading.bal"), align: "right" },
  { prop: "availBal", label: t("trading.availBal"), align: "right" },
  { prop: "frozenBal", label: t("trading.frozenBal"), align: "right" },
]);

const positionsCols = computed<RTColumn[]>(() => [
  { prop: "instId", label: t("trading.instId"), minWidth: 120 },
  { prop: "posSide", label: t("trading.posSide"), width: 70, align: "center" },
  { prop: "pos", label: t("trading.pos"), width: 70, align: "right" },
  { prop: "avgPx", label: t("trading.avgPx"), align: "right" },
  {
    prop: "upl",
    label: t("trading.upl"),
    align: "right",
    cellClass: (_row: Record<string, any>, v: any) =>
      parseFloat(v) >= 0 ? "profit" : "loss",
  },
  { prop: "lever", label: t("trading.lever"), width: 60, align: "center" },
]);

const ordersCols = computed<RTColumn[]>(() => [
  { prop: "instId", label: t("trading.instId"), minWidth: 110 },
  { prop: "side", label: t("trading.side"), width: 60, align: "center" },
  { prop: "ordType", label: t("trading.ordType"), width: 70, align: "center" },
  { prop: "sz", label: t("trading.size"), width: 80, align: "right" },
  { prop: "px", label: t("trading.price"), align: "right" },
  { prop: "fillSz", label: t("trading.filled"), align: "right" },
  { prop: "actions", label: t("common.actions"), width: 80, align: "center" },
]);
</script>

<style scoped>
.trade-monitor {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.no-cred {
  padding: var(--space-6) 0;
}

.card {
  background: #fff;
  border: 1px solid var(--gray-200);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
  overflow-x: auto;
}

.card-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-3);
}

.card-title {
  font-size: var(--font-size-md);
  font-weight: 600;
  color: var(--gray-700);
}

/* Buy/sell colors */
.buy-text {
  color: #26a17b;
  font-weight: 600;
}
.sell-text {
  color: #e84646;
  font-weight: 600;
}

/* P&L colors */
:deep(.profit) {
  color: #26a17b;
}
:deep(.loss) {
  color: #e84646;
}
</style>
