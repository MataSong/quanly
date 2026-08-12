<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch, nextTick } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { EditorView, basicSetup } from "codemirror";
import { python } from "@codemirror/lang-python";
import { strategyApi } from "@/api/strategy";

const route = useRoute();
const router = useRouter();
const { t } = useI18n();

const id = route.params.id ? Number(route.params.id) : null;
const name = ref("");
const mode = ref<"visual" | "code">("visual");

// 可视化
const schemas = ref<Record<string, any[]>>({});
const kind = ref("ma_cross");
const config = ref<Record<string, any>>({});
const preview = ref("");

// 代码
const editorEl = ref<HTMLElement | null>(null);
let view: EditorView | null = null;
const validateMsg = ref("");
const dryrunLogs = ref<any[]>([]);

function kindNames() {
  return Object.keys(schemas.value);
}

function resetConfigForKind() {
  const fields = schemas.value[kind.value] || [];
  const c: Record<string, any> = {};
  for (const f of fields) c[f.name] = f.default;
  config.value = c;
}

async function refreshPreview() {
  if (!schemas.value[kind.value]) return;
  try {
    const r = await strategyApi.visualPreview(kind.value, config.value);
    preview.value = r.data.source;
  } catch (e: any) {
    preview.value = "# " + (e?.response?.data?.detail || "preview error");
  }
}

function codeSource() {
  return view ? view.state.doc.toString() : "";
}

async function toCode() {
  await refreshPreview();
  mode.value = "code";
  await nextTick();
  mountEditor(preview.value);
}

function mountEditor(initial: string) {
  if (view || !editorEl.value) return;
  view = new EditorView({
    doc: initial,
    extensions: [basicSetup, python()],
    parent: editorEl.value,
  });
}

async function validate() {
  try {
    await strategyApi.codeValidate(codeSource());
    validateMsg.value = t("strategy.editor.validOk");
  } catch (e: any) {
    validateMsg.value = e?.response?.data?.error || "syntax error";
  }
}

async function dryrun() {
  const r = await strategyApi.codeDryrun(codeSource());
  dryrunLogs.value = r.data.logs || [];
  if (r.data.error) dryrunLogs.value = [{ message: r.data.error, level: "warn" }];
}

async function save() {
  const payload: any = { name: name.value };
  if (mode.value === "visual") {
    payload.mode = "visual";
    payload.visual_config = { kind: kind.value, config: config.value };
    payload.source = preview.value;
  } else {
    payload.mode = "code";
    payload.source = codeSource();
  }
  if (id) await strategyApi.updateFull(id, payload);
  else await strategyApi.createFull(payload);
  router.push("/strategies/templates");
}

watch([kind], () => {
  resetConfigForKind();
  refreshPreview();
});
watch(config, refreshPreview, { deep: true });

onMounted(async () => {
  const r = await strategyApi.visualSchemas();
  schemas.value = r.data;
  if (id) {
    const s = (await strategyApi.get(id)).data;
    name.value = s.name;
    if (s.mode === "visual" && s.visual_config) {
      mode.value = "visual";
      kind.value = s.visual_config.kind || "ma_cross";
      config.value = s.visual_config.config || {};
      await refreshPreview();
    } else {
      mode.value = "code";
      await nextTick();
      mountEditor(s.source || "");
    }
  } else {
    resetConfigForKind();
    await refreshPreview();
  }
});
onUnmounted(() => view?.destroy());
</script>

<template>
  <div class="wrap">
    <div class="glass panel">
      <div class="head">
        <h2>{{ $t("strategy.editor.title") }}</h2>
        <div class="tabs">
          <button :class="{ on: mode === 'visual' }" @click="mode = 'visual'">
            {{ $t("strategy.editor.visualTab") }}
          </button>
          <button
            :class="{ on: mode === 'code' }"
            @click="mode = 'code'; nextTick(() => mountEditor(preview))"
          >
            {{ $t("strategy.editor.codeTab") }}
          </button>
        </div>
      </div>
      <input class="input" v-model="name" :placeholder="$t('strategy.name')" />

      <!-- 可视化模式 -->
      <div v-if="mode === 'visual'" class="visual">
        <label class="fld">
          {{ $t("strategy.editor.type") }}
          <select class="input" v-model="kind">
            <option v-for="k in kindNames()" :key="k" :value="k">
              {{ $t("strategy.visual.kinds." + k) }}
            </option>
          </select>
        </label>
        <div class="form">
          <label v-for="f in schemas[kind] || []" :key="f.name" class="fld">
            {{ $t(f.label_key) }}
            <input
              class="input"
              type="number"
              :step="f.type === 'float' ? 'any' : '1'"
              v-model.number="config[f.name]"
            />
          </label>
        </div>
        <div class="preview">
          <div class="plabel">{{ $t("strategy.editor.preview") }}</div>
          <pre>{{ preview }}</pre>
        </div>
        <button class="btn btn-ghost" @click="toCode">{{ $t("strategy.editor.toCode") }}</button>
      </div>

      <!-- 代码模式 -->
      <div v-else class="code-mode">
        <div ref="editorEl" class="editor"></div>
        <div class="row">
          <button class="btn btn-ghost" @click="validate">{{ $t("strategy.editor.validate") }}</button>
          <button class="btn btn-ghost" @click="dryrun">{{ $t("strategy.editor.dryrun") }}</button>
          <span class="msg">{{ validateMsg }}</span>
        </div>
        <div v-if="dryrunLogs.length" class="logs">
          <div v-for="(l, i) in dryrunLogs" :key="i" class="logline">{{ l.message }}</div>
        </div>
      </div>

      <div class="row">
        <button class="btn" @click="save">{{ $t("strategy.save") }}</button>
        <button class="btn btn-ghost" @click="router.push('/strategies/templates')">
          {{ $t("common.cancel") }}
        </button>
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
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
h2 {
  margin: 0;
}
.tabs button {
  background: transparent;
  border: 1px solid var(--glass-border);
  color: var(--fg-dim);
  padding: 6px 14px;
  cursor: pointer;
  border-radius: 8px;
  margin-left: 6px;
}
.tabs button.on {
  color: var(--fg);
  border-color: var(--accent, #4a9eff);
}
.form {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 12px;
}
.fld {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: var(--fg-dim);
}
.preview {
  margin-top: 14px;
}
.plabel {
  font-size: 12px;
  color: var(--fg-dim);
  margin-bottom: 4px;
}
.preview pre {
  background: #0d0d12;
  color: #d6d6dd;
  padding: 12px;
  border-radius: 8px;
  overflow: auto;
  max-height: 320px;
  font-family: ui-monospace, "SF Mono", monospace;
  font-size: 13px;
}
.editor {
  margin-top: 12px;
  border: 1px solid var(--glass-border);
  border-radius: 8px;
  overflow: hidden;
  max-height: 420px;
}
.row {
  display: flex;
  gap: 8px;
  margin-top: 12px;
  align-items: center;
}
.msg {
  font-size: 13px;
  color: var(--fg-dim);
}
.logs {
  margin-top: 12px;
  background: #0d0d12;
  color: #9fe6b0;
  padding: 10px;
  border-radius: 8px;
  max-height: 220px;
  overflow: auto;
  font-family: ui-monospace, "SF Mono", monospace;
  font-size: 12px;
}
.input {
  margin-top: 8px;
}
</style>
