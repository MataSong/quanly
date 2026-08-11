<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { useI18n } from "vue-i18n";
import { strategyApi } from "@/api/strategy";
import GlassSelect from "@/components/GlassSelect.vue";
import SearchSelect from "@/components/SearchSelect.vue";
import GlassNumber from "@/components/GlassNumber.vue";
import GlassCheckbox from "@/components/GlassCheckbox.vue";

const { t } = useI18n();
const route = useRoute();
const id = Number(route.params.id);

interface LogLine {
  level: string;
  message: string;
  ts: string;
}

const strategy = ref<any>(null);
const runs = ref<any[]>([]);
const credentials = ref<any[]>([]);
const logs = ref<LogLine[]>([]);
const activeRun = ref<any | null>(null);
const autoScroll = ref(true);
const logboxEl = ref<HTMLDivElement | null>(null);
let logWs: WebSocket | null = null;

const cfg = ref({
  env: "sim" as "sim" | "live",
  credential_id: null as number | null,
  symbol: "BTC-USDT",
  interval_sec: 5,
});

const symbols = ref<string[]>(["BTC-USDT", "ETH-USDT", "SOL-USDT"]);
const envOptions = computed(() => [
  { label: t("trade.sim"), value: "sim" },
  { label: t("trade.live"), value: "live" },
]);
const credOptions = computed(() =>
  credentials.value.map((c) => ({ label: `${c.label} (${c.api_key_masked})`, value: c.id }))
);
const symbolOptions = computed(() => symbols.value.map((s) => ({ label: s, value: s })));

function pushLog(line: LogLine) {
  logs.value.push(line);
  if (logs.value.length > 500) logs.value.shift();
  if (autoScroll.value) {
    nextTick(() => {
      if (logboxEl.value) logboxEl.value.scrollTop = logboxEl.value.scrollHeight;
    });
  }
}

async function loadAll() {
  const [s, r] = await Promise.all([strategyApi.get(id), strategyApi.runs(id)]);
  strategy.value = s.data;
  runs.value = r.data;
  activeRun.value = runs.value.find((x) => x.status === "running") || null;
  if (activeRun.value) openLogWs(activeRun.value.id);
}

async function loadCreds() {
  const r = await strategyApi.credentials(cfg.value.env);
  credentials.value = r.data;
  cfg.value.credential_id = credentials.value[0]?.id ?? null;
}

async function start() {
  logs.value = [];
  const r = await strategyApi.run(id, cfg.value);
  activeRun.value = r.data;
  await loadAll();
  openLogWs(r.data.id);
}

async function stop(runId: number) {
  await strategyApi.stop(runId);
  logWs?.close();
  await loadAll();
}

function nowTs() {
  return new Date().toLocaleTimeString();
}

function openLogWs(runId: number) {
  logWs?.close();
  const proto = location.protocol === "https:" ? "wss" : "ws";
  logWs = new WebSocket(`${proto}://${location.host}/ws/strategy/${runId}`);
  logWs.onmessage = (ev) => {
    try {
      const m = JSON.parse(ev.data);
      pushLog({ level: m.level || "info", message: m.message, ts: m.ts || nowTs() });
    } catch {
      pushLog({ level: "info", message: ev.data, ts: nowTs() });
    }
  };
}

watch(() => cfg.value.env, loadCreds);

onMounted(async () => {
  try {
    const r = await fetch("/api/market/symbols");
    const d = await r.json();
    if (Array.isArray(d.symbols) && d.symbols.length) symbols.value = d.symbols;
  } catch {
    /* 保留默认 */
  }
  await loadAll();
  await loadCreds();
  if (activeRun.value) {
    const r = await strategyApi.logs(activeRun.value.id);
    logs.value = r.data.map((l: any) => ({
      level: l.level || "info",
      message: l.message,
      ts: l.ts ? new Date(l.ts).toLocaleTimeString() : "",
    }));
    nextTick(() => {
      if (logboxEl.value) logboxEl.value.scrollTop = logboxEl.value.scrollHeight;
    });
  }
});
onBeforeUnmount(() => logWs?.close());
</script>

<template>
  <div class="wrap" v-if="strategy">
    <div class="glass panel">
      <h2>{{ strategy.name }}</h2>
      <div class="cfg">
        <div class="fld">
          <label>{{ $t("trade.env") }}</label>
          <GlassSelect v-model="cfg.env" :options="envOptions" />
        </div>
        <div class="fld">
          <label>{{ $t("trade.credential") }}</label>
          <GlassSelect v-model="cfg.credential_id" :options="credOptions" />
        </div>
        <div class="fld">
          <label>{{ $t("trade.symbol") }}</label>
          <SearchSelect v-model="cfg.symbol" :options="symbolOptions" />
        </div>
        <div class="fld">
          <label>{{ $t("strategy.interval") }}(s)</label>
          <GlassNumber v-model="cfg.interval_sec" :min="1" />
        </div>
        <div class="fld btns">
          <button v-if="!activeRun" class="btn" @click="start">{{ $t("strategy.start") }}</button>
          <button v-else class="btn btn-ghost" @click="stop(activeRun.id)">
            {{ $t("strategy.stop") }}
          </button>
        </div>
      </div>
      <div class="status">
        {{ $t("strategy.status") }}:
        <span :class="activeRun ? 'running' : 'stopped'">
          {{ activeRun ? $t("strategy.running") : $t("strategy.notRunning") }}
        </span>
      </div>
    </div>

    <div class="glass panel">
      <div class="log-head">
        <h3>{{ $t("strategy.logs") }}</h3>
        <GlassCheckbox v-model="autoScroll" :label="$t('strategy.autoScroll')" />
      </div>
      <div ref="logboxEl" class="logbox terminal">
        <div v-for="(l, i) in logs" :key="i" class="logline" :class="'lv-' + l.level">
          <span class="ts">{{ l.ts }}</span>
          <span class="lvl">{{ l.level.toUpperCase() }}</span>
          <span class="msg">{{ l.message }}</span>
        </div>
        <div v-if="logs.length === 0" class="empty">{{ $t("strategy.noLogs") }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.wrap {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.panel {
  padding: 22px;
}
h2,
h3 {
  margin: 0 0 14px;
}
.cfg {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: flex-end;
}
.fld {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.fld label {
  font-size: 12px;
  color: var(--fg-dim);
}
.btns {
  justify-content: flex-end;
}
.status {
  margin-top: 14px;
  font-size: 14px;
  color: var(--fg-dim);
}
.running {
  color: #30d158;
  font-weight: 600;
}
.stopped {
  color: var(--fg-dim);
}
.log-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.log-head h3 {
  margin: 0;
}
.autoscroll {
  font-size: 12px;
  color: var(--fg-dim);
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
}
.logbox.terminal {
  background: #0d0d12;
  border: 1px solid var(--glass-border);
  border-radius: 10px;
  padding: 12px 14px;
  height: 360px;
  overflow-y: auto;
  font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
  font-size: 12.5px;
  line-height: 1.7;
}
.logline {
  display: flex;
  gap: 10px;
  padding: 1px 0;
  white-space: pre-wrap;
  word-break: break-all;
  color: #c8c8d0;
}
.logline .ts {
  color: #6a6a78;
  flex-shrink: 0;
}
.logline .lvl {
  flex-shrink: 0;
  width: 42px;
  font-weight: 700;
}
.logline.lv-buy .lvl {
  color: #30d158;
}
.logline.lv-sell .lvl {
  color: #ff453a;
}
.logline.lv-warn .lvl {
  color: #ff9f0a;
}
.logline.lv-info .lvl {
  color: #64d2ff;
}
.logline.lv-buy .msg {
  color: #7ee2a0;
}
.logline.lv-sell .msg {
  color: #ff8a80;
}
.logline.lv-warn .msg {
  color: #ffca6a;
}
.empty {
  color: #6a6a78;
  text-align: center;
  padding: 20px;
}
</style>
