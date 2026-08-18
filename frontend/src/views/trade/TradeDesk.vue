<template>
  <div class="trade-desk">
    <!-- Page title -->
    <div class="page-header">
      <h2 class="page-title">{{ t("trade.title") }}</h2>
    </div>

    <!-- Live-env warning banner -->
    <el-alert
      v-if="isLive"
      :title="t('trade.liveWarning')"
      type="error"
      :closable="false"
      show-icon
      class="live-banner"
    />
    <!-- Sim-env info banner -->
    <el-alert
      v-else-if="store.credentialEnv === 'sim'"
      :title="t('trading.simBanner')"
      type="info"
      :closable="false"
      show-icon
      class="live-banner"
    />

    <!-- Top shared selector bar -->
    <div class="selector-bar">
      <!-- Symbol -->
      <div class="selector-item">
        <span class="selector-label">{{ t("trade.selectSymbol") }}</span>
        <el-select
          v-model="selectedSymbol"
          filterable
          :placeholder="t('trade.selectSymbol')"
          style="width: 160px"
          @change="store.setSymbol"
        >
          <el-option
            v-for="sym in symbols"
            :key="sym.instId"
            :value="sym.instId"
            :label="sym.instId"
          />
        </el-select>
      </div>

      <!-- Bar/interval -->
      <div class="selector-item">
        <span class="selector-label">{{ t("trade.bar") }}</span>
        <el-select
          v-model="selectedBar"
          style="width: 100px"
          @change="store.setBar"
        >
          <el-option v-for="b in BAR_OPTIONS" :key="b" :value="b" :label="b" />
        </el-select>
      </div>

      <!-- Credential -->
      <div class="selector-item">
        <span class="selector-label">{{ t("trade.selectCredential") }}</span>
        <el-select
          v-model="selectedCredId"
          :loading="credLoading"
          :placeholder="t('trade.selectCredential')"
          clearable
          style="width: 200px"
          @change="onCredentialChange"
        >
          <el-option
            v-for="cred in credentials"
            :key="cred.id"
            :value="cred.id"
            :label="`${cred.label} · ${cred.api_key_masked}`"
          >
            <span>{{ cred.label }}</span>
            <el-tag
              :type="cred.env === 'live' ? 'danger' : 'success'"
              size="small"
              style="margin-left: 8px"
            >
              {{ cred.env === "live" ? t("trading.envLive") : t("trading.envSim") }}
            </el-tag>
            <span style="color: var(--gray-400); margin-left: 6px; font-size: 12px">
              {{ cred.api_key_masked }}
            </span>
          </el-option>
        </el-select>
      </div>
    </div>

    <!-- Main layout: PC grid, mobile single-column -->
    <div class="desk-layout">
      <!-- Left/top: K-line chart -->
      <div class="chart-area">
        <TradeChart />
      </div>

      <!-- Right/inline: order panel -->
      <div class="order-area card">
        <TradeOrderPanel @placed="onOrderPlaced" />
      </div>
    </div>

    <!-- Full-width monitor area -->
    <div class="monitor-area">
      <TradeMonitor ref="monitorRef" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { useTradeDeskStore } from "@/stores/tradeDesk";
import { getSymbols, type Symbol } from "@/api/market";
import { listCredentials, type Credential } from "@/api/credentials";
import TradeChart from "./TradeChart.vue";
import TradeOrderPanel from "./TradeOrderPanel.vue";
import TradeMonitor from "./TradeMonitor.vue";

const { t } = useI18n();
const store = useTradeDeskStore();

const BAR_OPTIONS = ["1m", "3m", "5m", "15m", "30m", "1H", "4H", "1D"];

// ── Symbol selector ──────────────────────────────────────────────────────────
const symbols = ref<Symbol[]>([]);
const selectedSymbol = ref(store.symbol);

async function loadSymbols() {
  try {
    symbols.value = await getSymbols();
  } catch {
    // fallback: keep whatever is in store
  }
}

// ── Bar selector ─────────────────────────────────────────────────────────────
const selectedBar = ref(store.bar);

// ── Credential selector ──────────────────────────────────────────────────────
const credentials = ref<Credential[]>([]);
const credLoading = ref(false);
const selectedCredId = ref<number | null>(store.credentialId);

async function loadCredentials() {
  credLoading.value = true;
  try {
    credentials.value = await listCredentials();
  } catch {
    // silently ignore
  } finally {
    credLoading.value = false;
  }
}

function onCredentialChange(id: number | null) {
  store.setCredential(id ?? null);
  const cred = credentials.value.find((c) => c.id === id);
  store.setCredentialEnv(cred?.env ?? null);
}

const isLive = computed(() => store.credentialEnv === "live");

// ── Monitor ref for reload after order placed ────────────────────────────────
const monitorRef = ref<InstanceType<typeof TradeMonitor> | null>(null);

function onOrderPlaced() {
  monitorRef.value?.reload();
}

// ── Init ─────────────────────────────────────────────────────────────────────
onMounted(() => {
  loadSymbols();
  loadCredentials();
});
</script>

<style scoped lang="scss">
@use "@/styles/mixins" as *;

.trade-desk {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.page-header {
  display: flex;
  align-items: center;
}

.page-title {
  font-size: var(--font-size-xl);
  font-weight: 600;
  color: var(--gray-800);
  margin: 0;
}

.live-banner {
  margin-bottom: 0;
}

/* Selector bar */
.selector-bar {
  display: flex;
  align-items: center;
  gap: var(--space-5);
  flex-wrap: wrap;
  background: #fff;
  border: 1px solid var(--gray-200);
  border-radius: var(--radius-lg);
  padding: var(--space-3) var(--space-5);

  @include mobile {
    gap: var(--space-3);
    padding: var(--space-3);
  }
}

.selector-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.selector-label {
  font-size: var(--font-size-sm);
  color: var(--gray-600);
  white-space: nowrap;
}

/* Main layout: PC grid */
.desk-layout {
  display: grid;
  grid-template-columns: 1fr 360px;
  gap: var(--space-4);
  align-items: start;

  @include mobile {
    grid-template-columns: 1fr;
  }
}

.chart-area {
  min-width: 0; /* prevent overflow in grid */
}

.order-area {
  min-width: 0;
}

.card {
  background: #fff;
  border: 1px solid var(--gray-200);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
}
</style>
