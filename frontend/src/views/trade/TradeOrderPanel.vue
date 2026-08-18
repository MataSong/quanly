<template>
  <div class="order-panel">
    <!-- No credential selected -->
    <div v-if="!store.credentialId" class="no-cred">
      <el-alert
        :title="t('trading.selectCredentialHint')"
        type="info"
        :closable="false"
        show-icon
      />
    </div>

    <template v-else>
      <!-- Instrument type tabs -->
      <el-radio-group
        :model-value="store.instType"
        class="inst-tabs"
        @update:model-value="(v: 'SPOT' | 'SWAP') => onInstTypeChange(v)"
      >
        <el-radio-button value="SPOT">{{ t("trading.spot") }}</el-radio-button>
        <el-radio-button value="SWAP">{{ t("trading.swap") }}</el-radio-button>
      </el-radio-group>

      <el-form
        :label-position="isMobile ? 'top' : 'right'"
        label-width="110px"
        class="order-form"
        :disabled="!store.credentialId"
      >
        <!-- Instrument ID -->
        <el-form-item :label="t('trading.instId')">
          <el-autocomplete
            v-model="form.inst_id"
            :fetch-suggestions="suggestSymbols"
            :placeholder="store.instType === 'SPOT' ? 'BTC-USDT' : 'BTC-USDT-SWAP'"
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
        <template v-if="store.instType === 'SWAP'">
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
            :class="{ 'is-live': isLive }"
            :loading="placing"
            style="width: 100%"
            @click="onPlaceOrder"
          >
            {{ isLive ? t("trading.placeOrderLive") : t("trading.placeOrder") }}
          </el-button>
        </el-form-item>
      </el-form>
    </template>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, watch, computed } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage, ElMessageBox } from "element-plus";
import { useTradeDeskStore } from "@/stores/tradeDesk";
import { useBreakpoint } from "@/composables/useBreakpoint";
import { placeOrder } from "@/api/trading";
import { formatApiError } from "@/utils/errors";

const { t } = useI18n();
const { isMobile } = useBreakpoint();
const store = useTradeDeskStore();

const emit = defineEmits<{
  (e: "placed"): void;
}>();

// ── Credential env — read from store (set by parent TradeDesk when cred selected) ──
const isLive = computed(() => store.credentialEnv === "live");

// ── Symbol suggestions ───────────────────────────────────────────────────────
const SPOT_SYMBOLS = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "BNB-USDT", "XRP-USDT"];
const SWAP_SYMBOLS = [
  "BTC-USDT-SWAP",
  "ETH-USDT-SWAP",
  "SOL-USDT-SWAP",
  "BNB-USDT-SWAP",
  "XRP-USDT-SWAP",
];

function suggestSymbols(query: string, cb: (results: { value: string }[]) => void) {
  const list = store.instType === "SPOT" ? SPOT_SYMBOLS : SWAP_SYMBOLS;
  const upper = query.toUpperCase();
  cb(list.filter((s) => !upper || s.includes(upper)).map((s) => ({ value: s })));
}

// ── Order form ───────────────────────────────────────────────────────────────
const form = reactive<{
  inst_id: string;
  side: "buy" | "sell";
  ord_type: "market" | "limit";
  sz: string;
  px: string;
  pos_side: "long" | "short";
  td_mode: "cash" | "cross" | "isolated";
  reduce_only: boolean;
}>({
  inst_id: store.symbol,
  side: "buy",
  ord_type: "market",
  sz: "",
  px: "",
  pos_side: "long",
  td_mode: "cash",
  reduce_only: false,
});

// Keep inst_id in sync with store.symbol when symbol changes from outside
watch(
  () => store.symbol,
  (s) => {
    form.inst_id = s;
  },
);

// Reset SWAP-specific fields on instType change
function onInstTypeChange(v: "SPOT" | "SWAP") {
  store.setInstType(v);
  if (v === "SPOT") {
    form.td_mode = "cash";
    form.pos_side = "long";
    form.reduce_only = false;
  } else {
    form.td_mode = "cross";
    form.pos_side = "long";
  }
}

// ── Place order ──────────────────────────────────────────────────────────────
const placing = ref(false);

async function onPlaceOrder() {
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
  if (!store.credentialId) return;

  // Live-env second confirmation
  if (isLive.value) {
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
      credential_id: store.credentialId!,
      inst_type: store.instType,
      inst_id: form.inst_id.trim(),
      side: form.side,
      ord_type: form.ord_type,
      sz: form.sz.trim(),
      ...(form.ord_type === "limit" ? { px: form.px.trim() } : {}),
      ...(store.instType === "SWAP"
        ? {
            pos_side: form.pos_side,
            td_mode: form.td_mode,
            reduce_only: form.reduce_only,
          }
        : { td_mode: "cash" as const }),
    };
    const res = await placeOrder(payload);
    ElMessage.success(t("trading.placeSuccess", { ordId: res.okx.ordId }));
    emit("placed");
  } catch (e) {
    ElMessage.error(formatApiError(e, "trading"));
  } finally {
    placing.value = false;
  }
}
</script>

<style scoped>
.order-panel {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.no-cred {
  padding: var(--space-2) 0;
}

.inst-tabs {
  margin-bottom: var(--space-4);
}

.order-form {
  margin-top: var(--space-2);
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
</style>
