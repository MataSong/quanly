<template>
  <div class="trading-panel">
    <!-- Page header -->
    <div class="page-header">
      <h2 class="page-title">{{ t("trading.title") }}</h2>
    </div>

    <!-- Credential selector -->
    <div class="credential-row">
      <span class="field-label">{{ t("trading.credential") }}</span>
      <el-select
        v-model="selectedCredId"
        :placeholder="t('trading.selectCredential')"
        style="width: 320px"
        :loading="credLoading"
        @change="onCredChange"
      >
        <el-option
          v-for="c in credentials"
          :key="c.id"
          :value="c.id"
          :label="`${c.label} · ${c.api_key_masked}`"
        >
          <span>{{ c.label }}</span>
          <el-tag
            :type="c.env === 'live' ? 'danger' : 'success'"
            size="small"
            style="margin-left: 8px"
          >{{ c.env === 'live' ? t('trading.envLive') : t('trading.envSim') }}</el-tag>
          <span style="color: var(--gray-400); margin-left: 6px; font-size: 12px">
            {{ c.api_key_masked }}
          </span>
        </el-option>
      </el-select>
    </div>

    <!-- Environment banner -->
    <el-alert
      v-if="selectedCred?.env === 'live'"
      :title="t('trading.liveBanner')"
      type="error"
      :closable="false"
      show-icon
      class="env-banner"
    />
    <el-alert
      v-else-if="selectedCred?.env === 'sim'"
      :title="t('trading.simBanner')"
      type="info"
      :closable="false"
      show-icon
      class="env-banner"
    />

    <!-- Main content (only when credential selected) -->
    <template v-if="selectedCred">
      <div class="main-grid">
        <!-- Left: order form -->
        <div class="order-card card">
          <div class="card-title">{{ t("trading.orderForm") }}</div>

          <!-- Instrument type tabs -->
          <el-radio-group v-model="instType" class="inst-tabs" @change="onInstTypeChange">
            <el-radio-button value="SPOT">{{ t("trading.spot") }}</el-radio-button>
            <el-radio-button value="SWAP">{{ t("trading.swap") }}</el-radio-button>
          </el-radio-group>

          <el-form label-width="110px" class="order-form">
            <!-- Instrument ID -->
            <el-form-item :label="t('trading.instId')">
              <el-autocomplete
                v-model="form.inst_id"
                :fetch-suggestions="suggestSymbols"
                :placeholder="instType === 'SPOT' ? 'BTC-USDT' : 'BTC-USDT-SWAP'"
                style="width: 100%"
                clearable
              />
            </el-form-item>

            <!-- Side -->
            <el-form-item :label="t('trading.side')">
              <el-radio-group v-model="form.side">
                <el-radio-button value="buy">
                  <span class="buy-text">{{ t("trading.buy") }}</span>
                </el-radio-button>
                <el-radio-button value="sell">
                  <span class="sell-text">{{ t("trading.sell") }}</span>
                </el-radio-button>
              </el-radio-group>
            </el-form-item>

            <!-- Order type -->
            <el-form-item :label="t('trading.ordType')">
              <el-radio-group v-model="form.ord_type">
                <el-radio-button value="market">{{ t("trading.market") }}</el-radio-button>
                <el-radio-button value="limit">{{ t("trading.limit") }}</el-radio-button>
              </el-radio-group>
            </el-form-item>

            <!-- Price (limit only) -->
            <el-form-item v-if="form.ord_type === 'limit'" :label="t('trading.price')">
              <el-input v-model="form.px" :placeholder="t('trading.pricePlaceholder')" />
            </el-form-item>

            <!-- Size -->
            <el-form-item :label="t('trading.size')">
              <el-input v-model="form.sz" :placeholder="t('trading.sizePlaceholder')" />
            </el-form-item>

            <!-- SWAP-specific fields -->
            <template v-if="instType === 'SWAP'">
              <el-form-item :label="t('trading.posSide')">
                <el-radio-group v-model="form.pos_side">
                  <el-radio-button value="long">{{ t("trading.long") }}</el-radio-button>
                  <el-radio-button value="short">{{ t("trading.short") }}</el-radio-button>
                </el-radio-group>
              </el-form-item>
              <el-form-item :label="t('trading.tdMode')">
                <el-radio-group v-model="form.td_mode">
                  <el-radio-button value="cross">{{ t("trading.cross") }}</el-radio-button>
                  <el-radio-button value="isolated">{{ t("trading.isolated") }}</el-radio-button>
                </el-radio-group>
              </el-form-item>
              <el-form-item :label="t('trading.reduceOnly')">
                <el-switch v-model="form.reduce_only" />
              </el-form-item>
            </template>

            <!-- Submit -->
            <el-form-item>
              <el-button
                type="primary"
                :class="{ 'is-live': selectedCred.env === 'live' }"
                :loading="placing"
                @click="onPlaceOrder"
                style="width: 100%"
              >
                {{ selectedCred.env === 'live'
                  ? t('trading.placeOrderLive')
                  : t('trading.placeOrder') }}
              </el-button>
            </el-form-item>
          </el-form>
        </div>

        <!-- Right: monitor panels -->
        <div class="monitor-col">
          <!-- Balance -->
          <div class="card monitor-card">
            <div class="card-title-row">
              <span class="card-title">{{ t("trading.balance") }}</span>
              <el-button size="small" :loading="balanceLoading" @click="reloadBalance">
                {{ t("common.refresh") }}
              </el-button>
            </div>
            <el-table :data="balance" size="small" border v-loading="balanceLoading">
              <el-table-column prop="ccy" :label="t('trading.ccy')" width="80" />
              <el-table-column prop="bal" :label="t('trading.bal')" align="right" />
              <el-table-column prop="availBal" :label="t('trading.availBal')" align="right" />
              <el-table-column prop="frozenBal" :label="t('trading.frozenBal')" align="right" />
            </el-table>
          </div>

          <!-- Positions (SWAP only) -->
          <div v-if="instType === 'SWAP'" class="card monitor-card">
            <div class="card-title-row">
              <span class="card-title">{{ t("trading.positions") }}</span>
              <el-button size="small" :loading="posLoading" @click="reloadPositions">
                {{ t("common.refresh") }}
              </el-button>
            </div>
            <el-table :data="positions" size="small" border v-loading="posLoading">
              <el-table-column prop="instId" :label="t('trading.instId')" min-width="120" />
              <el-table-column prop="posSide" :label="t('trading.posSide')" width="70" align="center" />
              <el-table-column prop="pos" :label="t('trading.pos')" width="70" align="right" />
              <el-table-column prop="avgPx" :label="t('trading.avgPx')" align="right" />
              <el-table-column prop="upl" :label="t('trading.upl')" align="right">
                <template #default="{ row }">
                  <span :class="parseFloat(row.upl) >= 0 ? 'profit' : 'loss'">
                    {{ row.upl }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column prop="lever" :label="t('trading.lever')" width="60" align="center" />
            </el-table>
          </div>

          <!-- Open orders -->
          <div class="card monitor-card">
            <div class="card-title-row">
              <span class="card-title">{{ t("trading.openOrders") }}</span>
              <el-button size="small" :loading="ordersLoading" @click="reloadOrders">
                {{ t("common.refresh") }}
              </el-button>
            </div>
            <el-table :data="orders" size="small" border v-loading="ordersLoading">
              <el-table-column prop="instId" :label="t('trading.instId')" min-width="110" />
              <el-table-column prop="side" :label="t('trading.side')" width="60" align="center">
                <template #default="{ row }">
                  <span :class="row.side === 'buy' ? 'buy-text' : 'sell-text'">
                    {{ row.side === 'buy' ? t('trading.buy') : t('trading.sell') }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column prop="ordType" :label="t('trading.ordType')" width="70" align="center" />
              <el-table-column prop="sz" :label="t('trading.size')" width="80" align="right" />
              <el-table-column prop="px" :label="t('trading.price')" align="right" />
              <el-table-column prop="fillSz" :label="t('trading.filled')" align="right" />
              <el-table-column :label="t('common.actions')" width="80" align="center">
                <template #default="{ row }">
                  <el-button
                    size="small"
                    type="danger"
                    :loading="cancellingId === row.ordId"
                    @click="onCancelOrder(row)"
                  >
                    {{ t("trading.cancel") }}
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>
      </div>
    </template>

    <!-- No credential selected placeholder -->
    <div v-else class="no-cred-hint">
      <el-empty :description="t('trading.selectCredentialHint')" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage, ElMessageBox } from "element-plus";
import { listCredentials, type Credential } from "@/api/credentials";
import {
  placeOrder,
  cancelOrder,
  getOrders,
  getPositions,
  getBalance,
  type OrderItem,
  type PositionItem,
  type BalanceItem,
} from "@/api/trading";
import { formatApiError } from "@/utils/errors";

const { t } = useI18n();

// ── Credentials ───────────────────────────────────────────────────────────────
const credentials = ref<Credential[]>([]);
const credLoading = ref(false);
const selectedCredId = ref<number | null>(null);

const selectedCred = computed<Credential | undefined>(
  () => credentials.value.find((c) => c.id === selectedCredId.value),
);

async function loadCredentials() {
  credLoading.value = true;
  try {
    credentials.value = await listCredentials();
  } catch (e) {
    ElMessage.error(formatApiError(e, "credentials"));
  } finally {
    credLoading.value = false;
  }
}

function onCredChange() {
  if (selectedCredId.value != null) {
    reloadAll();
  }
}

// ── Instrument type ───────────────────────────────────────────────────────────
const instType = ref<"SPOT" | "SWAP">("SPOT");

function onInstTypeChange() {
  // reset pos_side / td_mode to defaults when switching
  if (instType.value === "SPOT") {
    form.td_mode = "cash";
    form.pos_side = undefined;
    form.reduce_only = false;
  } else {
    form.td_mode = "cross";
    form.pos_side = "long";
  }
  reloadAll();
}

// ── Order form ────────────────────────────────────────────────────────────────
const form = reactive<{
  inst_id: string;
  side: "buy" | "sell";
  ord_type: "market" | "limit";
  sz: string;
  px: string;
  pos_side?: "long" | "short";
  td_mode: "cash" | "cross" | "isolated";
  reduce_only: boolean;
}>({
  inst_id: "",
  side: "buy",
  ord_type: "market",
  sz: "",
  px: "",
  td_mode: "cash",
  reduce_only: false,
});

// Common symbols for autocomplete suggestions
const SPOT_SYMBOLS = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "BNB-USDT", "XRP-USDT"];
const SWAP_SYMBOLS = [
  "BTC-USDT-SWAP",
  "ETH-USDT-SWAP",
  "SOL-USDT-SWAP",
  "BNB-USDT-SWAP",
  "XRP-USDT-SWAP",
];

function suggestSymbols(
  query: string,
  cb: (results: { value: string }[]) => void,
) {
  const list = instType.value === "SPOT" ? SPOT_SYMBOLS : SWAP_SYMBOLS;
  const upper = query.toUpperCase();
  cb(
    list
      .filter((s) => !upper || s.includes(upper))
      .map((s) => ({ value: s })),
  );
}

const placing = ref(false);

async function onPlaceOrder() {
  // Validate
  if (!form.inst_id.trim()) {
    ElMessage.warning(t("trading.instIdRequired"));
    return;
  }
  if (!form.sz.trim()) {
    ElMessage.warning(t("trading.sizeRequired"));
    return;
  }
  if (form.ord_type === "limit" && !form.px.trim()) {
    ElMessage.warning(t("trading.priceRequired"));
    return;
  }
  if (!selectedCredId.value) return;

  // Live-env second confirmation
  if (selectedCred.value?.env === "live") {
    try {
      await ElMessageBox.confirm(
        t("trading.liveConfirmMsg", {
          instId: form.inst_id,
          side: form.side === "buy" ? t("trading.buy") : t("trading.sell"),
          sz: form.sz,
        }),
        t("trading.liveConfirmTitle"),
        {
          type: "error",
          confirmButtonText: t("trading.confirmPlace"),
          cancelButtonText: t("common.cancel"),
          confirmButtonClass: "el-button--danger",
        },
      );
    } catch {
      return; // user cancelled
    }
  }

  placing.value = true;
  try {
    const payload = {
      credential_id: selectedCredId.value!,
      inst_type: instType.value,
      inst_id: form.inst_id.trim(),
      side: form.side,
      ord_type: form.ord_type,
      sz: form.sz.trim(),
      ...(form.ord_type === "limit" ? { px: form.px.trim() } : {}),
      ...(instType.value === "SWAP"
        ? {
            pos_side: form.pos_side,
            td_mode: form.td_mode,
            reduce_only: form.reduce_only,
          }
        : { td_mode: "cash" as const }),
    };
    const res = await placeOrder(payload);
    ElMessage.success(t("trading.placeSuccess", { ordId: res.okx.ordId }));
    // Refresh orders after placing
    await reloadOrders();
  } catch (e) {
    ElMessage.error(formatApiError(e, "trading"));
  } finally {
    placing.value = false;
  }
}

// ── Monitor: balance ──────────────────────────────────────────────────────────
const balance = ref<BalanceItem[]>([]);
const balanceLoading = ref(false);

async function reloadBalance() {
  if (!selectedCredId.value) return;
  balanceLoading.value = true;
  try {
    balance.value = await getBalance(selectedCredId.value);
  } catch (e) {
    ElMessage.error(formatApiError(e, "trading"));
  } finally {
    balanceLoading.value = false;
  }
}

// ── Monitor: positions ────────────────────────────────────────────────────────
const positions = ref<PositionItem[]>([]);
const posLoading = ref(false);

async function reloadPositions() {
  if (!selectedCredId.value) return;
  posLoading.value = true;
  try {
    positions.value = await getPositions(selectedCredId.value, instType.value);
  } catch (e) {
    ElMessage.error(formatApiError(e, "trading"));
  } finally {
    posLoading.value = false;
  }
}

// ── Monitor: open orders ──────────────────────────────────────────────────────
const orders = ref<OrderItem[]>([]);
const ordersLoading = ref(false);
const cancellingId = ref<string | null>(null);

async function reloadOrders() {
  if (!selectedCredId.value) return;
  ordersLoading.value = true;
  try {
    orders.value = await getOrders(selectedCredId.value, instType.value);
  } catch (e) {
    ElMessage.error(formatApiError(e, "trading"));
  } finally {
    ordersLoading.value = false;
  }
}

async function onCancelOrder(row: OrderItem) {
  if (!selectedCredId.value) return;
  cancellingId.value = row.ordId;
  try {
    await cancelOrder({
      credential_id: selectedCredId.value,
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

function reloadAll() {
  reloadBalance();
  reloadPositions();
  reloadOrders();
}

onMounted(async () => {
  await loadCredentials();
});
</script>

<style scoped>
.trading-panel {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.page-title {
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: 600;
  color: var(--gray-800);
}

.credential-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.field-label {
  font-size: var(--font-size-sm);
  color: var(--gray-600);
  white-space: nowrap;
}

.env-banner {
  border-radius: var(--radius-md);
}

/* Main grid: form left | monitors right */
.main-grid {
  display: grid;
  grid-template-columns: 380px 1fr;
  gap: var(--space-5);
  align-items: start;
}

@media (max-width: 900px) {
  .main-grid {
    grid-template-columns: 1fr;
  }
}

.card {
  background: #fff;
  border: 1px solid var(--gray-200);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
}

.card-title {
  font-size: var(--font-size-md);
  font-weight: 600;
  color: var(--gray-700);
  margin-bottom: var(--space-4);
  display: block;
}

.card-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-3);
}

.card-title-row .card-title {
  margin-bottom: 0;
}

.inst-tabs {
  margin-bottom: var(--space-4);
}

.order-form {
  margin-top: var(--space-2);
}

.monitor-col {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.monitor-card {
  overflow-x: auto;
}

/* Live button */
.el-button.is-live {
  background-color: var(--el-color-danger);
  border-color: var(--el-color-danger);
}
.el-button.is-live:hover {
  background-color: var(--el-color-danger-light-3);
  border-color: var(--el-color-danger-light-3);
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
.profit {
  color: #26a17b;
}
.loss {
  color: #e84646;
}

.no-cred-hint {
  margin-top: var(--space-10);
}

:deep(.el-table th.el-table__cell > .cell) {
  text-align: center;
}
</style>
