<template>
  <div class="strategy-page">
    <!-- Page header -->
    <div class="page-header">
      <h2 class="page-title">{{ t("strategy.title") }}</h2>
      <el-button type="primary" :icon="Plus" @click="openCreateDialog">
        {{ t("strategy.newRun") }}
      </el-button>
    </div>

    <!-- Built-in strategies info cards -->
    <div class="strategy-cards">
      <div
        v-for="s in strategies"
        :key="s.id"
        class="strategy-card card"
        :class="{ selected: selectedStrategyId === s.id }"
        @click="selectedStrategyId = s.id"
      >
        <div class="sc-name">{{ s.name }}</div>
        <div class="sc-code">{{ s.code_ref }}</div>
        <div class="sc-params">
          <span v-for="(v, k) in s.default_params" :key="String(k)" class="sc-param">
            {{ k }}: <strong>{{ v }}</strong>
          </span>
        </div>
      </div>
      <el-empty v-if="!strategies.length && !strategiesLoading" :description="t('common.empty')" />
    </div>

    <!-- My runs table -->
    <div class="card runs-card">
      <div class="card-title-row">
        <span class="card-title">{{ t("strategy.runs") }}</span>
        <el-button size="small" :loading="runsLoading" @click="loadRuns">
          {{ t("common.refresh") }}
        </el-button>
      </div>
      <el-table :data="runs" size="small" border v-loading="runsLoading" empty-text="">
        <!-- Problem 2: show run name as primary column -->
        <el-table-column :label="t('strategy.colName')" min-width="160">
          <template #default="{ row }">{{ row.name || row.strategy_name }}</template>
        </el-table-column>
        <el-table-column :label="t('strategy.colStrategy')" min-width="120">
          <template #default="{ row }">{{ row.strategy_name }}</template>
        </el-table-column>
        <el-table-column :label="t('strategy.colSymbol')" width="140">
          <template #default="{ row }">{{ row.symbol }}</template>
        </el-table-column>
        <el-table-column :label="t('strategy.colEnv')" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.credential_env === 'live' ? 'danger' : 'success'" size="small">
              {{ row.credential_env === 'live' ? t('strategy.envLive') : t('strategy.envSim') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('strategy.colStatus')" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">
              {{ t(`strategy.status.${row.status}`) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('strategy.colCredential')" min-width="120">
          <template #default="{ row }">{{ row.credential_label }}</template>
        </el-table-column>
        <el-table-column :label="t('common.createdAt')" width="160">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column :label="t('common.actions')" width="200" align="center" fixed="right">
          <template #default="{ row }">
            <!-- Problem 3: start visible for pending/stopped/error -->
            <el-button
              v-if="['pending', 'stopped', 'error'].includes(row.status)"
              size="small"
              type="success"
              :loading="actionId === row.id && actionType === 'start'"
              @click="onStart(row)"
            >
              {{ t("strategy.start") }}
            </el-button>
            <el-button
              v-if="row.status === 'running'"
              size="small"
              type="danger"
              :loading="actionId === row.id && actionType === 'stop'"
              @click="onStop(row)"
            >
              {{ t("strategy.stop") }}
            </el-button>
            <el-button size="small" @click="openLogs(row)">
              {{ t("strategy.logs") }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!runs.length && !runsLoading" :description="t('common.empty')" style="padding: 20px 0" />
    </div>

    <!-- ── Create Run Dialog ───────────────────────────────────────────────── -->
    <el-dialog
      v-model="createDialogVisible"
      :title="t('strategy.newRun')"
      width="500px"
      :close-on-click-modal="false"
    >
      <!-- Live-env warning -->
      <el-alert
        v-if="selectedCred?.env === 'live'"
        :title="t('strategy.liveBanner')"
        type="error"
        :closable="false"
        show-icon
        style="margin-bottom: 16px"
      />

      <el-form :model="createForm" label-width="120px">
        <!-- Problem 2: optional run name field -->
        <el-form-item :label="t('strategy.runName')">
          <el-input
            v-model="createForm.name"
            :placeholder="t('strategy.runNamePlaceholder')"
          />
        </el-form-item>

        <!-- Strategy select -->
        <el-form-item :label="t('strategy.selectStrategy')">
          <el-select
            v-model="createForm.strategy_id"
            style="width: 100%"
            :loading="strategiesLoading"
            @change="onStrategyChange"
          >
            <el-option
              v-for="s in strategies"
              :key="s.id"
              :value="s.id"
              :label="s.name"
            />
          </el-select>
        </el-form-item>

        <!-- Credential select -->
        <el-form-item :label="t('strategy.selectCredential')">
          <el-select
            v-model="createForm.credential_id"
            style="width: 100%"
            :loading="credLoading"
          >
            <el-option
              v-for="c in credentials"
              :key="c.id"
              :value="c.id"
              :label="`${c.label}`"
            >
              <span>{{ c.label }}</span>
              <el-tag
                :type="c.env === 'live' ? 'danger' : 'success'"
                size="small"
                style="margin-left: 8px"
              >
                {{ c.env === 'live' ? t('strategy.envLive') : t('strategy.envSim') }}
              </el-tag>
              <span style="color: var(--gray-400); margin-left: 6px; font-size: 12px">
                {{ c.api_key_masked }}
              </span>
            </el-option>
          </el-select>
        </el-form-item>

        <!-- Problem 4: symbol as filterable select, fallback to input -->
        <el-form-item :label="t('strategy.symbol')">
          <el-select
            v-if="!symbolFallback"
            v-model="createForm.symbol"
            filterable
            allow-create
            :loading="symbolsLoading"
            :placeholder="t('strategy.symbolPlaceholder')"
            style="width: 100%"
            default-first-option
          >
            <el-option
              v-for="sym in symbols"
              :key="sym.instId"
              :value="sym.instId"
              :label="sym.instId"
            />
          </el-select>
          <template v-else>
            <el-input v-model="createForm.symbol" placeholder="BTC-USDT" />
            <div style="font-size: 12px; color: var(--gray-400); margin-top: 4px">
              {{ t('strategy.symbolFallbackHint') }}
            </div>
          </template>
        </el-form-item>

        <!-- dual_ma params -->
        <template v-if="isDualMa">
          <el-form-item :label="t('strategy.fastPeriod')">
            <el-input-number v-model="createForm.params.fast_period" :min="1" :max="200" style="width: 100%" />
          </el-form-item>
          <el-form-item :label="t('strategy.slowPeriod')">
            <el-input-number v-model="createForm.params.slow_period" :min="1" :max="500" style="width: 100%" />
          </el-form-item>
          <el-form-item :label="t('strategy.sz')">
            <el-input v-model="createForm.params.sz" placeholder="0.01" />
          </el-form-item>
        </template>
      </el-form>

      <template #footer>
        <el-button @click="createDialogVisible = false">{{ t("common.cancel") }}</el-button>
        <el-button type="primary" :loading="creating" @click="onCreateRun">
          {{ t("common.create") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- ── Logs Dialog ────────────────────────────────────────────────────── -->
    <el-dialog
      v-model="logsDialogVisible"
      :title="logsDialogTitle"
      width="760px"
      :close-on-click-modal="false"
      @close="onLogsDialogClose"
    >
      <!-- Run status + live indicator -->
      <div class="logs-meta">
        <el-tag :type="statusTagType(activeRun?.status ?? 'pending')" size="small">
          {{ activeRun ? t(`strategy.status.${activeRun.status}`) : '' }}
        </el-tag>
        <el-tag v-if="activeRun?.credential_env === 'live'" type="danger" size="small" style="margin-left: 6px">
          {{ t('strategy.envLive') }}
        </el-tag>
        <el-tag :type="wsConnected ? 'success' : 'info'" size="small" style="margin-left: 6px">
          {{ wsConnected ? t('strategy.wsConnected') : t('strategy.wsDisconnected') }}
        </el-tag>
        <span style="flex: 1" />
        <el-button size="small" @click="clearLogs">{{ t("strategy.clearLogs") }}</el-button>
      </div>

      <!-- Log terminal -->
      <div ref="logContainer" class="log-terminal">
        <div
          v-for="(entry, idx) in logEntries"
          :key="idx"
          class="log-line"
          :class="`log-${resolveLogClass(entry.level)}`"
        >
          <span class="log-ts">{{ formatLogTs(entry.ts) }}</span>
          <span class="log-level">[{{ entry.level.toUpperCase() }}]</span>
          <span class="log-msg">{{ entry.message }}</span>
        </div>
        <div v-if="!logEntries.length" class="log-empty">{{ t("strategy.logsEmpty") }}</div>
      </div>

      <template #footer>
        <el-button @click="logsDialogVisible = false">{{ t("common.close") }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage, ElMessageBox } from "element-plus";
import { Plus } from "@element-plus/icons-vue";
import { listCredentials, type Credential } from "@/api/credentials";
import {
  listStrategies,
  listRuns,
  createRun,
  startRun,
  stopRun,
  getRunLogs,
  type Strategy,
  type StrategyRun,
  type StrategyLog,
} from "@/api/strategy";
import { getSymbols, type Symbol as MarketSymbol } from "@/api/market";
import { useStrategySocket } from "@/composables/useStrategySocket";
import { formatApiError } from "@/utils/errors";

const { t } = useI18n();

// ── Strategies (built-in list) ────────────────────────────────────────────────

const strategies = ref<Strategy[]>([]);
const strategiesLoading = ref(false);
const selectedStrategyId = ref<number | null>(null);

async function loadStrategies() {
  strategiesLoading.value = true;
  try {
    strategies.value = await listStrategies();
    if (strategies.value.length && selectedStrategyId.value === null) {
      selectedStrategyId.value = strategies.value[0].id;
    }
  } catch (e) {
    ElMessage.error(formatApiError(e, "strategy"));
  } finally {
    strategiesLoading.value = false;
  }
}

// ── Credentials ───────────────────────────────────────────────────────────────

const credentials = ref<Credential[]>([]);
const credLoading = ref(false);

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

// ── Symbols (Problem 4: dropdown) ─────────────────────────────────────────────

const symbols = ref<MarketSymbol[]>([]);
const symbolsLoading = ref(false);
const symbolFallback = ref(false);  // true = API failed, fallback to text input

async function loadSymbols() {
  symbolsLoading.value = true;
  try {
    symbols.value = await getSymbols();
    symbolFallback.value = symbols.value.length === 0;
  } catch {
    // API failed (e.g. OKX unreachable in Docker) — degrade gracefully to text input
    symbolFallback.value = true;
  } finally {
    symbolsLoading.value = false;
  }
}

// ── Runs ──────────────────────────────────────────────────────────────────────

const runs = ref<StrategyRun[]>([]);
const runsLoading = ref(false);

async function loadRuns() {
  runsLoading.value = true;
  try {
    runs.value = await listRuns();
  } catch (e) {
    ElMessage.error(formatApiError(e, "strategy"));
  } finally {
    runsLoading.value = false;
  }
}

// ── Problem 1: Short-lived polling after start/stop ───────────────────────────
//
// After a start/stop action the container takes a few seconds to spin up/down.
// We poll loadRuns() every 2 s for up to 10 s (5 ticks) so the status change
// is reflected automatically without a manual refresh.

let pollInterval: ReturnType<typeof setInterval> | null = null;
let pollTicksLeft = 0;

function startPolling() {
  stopPolling(); // clear any existing poll
  pollTicksLeft = 5; // 5 ticks × 2 s = 10 s
  pollInterval = setInterval(async () => {
    pollTicksLeft--;
    await loadRuns();
    if (pollTicksLeft <= 0) {
      stopPolling();
    }
  }, 2000);
}

function stopPolling() {
  if (pollInterval !== null) {
    clearInterval(pollInterval);
    pollInterval = null;
  }
  pollTicksLeft = 0;
}

// Cleanup on unmount to prevent leaks
onUnmounted(() => {
  stopPolling();
});

// ── Start / Stop ──────────────────────────────────────────────────────────────

const actionId = ref<number | null>(null);
const actionType = ref<"start" | "stop" | null>(null);

async function onStart(row: StrategyRun) {
  actionId.value = row.id;
  actionType.value = "start";
  try {
    await startRun(row.id);
    ElMessage.success(t("strategy.startSuccess"));
    await loadRuns();
    startPolling(); // Problem 1: auto-poll until status stabilises
  } catch (e) {
    ElMessage.error(formatApiError(e, "strategy"));
  } finally {
    actionId.value = null;
    actionType.value = null;
  }
}

async function onStop(row: StrategyRun) {
  actionId.value = row.id;
  actionType.value = "stop";
  try {
    await stopRun(row.id);
    ElMessage.success(t("strategy.stopSuccess"));
    await loadRuns();
    startPolling(); // Problem 1: auto-poll until status stabilises
  } catch (e) {
    ElMessage.error(formatApiError(e, "strategy"));
  } finally {
    actionId.value = null;
    actionType.value = null;
  }
}

// ── Create run dialog ─────────────────────────────────────────────────────────

const createDialogVisible = ref(false);
const creating = ref(false);

const createForm = reactive<{
  name: string;
  strategy_id: number | null;
  credential_id: number | null;
  symbol: string;
  params: Record<string, unknown>;
}>({
  name: "",
  strategy_id: null,
  credential_id: null,
  symbol: "BTC-USDT",
  params: { fast_period: 5, slow_period: 20, sz: "0.01" },
});

const selectedCred = computed<Credential | undefined>(() =>
  credentials.value.find((c) => c.id === createForm.credential_id),
);

const isDualMa = computed<boolean>(() => {
  const s = strategies.value.find((s) => s.id === createForm.strategy_id);
  return s?.code_ref === "dual_ma" || s?.name?.toLowerCase().includes("双均线") || false;
});

function onStrategyChange() {
  const s = strategies.value.find((x) => x.id === createForm.strategy_id);
  if (s?.default_params) {
    // Merge defaults into form params
    Object.assign(createForm.params, s.default_params);
  }
}

function openCreateDialog() {
  // Pre-select first strategy and first credential
  if (strategies.value.length) createForm.strategy_id = strategies.value[0].id;
  if (credentials.value.length) createForm.credential_id = credentials.value[0].id;
  createForm.name = "";
  onStrategyChange();
  createDialogVisible.value = true;
}

async function onCreateRun() {
  if (!createForm.strategy_id) {
    ElMessage.warning(t("strategy.selectStrategyHint"));
    return;
  }
  if (!createForm.credential_id) {
    ElMessage.warning(t("strategy.selectCredentialHint"));
    return;
  }
  if (!createForm.symbol.trim()) {
    ElMessage.warning(t("strategy.symbolRequired"));
    return;
  }

  // Live env confirmation
  if (selectedCred.value?.env === "live") {
    try {
      await ElMessageBox.confirm(
        t("strategy.liveConfirmMsg"),
        t("strategy.liveConfirmTitle"),
        {
          type: "error",
          confirmButtonText: t("common.confirm"),
          cancelButtonText: t("common.cancel"),
          confirmButtonClass: "el-button--danger",
        },
      );
    } catch {
      return;
    }
  }

  creating.value = true;
  try {
    await createRun({
      strategy_id: createForm.strategy_id!,
      credential_id: createForm.credential_id!,
      symbol: createForm.symbol.trim(),
      params: { ...createForm.params },
      name: createForm.name.trim() || undefined,
    });
    ElMessage.success(t("strategy.createSuccess"));
    createDialogVisible.value = false;
    await loadRuns();
  } catch (e) {
    ElMessage.error(formatApiError(e, "strategy"));
  } finally {
    creating.value = false;
  }
}

// ── Logs dialog ───────────────────────────────────────────────────────────────

const logsDialogVisible = ref(false);
const activeRun = ref<StrategyRun | null>(null);
const logEntries = ref<StrategyLog[]>([]);
const wsConnected = ref(false);
const logContainer = ref<HTMLElement | null>(null);

const logsDialogTitle = computed(() =>
  activeRun.value
    ? `${t("strategy.logs")} — ${activeRun.value.name || activeRun.value.strategy_name} / ${activeRun.value.symbol}`
    : t("strategy.logs"),
);

let wsDisconnect: (() => void) | null = null;

function appendLog(entry: StrategyLog) {
  logEntries.value.push(entry);
  // Auto-scroll to bottom
  nextTick(() => {
    if (logContainer.value) {
      logContainer.value.scrollTop = logContainer.value.scrollHeight;
    }
  });
}

function clearLogs() {
  logEntries.value = [];
}

function stopWs() {
  if (wsDisconnect) {
    wsDisconnect();
    wsDisconnect = null;
  }
  wsConnected.value = false;
}

async function openLogs(row: StrategyRun) {
  stopWs();
  logEntries.value = [];
  activeRun.value = row;
  logsDialogVisible.value = true;

  // Load historical logs first
  try {
    const hist = await getRunLogs(row.id);
    logEntries.value = hist;
  } catch (e) {
    ElMessage.error(formatApiError(e, "strategy"));
  }

  // Then open WS for incremental updates
  const { connected, disconnect } = useStrategySocket(row.id, (entry) => {
    appendLog(entry);
    // Refresh run status periodically when WS active
    loadRuns();
  });
  watch(connected, (v) => { wsConnected.value = v; }, { immediate: true });
  wsDisconnect = disconnect;

  // Scroll to bottom after initial load
  await nextTick();
  if (logContainer.value) {
    logContainer.value.scrollTop = logContainer.value.scrollHeight;
  }
}

function onLogsDialogClose() {
  stopWs();
  activeRun.value = null;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function statusTagType(status: string): "" | "success" | "danger" | "warning" | "info" {
  switch (status) {
    case "running": return "success";
    case "error": return "danger";
    case "stopped": return "info";
    default: return "warning"; // pending
  }
}

function resolveLogClass(level: string): string {
  const l = level.toLowerCase();
  if (l === "buy") return "buy";
  if (l === "sell") return "sell";
  if (l === "error") return "error";
  if (l === "warn" || l === "warning") return "warn";
  return "info";
}

function formatDate(iso: string): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

function formatLogTs(ts: string): string {
  if (!ts) return "";
  try {
    return new Date(ts).toLocaleTimeString();
  } catch {
    return ts;
  }
}

// ── Lifecycle ─────────────────────────────────────────────────────────────────

onMounted(async () => {
  await Promise.all([loadStrategies(), loadCredentials(), loadRuns(), loadSymbols()]);
});
</script>

<style scoped>
.strategy-page {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
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

/* Strategy cards */
.strategy-cards {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
}

.strategy-card {
  cursor: pointer;
  min-width: 220px;
  padding: var(--space-4);
  border: 2px solid var(--gray-200);
  border-radius: var(--radius-lg);
  background: #fff;
  transition: border-color var(--duration-fast) var(--ease),
              box-shadow var(--duration-fast) var(--ease);
}

.strategy-card:hover {
  border-color: var(--brand-primary);
}

.strategy-card.selected {
  border-color: var(--brand-primary);
  box-shadow: 0 0 0 3px rgba(99, 91, 255, 0.1);
}

.sc-name {
  font-weight: 600;
  font-size: var(--font-size-md);
  color: var(--gray-800);
  margin-bottom: 4px;
}

.sc-code {
  font-size: var(--font-size-xs);
  color: var(--gray-500);
  font-family: monospace;
  margin-bottom: var(--space-2);
}

.sc-params {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.sc-param {
  font-size: var(--font-size-xs);
  color: var(--gray-600);
  background: var(--gray-100);
  padding: 2px 6px;
  border-radius: 4px;
}

/* Cards */
.card {
  background: #fff;
  border: 1px solid var(--gray-200);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
}

.runs-card {
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

/* Logs dialog */
.logs-meta {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
}

.log-terminal {
  background: #1a1a1a;
  border-radius: var(--radius-md);
  padding: var(--space-3);
  height: 380px;
  overflow-y: auto;
  font-family: "JetBrains Mono", "Fira Code", "Cascadia Code", ui-monospace, monospace;
  font-size: 12px;
  line-height: 1.6;
  scrollbar-width: thin;
  scrollbar-color: #444 #1a1a1a;
}

.log-terminal::-webkit-scrollbar { width: 6px; }
.log-terminal::-webkit-scrollbar-track { background: #1a1a1a; }
.log-terminal::-webkit-scrollbar-thumb { background: #444; border-radius: 3px; }

.log-line {
  display: flex;
  gap: 8px;
  padding: 1px 0;
}

.log-ts {
  color: #555;
  flex: none;
  width: 90px;
}

.log-level {
  flex: none;
  width: 60px;
  font-weight: 600;
}

.log-msg {
  flex: 1;
  word-break: break-all;
}

/* Level colors */
.log-buy .log-level,
.log-buy .log-msg { color: #26a17b; }

.log-sell .log-level,
.log-sell .log-msg { color: #e84646; }

.log-error .log-level,
.log-error .log-msg { color: #e84646; }

.log-warn .log-level,
.log-warn .log-msg { color: #e6a817; }

.log-info .log-level { color: #888; }
.log-info .log-msg { color: #ccc; }

.log-empty {
  color: #555;
  text-align: center;
  margin-top: 40px;
}
</style>
