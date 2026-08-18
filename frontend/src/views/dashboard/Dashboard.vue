<template>
  <div class="dashboard">
    <!-- Page header -->
    <div class="page-header">
      <h1 class="page-title">{{ t("dashboard.title") }}</h1>
      <p class="page-sub">{{ t("dashboard.subtitle") }}</p>
    </div>

    <!-- Welcome banner -->
    <div class="welcome-banner">
      <div class="welcome-icon">
        <el-icon :size="32"><TrendCharts /></el-icon>
      </div>
      <div class="welcome-text">
        <div class="welcome-greeting">
          {{ t("dashboard.welcome", { username: auth.user?.username ?? "—" }) }}
        </div>
        <div class="welcome-hint">{{ t("dashboard.subtitle") }}</div>
      </div>
    </div>

    <!-- Credential selector row -->
    <div class="credential-row">
      <span class="field-label">{{ t("dashboard.credential") }}</span>
      <el-select
        v-model="selectedCredId"
        :placeholder="t('dashboard.selectCredential')"
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
          >{{ c.env === 'live' ? t('dashboard.envLive') : t('dashboard.envSim') }}</el-tag>
          <span style="color: var(--gray-400); margin-left: 6px; font-size: 12px">
            {{ c.api_key_masked }}
          </span>
        </el-option>
      </el-select>
      <el-button
        :loading="loading"
        :disabled="selectedCredId == null"
        @click="loadSummary"
      >
        {{ t("dashboard.refresh") }}
      </el-button>
    </div>

    <!-- Live environment warning banner -->
    <el-alert
      v-if="selectedCred?.env === 'live'"
      :title="t('dashboard.liveWarning')"
      type="error"
      :closable="false"
      show-icon
      class="env-banner"
    />

    <!-- No credential selected -->
    <div v-if="selectedCredId == null" class="no-cred-hint">
      <el-empty :description="t('dashboard.selectCredential')" />
    </div>

    <!-- Asset board (only when credential selected) -->
    <template v-else>
      <!-- Net value stat cards -->
      <div class="stat-row" v-loading="loading">
        <div class="stat-card">
          <div class="stat-value">{{ formatNetValue(summary?.net_value) }}</div>
          <div class="stat-label">{{ t("dashboard.netValue") }} ({{ t("dashboard.netValueUnit") }})</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ summary?.positions?.length ?? "—" }}</div>
          <div class="stat-label">{{ t("dashboard.positionCount") }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ summary?.currencies?.length ?? "—" }}</div>
          <div class="stat-label">{{ t("dashboard.currencyCount") }}</div>
        </div>
      </div>

      <!-- Currency distribution -->
      <div class="board-card" v-loading="loading">
        <div class="card-title">{{ t("dashboard.currencyDist") }}</div>
        <div class="currency-progress-list">
          <div
            v-for="cur in summary?.currencies ?? []"
            :key="cur.ccy"
            class="currency-progress-item"
          >
            <div class="currency-progress-label">
              <span class="ccy-name">{{ cur.ccy }}</span>
              <span class="ccy-usd">{{ formatUsd(cur.eqUsd) }} USD</span>
            </div>
            <el-progress
              :percentage="calcPercent(cur.eqUsd)"
              :text-inside="true"
              :stroke-width="20"
              :format="() => `${cur.ccy} ${calcPercent(cur.eqUsd)}%`"
            />
          </div>
          <el-empty
            v-if="!summary?.currencies?.length"
            :description="t('dashboard.noData')"
            :image-size="48"
          />
        </div>
        <ResponsiveTable
          v-if="summary?.currencies?.length"
          :columns="currencyColumns"
          :data="summary.currencies"
          row-key="ccy"
          :empty-text="t('dashboard.noData')"
          style="margin-top: 16px"
        />
      </div>

      <!-- Positions table -->
      <div class="board-card" v-loading="loading">
        <div class="card-title">{{ t("dashboard.positions") }}</div>
        <ResponsiveTable
          :columns="positionColumns"
          :data="summary?.positions ?? []"
          row-key="instId"
          :empty-text="t('dashboard.noData')"
        />
      </div>

      <!-- Bills table -->
      <div class="board-card" v-loading="loading">
        <div class="card-title">{{ t("dashboard.bills") }}</div>
        <ResponsiveTable
          :columns="billColumns"
          :data="summary?.bills ?? []"
          :empty-text="t('dashboard.noData')"
        />
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage } from "element-plus";
import { TrendCharts } from "@element-plus/icons-vue";
import { useAuthStore } from "@/stores/auth";
import { listCredentials, type Credential } from "@/api/credentials";
import { getAssetsSummary, type AssetsSummary } from "@/api/assets";
import ResponsiveTable, { type RTColumn } from "@/components/ResponsiveTable.vue";

const { t } = useI18n();
const auth = useAuthStore();

// ── 表格列定义(ResponsiveTable) ────────────────────────────────────────────────
const currencyColumns = computed<RTColumn[]>(() => [
  { prop: "ccy", label: t("dashboard.ccy"), width: 100 },
  { prop: "eqUsd", label: t("dashboard.eqUsd"), align: "right" },
  { prop: "ratio", label: t("dashboard.ratio"), align: "right", width: 100,
    formatter: (row) => `${calcPercent(row.eqUsd)}%` },
  { prop: "availBal", label: t("dashboard.availBal"), align: "right" },
  { prop: "frozenBal", label: t("dashboard.frozenBal"), align: "right" },
]);

const positionColumns = computed<RTColumn[]>(() => [
  { prop: "instId", label: t("dashboard.instId"), minWidth: 140 },
  { prop: "posSide", label: t("dashboard.posSide"), width: 80, align: "center" },
  { prop: "pos", label: t("dashboard.pos"), width: 80, align: "right" },
  { prop: "avgPx", label: t("dashboard.avgPx"), align: "right" },
  { prop: "upl", label: t("dashboard.upl"), align: "right",
    cellClass: (_row, v) => (parseFloat(v) >= 0 ? "profit" : "loss") },
  { prop: "notionalUsd", label: t("dashboard.notionalUsd"), align: "right", minWidth: 130 },
  { prop: "lever", label: t("dashboard.lever"), width: 80, align: "center" },
]);

const billColumns = computed<RTColumn[]>(() => [
  { prop: "ts", label: t("dashboard.billTime"), minWidth: 160, formatter: (row) => formatTs(row.ts) },
  { prop: "type", label: t("dashboard.billType"), width: 80, align: "center" },
  { prop: "ccy", label: t("dashboard.billCcy"), width: 90 },
  { prop: "balChg", label: t("dashboard.balChg"), align: "right",
    cellClass: (_row, v) => (parseFloat(v) >= 0 ? "profit" : "loss") },
  { prop: "fee", label: t("dashboard.fee"), align: "right" },
]);

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
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    ElMessage.error(err.response?.data?.detail ?? err.message ?? String(e));
  } finally {
    credLoading.value = false;
  }
}

function onCredChange() {
  if (selectedCredId.value != null) {
    loadSummary();
  }
}

// ── Assets summary ────────────────────────────────────────────────────────────
const summary = ref<AssetsSummary | null>(null);
const loading = ref(false);

async function loadSummary() {
  if (selectedCredId.value == null) return;
  loading.value = true;
  summary.value = null;
  try {
    summary.value = await getAssetsSummary(selectedCredId.value);
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    ElMessage.error(
      t("dashboard.loadError") + ": " + (err.response?.data?.detail ?? err.message ?? String(e)),
    );
  } finally {
    loading.value = false;
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function formatNetValue(val?: number): string {
  if (val == null) return "—";
  return val.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatUsd(eqUsd: string): string {
  const n = parseFloat(eqUsd);
  if (isNaN(n)) return eqUsd;
  return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function calcPercent(eqUsd: string): number {
  const netVal = summary.value?.net_value ?? 0;
  if (netVal <= 0) return 0;
  const n = parseFloat(eqUsd);
  if (isNaN(n)) return 0;
  return Math.min(100, Math.max(0, Math.round((n / netVal) * 100)));
}

function formatTs(ts: string): string {
  const n = Number(ts);
  if (isNaN(n)) return ts;
  return new Date(n).toLocaleString();
}

onMounted(async () => {
  await loadCredentials();
});
</script>

<style scoped>
.dashboard {
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}

.page-header { }
.page-title {
  margin: 0 0 var(--space-1);
  font-size: var(--font-size-2xl);
  font-weight: 700;
  color: var(--gray-800);
}
.page-sub {
  margin: 0;
  font-size: var(--font-size-base);
  color: var(--gray-500);
}

.welcome-banner {
  display: flex;
  align-items: center;
  gap: var(--space-5);
  padding: var(--space-6);
  background: linear-gradient(135deg, rgba(99, 91, 255, 0.08) 0%, rgba(0, 212, 255, 0.06) 100%);
  border: 1px solid rgba(99, 91, 255, 0.15);
  border-radius: var(--radius-xl);
}

.welcome-icon {
  width: 56px;
  height: 56px;
  border-radius: var(--radius-lg);
  background: var(--brand-gradient);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  flex: none;
}

.welcome-greeting {
  font-size: var(--font-size-xl);
  font-weight: 600;
  color: var(--gray-800);
}
.welcome-hint {
  font-size: var(--font-size-base);
  color: var(--gray-500);
  margin-top: 4px;
}

/* Credential selector */
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

/* Stat cards */
.stat-row {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: var(--space-4);
}

.stat-card {
  background: #fff;
  border: 1px solid var(--gray-200);
  border-radius: var(--radius-lg);
  padding: var(--space-5) var(--space-6);
  box-shadow: var(--shadow-xs);
}
.stat-card.accent {
  border-color: rgba(34, 197, 94, 0.3);
  background: var(--color-success-bg);
}

.stat-value {
  font-size: var(--font-size-2xl);
  font-weight: 700;
  color: var(--brand-primary);
  margin-bottom: var(--space-1);
}
.stat-card.accent .stat-value {
  color: var(--color-success);
}
.stat-label {
  font-size: var(--font-size-sm);
  color: var(--gray-500);
}

/* Board card (sections) */
.board-card {
  background: #fff;
  border: 1px solid var(--gray-200);
  border-radius: var(--radius-lg);
  padding: var(--space-5) var(--space-6);
  box-shadow: var(--shadow-xs);
}

.card-title {
  font-size: var(--font-size-md);
  font-weight: 600;
  color: var(--gray-700);
  margin-bottom: var(--space-4);
  display: block;
}

/* Currency distribution */
.currency-progress-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.currency-progress-item {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.currency-progress-label {
  display: flex;
  justify-content: space-between;
  font-size: var(--font-size-sm);
}

.ccy-name {
  font-weight: 600;
  color: var(--gray-700);
}

.ccy-usd {
  color: var(--gray-500);
}

/* P&L colors */
.profit {
  color: #26a17b;
  font-weight: 500;
}
.loss {
  color: #e84646;
  font-weight: 500;
}

.no-cred-hint {
  margin-top: var(--space-10);
}

:deep(.el-table th.el-table__cell > .cell) {
  text-align: center;
}
</style>
