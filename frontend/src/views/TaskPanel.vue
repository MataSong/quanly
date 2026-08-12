<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { strategyApi } from "@/api/strategy";

const route = useRoute();
const router = useRouter();

const templates = ref<any[]>([]);
const creds = ref<any[]>([]);
const groups = ref<any[]>([]);

const form = ref({
  template_id: null as number | null,
  env: "sim",
  credential_id: null as number | null,
  interval_sec: 5,
  symbolsText: "BTC-USDT",
});

let timer: any = null;

async function loadTemplates() {
  const r = await strategyApi.list();
  templates.value = r.data;
  // 从模板库「批量启动」跳转带来的预选
  const t = route.query.template;
  if (t && !form.value.template_id) form.value.template_id = Number(t);
}

async function loadCreds() {
  try {
    const r = await strategyApi.credentials(form.value.env);
    creds.value = r.data;
    form.value.credential_id = creds.value.length === 1 ? creds.value[0].id : form.value.credential_id;
  } catch {
    creds.value = [];
  }
}

async function loadTasks() {
  const r = await strategyApi.tasksOverview();
  groups.value = r.data;
}

async function onEnvChange() {
  form.value.credential_id = null;
  await loadCreds();
}

async function batchRun() {
  const symbols = form.value.symbolsText
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  if (!form.value.template_id || symbols.length === 0) return;
  await strategyApi.batchRun({
    template_id: form.value.template_id,
    symbols,
    env: form.value.env,
    credential_id: form.value.credential_id ?? undefined,
    interval_sec: form.value.interval_sec,
  });
  await loadTasks();
}

async function stopRun(runId: number) {
  await strategyApi.stop(runId);
  await loadTasks();
}

async function stopBatch(batchId: string) {
  if (!batchId) return;
  await strategyApi.batchStop(batchId);
  await loadTasks();
}

function openLogs(runId: number) {
  router.push(`/strategies/${runId}`);
}

function statusClass(s: string) {
  return {
    running: s === "running",
    stopped: s === "stopped",
    error: s === "error",
    pending: s === "pending",
  };
}

onMounted(async () => {
  await loadTemplates();
  await loadCreds();
  await loadTasks();
  timer = setInterval(loadTasks, 3000);
});
onUnmounted(() => timer && clearInterval(timer));
</script>

<template>
  <div class="wrap">
    <div class="glass panel">
      <h2>{{ $t("strategy.tasks.title") }}</h2>
      <div class="form">
        <label>
          {{ $t("strategy.tasks.selectTemplate") }}
          <select class="input" v-model="form.template_id">
            <option :value="null" disabled>—</option>
            <option v-for="t in templates" :key="t.id" :value="t.id">{{ t.name }}</option>
          </select>
        </label>
        <label>
          env
          <select class="input" v-model="form.env" @change="onEnvChange">
            <option value="sim">sim</option>
            <option value="live">live</option>
          </select>
        </label>
        <label>
          {{ $t("keys.title") }}
          <select class="input" v-model="form.credential_id">
            <option :value="null">—</option>
            <option v-for="c in creds" :key="c.id" :value="c.id">{{ c.label }}</option>
          </select>
        </label>
        <label>
          {{ $t("strategy.interval") }}
          <input class="input" type="number" min="1" max="3600" v-model.number="form.interval_sec" />
        </label>
        <label class="grow">
          {{ $t("strategy.tasks.symbols") }}
          <input class="input" v-model="form.symbolsText" placeholder="BTC-USDT, ETH-USDT" />
        </label>
        <button class="btn" @click="batchRun">{{ $t("strategy.tasks.batchRun") }}</button>
      </div>
    </div>

    <div class="glass panel">
      <h3>{{ $t("strategy.tasks.running") }}</h3>
      <div v-if="groups.length === 0" class="empty">{{ $t("strategy.tasks.empty") }}</div>
      <div v-for="g in groups" :key="g.batch_id || g.runs[0].id" class="group">
        <div class="ghead">
          <span class="gname">{{ g.template_name }} · {{ g.env }}</span>
          <button v-if="g.batch_id" class="btn btn-ghost sm" @click="stopBatch(g.batch_id)">
            {{ $t("strategy.tasks.stopAll") }}
          </button>
        </div>
        <table class="tbl">
          <thead>
            <tr>
              <th>{{ $t("trade.symbol") }}</th>
              <th>{{ $t("strategy.status") }}</th>
              <th>{{ $t("strategy.tasks.heartbeat") }}</th>
              <th>{{ $t("strategy.tasks.pnl") }}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="run in g.runs" :key="run.id">
              <td>{{ run.symbol }}</td>
              <td><span class="badge" :class="statusClass(run.status)">{{ run.status }}</span></td>
              <td class="dim">{{ run.last_heartbeat ? new Date(run.last_heartbeat).toLocaleTimeString() : "—" }}</td>
              <td :class="{ pos: run.pnl > 0, neg: run.pnl < 0 }">{{ run.pnl }}</td>
              <td class="actions">
                <button class="btn btn-ghost sm" @click="openLogs(run.id)">{{ $t("strategy.logs") }}</button>
                <button class="btn btn-ghost sm" @click="stopRun(run.id)">{{ $t("strategy.stop") }}</button>
              </td>
            </tr>
          </tbody>
        </table>
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
  margin: 0 0 12px;
}
.form {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: flex-end;
}
.form label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: var(--fg-dim);
}
.form .grow {
  flex: 1;
  min-width: 200px;
}
.group {
  margin-top: 16px;
}
.ghead {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
.gname {
  font-weight: 600;
}
.tbl {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}
.tbl th,
.tbl td {
  text-align: left;
  padding: 8px 6px;
  border-bottom: 1px solid var(--glass-border);
}
.tbl th {
  color: var(--fg-dim);
  font-weight: 600;
}
.dim {
  color: var(--fg-dim);
}
.pos {
  color: var(--up, #26a69a);
}
.neg {
  color: var(--down, #ef5350);
}
.badge {
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 12px;
  background: var(--glass-border);
}
.badge.running {
  color: #26a69a;
}
.badge.error {
  color: #ef5350;
}
.actions {
  display: flex;
  gap: 6px;
}
.sm {
  padding: 4px 10px;
  font-size: 12px;
}
.empty {
  text-align: center;
  color: var(--fg-dim);
  padding: 16px;
}
.input {
  min-width: 120px;
}
</style>
