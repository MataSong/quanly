<template>
  <div class="my-strategies-page">
    <!-- Header -->
    <div class="page-header">
      <h2 class="page-title">{{ t("strategy.myStrategies") }}</h2>
      <el-button type="primary" @click="openCreate">
        {{ t("strategy.createStrategy") }}
      </el-button>
    </div>

    <!-- Table -->
    <div class="card" v-loading="loading">
      <div class="card-title-row">
        <span class="card-title">{{ t("strategy.myStrategies") }}</span>
        <el-button size="small" :loading="loading" @click="load">
          {{ t("common.refresh") }}
        </el-button>
      </div>
      <ResponsiveTable
        :columns="cols"
        :data="rows"
        row-key="id"
        :empty-text="t('common.empty')"
      >
        <!-- Visibility -->
        <template #cell-visibility="{ row }">
          <el-tag
            :type="row.visibility === 'public' ? 'primary' : 'info'"
            size="small"
          >
            {{ t(`strategy.visibilityOpt.${row.visibility ?? 'private'}`) }}
          </el-tag>
        </template>

        <!-- Audit status -->
        <template #cell-status="{ row }">
          <el-tag v-if="row.status" :type="auditTagType(row.status)" size="small">
            {{ t(`strategy.auditStatus.${row.status}`) }}
          </el-tag>
          <span v-else>—</span>
        </template>

        <!-- Check status (code strategies only) -->
        <template #cell-check_status="{ row }">
          <el-tag
            v-if="row.source_type === 'code' && row.check_status"
            :type="checkTagType(row.check_status)"
            size="small"
          >
            {{ t(`strategy.check${capitalize(row.check_status)}`) }}
          </el-tag>
          <span v-else>—</span>
        </template>

        <!-- Actions -->
        <template #cell-actions="{ row }">
          <div class="action-btns">
            <!-- Edit -->
            <el-button size="small" @click.stop="openEdit(row as Strategy)">
              {{ t("common.edit") }}
            </el-button>

            <!-- Re-check (code strategies) -->
            <el-button
              v-if="row.source_type === 'code'"
              size="small"
              :loading="checkingId === row.id"
              @click.stop="onCheck(row as Strategy)"
            >
              {{ t("strategy.check") }}
            </el-button>

            <!-- Submit for audit (draft / rejected only) -->
            <el-tooltip
              v-if="(row.status === 'draft' || row.status === 'rejected') && !canSubmit(row as Strategy)"
              :content="t('strategy.checkNotPassedHint')"
              placement="top"
            >
              <span>
                <el-button size="small" type="warning" disabled>
                  {{ t("strategy.submitAudit") }}
                </el-button>
              </span>
            </el-tooltip>
            <el-button
              v-else-if="row.status === 'draft' || row.status === 'rejected'"
              size="small"
              type="warning"
              @click.stop="onSubmit(row as Strategy)"
            >
              {{ t("strategy.submitAudit") }}
            </el-button>

            <!-- View reject reason -->
            <el-tooltip
              v-if="row.status === 'rejected' && row.reject_reason"
              :content="row.reject_reason"
              placement="top"
            >
              <el-button size="small" type="danger" plain>
                {{ t("strategy.rejectReason") }}
              </el-button>
            </el-tooltip>

            <!-- Delete -->
            <el-button size="small" type="danger" @click.stop="onDelete(row as Strategy)">
              {{ t("common.delete") }}
            </el-button>
          </div>
        </template>
      </ResponsiveTable>
    </div>

    <!-- Create / Edit dialog -->
    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? t('strategy.editStrategy') : t('strategy.createStrategy')"
      :width="dialogWidth"
      :close-on-click-modal="false"
    >
      <el-alert
        v-if="editingId"
        :title="t('strategy.editResetWarning')"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 16px"
      />
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        :label-width="isMobile ? undefined : '120px'"
        :label-position="isMobile ? 'top' : 'right'"
      >
        <!-- Source type (only when creating) -->
        <el-form-item v-if="!editingId" :label="t('strategy.sourceType')">
          <el-radio-group v-model="form.source_type">
            <el-radio-button value="uploaded">{{ t("strategy.sourceUploaded") }}</el-radio-button>
            <el-radio-button value="code">{{ t("strategy.sourceCode") }}</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <!-- ── Click-through template (uploaded) ── -->
        <!-- Template (only when creating uploaded) -->
        <el-form-item
          v-if="!editingId && form.source_type === 'uploaded'"
          :label="t('strategy.template')"
          prop="template_ref"
        >
          <el-select
            v-model="form.template_ref"
            style="width: 100%"
            :loading="templatesLoading"
            :placeholder="t('strategy.selectTemplate')"
            @change="onTemplateChange"
          >
            <el-option
              v-for="s in templates"
              :key="s.id"
              :value="s.code_ref"
              :label="s.name"
            />
          </el-select>
        </el-form-item>
        <el-form-item
          v-else-if="editingId && form.source_type !== 'code'"
          :label="t('strategy.template')"
        >
          <span class="form-readonly">{{ form.template_ref }}</span>
        </el-form-item>

        <!-- Name -->
        <el-form-item :label="t('strategy.strategyName')" prop="name">
          <el-input v-model="form.name" :placeholder="t('strategy.strategyName')" />
        </el-form-item>

        <!-- Description -->
        <el-form-item :label="t('strategy.strategyDesc')">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="3"
            :placeholder="t('strategy.strategyDesc')"
          />
        </el-form-item>

        <!-- Dynamic params based on selected template's default_params (uploaded only) -->
        <template v-if="form.source_type !== 'code' && selectedTemplate">
          <el-form-item
            v-for="(defVal, key) in selectedTemplate.default_params"
            :key="String(key)"
            :label="paramLabel(String(key))"
          >
            <el-input-number
              v-if="typeof defVal === 'number'"
              v-model="(form.params as Record<string,unknown>)[String(key)] as number"
              :min="0"
              style="width: 100%"
            />
            <el-input
              v-else
              v-model="(form.params as Record<string,unknown>)[String(key)] as string"
            />
          </el-form-item>
        </template>

        <!-- ── Python script (code) ── -->
        <template v-if="form.source_type === 'code'">
          <el-form-item :label="t('strategy.codeLabel')" prop="code">
            <div class="code-field">
              <div class="code-field-toolbar">
                <span class="code-contract">{{ t("strategy.codeContract") }}</span>
                <el-button size="small" text type="primary" @click="fillExample">
                  {{ t("strategy.codeExample") }}
                </el-button>
              </div>
              <el-input
                v-model="form.code"
                type="textarea"
                :rows="15"
                :placeholder="t('strategy.codePlaceholder')"
                class="code-textarea"
                resize="vertical"
                spellcheck="false"
              />
            </div>
          </el-form-item>
        </template>

        <!-- Visibility -->
        <el-form-item :label="t('strategy.visibility')">
          <el-radio-group v-model="form.visibility">
            <el-radio value="private">{{ t("strategy.visibilityOpt.private") }}</el-radio>
            <el-radio value="public">{{ t("strategy.visibilityOpt.public") }}</el-radio>
          </el-radio-group>
        </el-form-item>

        <!-- Check result (code strategies, after create/check) -->
        <el-form-item
          v-if="form.source_type === 'code' && checkStatus"
          :label="t('strategy.checkResultTitle')"
        >
          <div class="check-panel">
            <el-tag :type="checkTagType(checkStatus)" size="small" style="margin-bottom: 8px">
              {{ t(`strategy.check${capitalize(checkStatus)}`) }}
            </el-tag>
            <div v-if="checkStageLabel" class="check-line">
              <b>{{ t("strategy.checkStage") }}:</b> {{ checkStageLabel }}
            </div>
            <!-- syntax error -->
            <div v-if="syntaxError" class="check-line check-err">
              <b>{{ t("strategy.checkSyntaxError") }}:</b>
              <template v-if="syntaxError.line != null"> {{ t("strategy.checkLine") }} {{ syntaxError.line }} — </template>
              {{ syntaxError.msg }}
            </div>
            <!-- ast violations -->
            <div v-if="astViolations.length" class="check-err">
              <b>{{ t("strategy.checkAstViolations") }}:</b>
              <ul class="check-list">
                <li v-for="(v, i) in astViolations" :key="i">
                  <template v-if="v.line != null">{{ t("strategy.checkLine") }} {{ v.line }} — </template>{{ v.rule }}
                </li>
              </ul>
            </div>
            <!-- trial -->
            <template v-if="trial">
              <div v-if="trial.error" class="check-line check-err">
                <b>{{ t("strategy.checkTrialError") }}:</b> {{ trial.error }}
              </div>
              <div v-else-if="trial.ok" class="check-line check-ok">
                {{ t("strategy.checkTrialOk") }}
                <span v-if="trial.signal_count != null">
                  — {{ t("strategy.checkSignalCount") }}: {{ trial.signal_count }}
                </span>
              </div>
            </template>
          </div>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">{{ t("common.cancel") }}</el-button>
        <el-button
          v-if="form.source_type === 'code' && editingId"
          :loading="checkingId === editingId"
          @click="onCheckCurrent"
        >
          {{ t("strategy.check") }}
        </el-button>
        <el-button type="primary" :loading="saving" @click="onSave">
          {{ editingId ? t("common.save") : t("common.create") }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage, ElMessageBox } from "element-plus";
import type { FormInstance, FormRules } from "element-plus";
import {
  getMyStrategies,
  getMarketplace,
  createStrategy,
  updateStrategy,
  deleteStrategy,
  submitStrategy,
  checkStrategy,
  type Strategy,
} from "@/api/strategy";
import { formatApiError } from "@/utils/errors";
import { useBreakpoint } from "@/composables/useBreakpoint";
import ResponsiveTable, { type RTColumn } from "@/components/ResponsiveTable.vue";

const { t } = useI18n();
const { isMobile } = useBreakpoint();

const dialogWidth = computed(() => (isMobile.value ? "92%" : "520px"));

// ── My strategies ─────────────────────────────────────────────────────────────

const rows = ref<Strategy[]>([]);
const loading = ref(false);

async function load() {
  loading.value = true;
  try {
    rows.value = await getMyStrategies();
  } catch (e) {
    ElMessage.error(formatApiError(e, "strategy"));
  } finally {
    loading.value = false;
  }
}

// ── Templates (builtin) for create dialog ─────────────────────────────────────

const templates = ref<Strategy[]>([]);
const templatesLoading = ref(false);

async function loadTemplates() {
  if (templates.value.length) return;
  templatesLoading.value = true;
  try {
    // 内置模板供选:filter=builtin,内置数量少,一页(50)足够。
    const res = await getMarketplace({ filter: "builtin", page_size: 50 });
    templates.value = res.results.filter((s) => s.is_builtin || !s.owner_username);
  } catch (e) {
    ElMessage.error(formatApiError(e, "strategy"));
  } finally {
    templatesLoading.value = false;
  }
}

// ── Table columns ─────────────────────────────────────────────────────────────

const cols = computed<RTColumn[]>(() => [
  { prop: "name", label: t("strategy.strategyName"), minWidth: 140 },
  { prop: "template_ref", label: t("strategy.template"), minWidth: 120 },
  { prop: "visibility", label: t("strategy.visibility"), width: 90, align: "center" },
  { prop: "status", label: t("strategy.audit"), width: 110, align: "center" },
  { prop: "check_status", label: t("strategy.checkStatus"), width: 100, align: "center" },
  { prop: "actions", label: t("common.actions"), minWidth: 300, align: "center", fixed: "right" },
]);

// ── Dialog form ───────────────────────────────────────────────────────────────

const dialogVisible = ref(false);
const editingId = ref<number | null>(null);
const saving = ref(false);
const formRef = ref<FormInstance>();

const form = reactive<{
  name: string;
  source_type: "uploaded" | "code";
  template_ref: string;
  description: string;
  visibility: "private" | "public";
  params: Record<string, unknown>;
  code: string;
}>({
  name: "",
  source_type: "uploaded",
  template_ref: "",
  description: "",
  visibility: "private",
  params: {},
  code: "",
});

const CODE_EXAMPLE = `def on_tick(ctx, params):
    candles = ctx.candles(bar="1m", limit=50)
    if not candles:
        return
    closes = [float(c["c"]) for c in candles]
    fast = sum(closes[-5:]) / 5
    slow = sum(closes[-20:]) / 20
    sz = params.get("sz", 0.001)
    if fast > slow:
        ctx.buy(sz)
    elif fast < slow:
        ctx.sell(sz)
    # ctx.log("info", f"fast={fast} slow={slow}")
`;

function fillExample() {
  form.code = CODE_EXAMPLE;
}

const rules = computed<FormRules>(() => ({
  name: [{ required: true, message: t("strategy.strategyName"), trigger: "blur" }],
  template_ref:
    form.source_type === "uploaded"
      ? [{ required: true, message: t("strategy.selectTemplate"), trigger: "change" }]
      : [],
  code:
    form.source_type === "code"
      ? [{ required: true, message: t("strategy.codeRequired"), trigger: "blur" }]
      : [],
}));

const selectedTemplate = computed<Strategy | undefined>(() =>
  templates.value.find((s) => s.code_ref === form.template_ref),
);

function onTemplateChange() {
  const tmpl = selectedTemplate.value;
  if (tmpl?.default_params) {
    form.params = { ...tmpl.default_params };
  } else {
    form.params = {};
  }
}

/** Human-readable label for param keys (dual_ma special casing + generic fallback) */
function paramLabel(key: string): string {
  const map: Record<string, string> = {
    fast_period: t("strategy.fastPeriod"),
    slow_period: t("strategy.slowPeriod"),
    sz: t("strategy.sz"),
  };
  return map[key] ?? key;
}

function openCreate() {
  editingId.value = null;
  form.name = "";
  form.source_type = "uploaded";
  form.template_ref = "";
  form.description = "";
  form.visibility = "private";
  form.params = {};
  form.code = "";
  resetCheck();
  loadTemplates();
  dialogVisible.value = true;
}

function openEdit(row: Strategy) {
  editingId.value = row.id;
  form.name = row.name ?? "";
  form.source_type = row.source_type === "code" ? "code" : "uploaded";
  form.template_ref = row.template_ref ?? row.code_ref ?? "";
  form.description = row.description ?? "";
  form.visibility = row.visibility ?? "private";
  form.params = row.params ? { ...row.params } : {};
  form.code = row.code ?? "";
  setCheck(row);
  loadTemplates();
  dialogVisible.value = true;
}

async function onSave() {
  await formRef.value?.validate().catch(() => { throw new Error("invalid"); });
  saving.value = true;
  try {
    if (editingId.value) {
      const payload =
        form.source_type === "code"
          ? {
              name: form.name,
              code: form.code,
              description: form.description,
              visibility: form.visibility,
            }
          : {
              name: form.name,
              params: { ...form.params },
              description: form.description,
              visibility: form.visibility,
            };
      const updated = await updateStrategy(editingId.value, payload);
      setCheck(updated);
    } else if (form.source_type === "code") {
      const created = await createStrategy({
        name: form.name,
        source_type: "code",
        code: form.code,
        description: form.description,
        visibility: form.visibility,
      });
      setCheck(created);
      // 创建即同步跑检测:留在对话框内展示结果,让用户看到检测报告
      ElMessage.success(t("common.success"));
      await load();
      return;
    } else {
      await createStrategy({
        name: form.name,
        source_type: "uploaded",
        template_ref: form.template_ref,
        params: { ...form.params },
        description: form.description,
        visibility: form.visibility,
      });
    }
    ElMessage.success(t("common.success"));
    dialogVisible.value = false;
    await load();
  } catch (e: unknown) {
    if ((e as Error).message !== "invalid") {
      ElMessage.error(formatApiError(e, "strategy"));
    }
  } finally {
    saving.value = false;
  }
}

// ── Code check (detection) ────────────────────────────────────────────────────

const checkingId = ref<number | null>(null);
const checkStatus = ref<"pending" | "passed" | "failed" | "">("");
const checkReport = ref<Record<string, unknown> | null>(null);

function resetCheck() {
  checkStatus.value = "";
  checkReport.value = null;
}

function setCheck(row: Strategy) {
  if (row.source_type === "code") {
    checkStatus.value = row.check_status ?? "";
    checkReport.value = row.check_report ?? null;
  } else {
    resetCheck();
  }
}

const checkStageLabel = computed(() => {
  const stage = checkReport.value?.stage as string | undefined;
  if (!stage) return "";
  const map: Record<string, string> = {
    syntax: t("strategy.checkStageSyntax"),
    ast: t("strategy.checkStageAst"),
    trial: t("strategy.checkStageTrial"),
  };
  return map[stage] ?? stage;
});

const syntaxError = computed<{ line?: number; msg: string } | null>(() => {
  const r = checkReport.value;
  if (!r || r.stage !== "syntax") return null;
  const msg = (r.error ?? r.msg ?? r.message) as string | undefined;
  if (!msg) return null;
  return { line: r.line as number | undefined, msg };
});

const astViolations = computed<{ line?: number; rule: string }[]>(() => {
  const r = checkReport.value;
  const raw = r?.violations;
  if (!Array.isArray(raw)) return [];
  return raw.map((v) => {
    if (typeof v === "string") return { rule: v };
    const o = v as Record<string, unknown>;
    return { line: o.line as number | undefined, rule: (o.rule ?? o.msg ?? o.message ?? "") as string };
  });
});

const trial = computed<{ ok?: boolean; error?: string; signal_count?: number } | null>(() => {
  const r = checkReport.value;
  if (!r || (r.stage !== "trial" && r.ok === undefined && r.signal_count === undefined)) return null;
  return {
    ok: r.ok as boolean | undefined,
    error: (r.error ?? r.message) as string | undefined,
    signal_count: r.signal_count as number | undefined,
  };
});

async function runCheck(id: number) {
  checkingId.value = id;
  try {
    const updated = await checkStrategy(id);
    setCheck(updated);
    // sync into list row if present
    const idx = rows.value.findIndex((s) => s.id === id);
    if (idx >= 0) rows.value[idx] = updated;
    if (updated.check_status === "passed") {
      ElMessage.success(t("strategy.checkPassed"));
    } else {
      ElMessage.warning(t("strategy.checkFailed"));
    }
  } catch (e) {
    ElMessage.error(formatApiError(e, "strategy"));
  } finally {
    checkingId.value = null;
  }
}

/** Re-check from list row */
async function onCheck(row: Strategy) {
  await runCheck(row.id);
}

/** Re-check from dialog (editing existing code strategy) */
async function onCheckCurrent() {
  if (editingId.value) await runCheck(editingId.value);
}

function checkTagType(status: string): "" | "info" | "success" | "danger" {
  switch (status) {
    case "passed": return "success";
    case "failed": return "danger";
    case "pending": return "info";
    default: return "";
  }
}

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** code 策略需 check_status==passed 才能提交;非 code 策略不受限 */
function canSubmit(row: Strategy): boolean {
  if (row.source_type === "code") return row.check_status === "passed";
  return true;
}

// ── Submit for audit ──────────────────────────────────────────────────────────

async function onSubmit(row: Strategy) {
  try {
    await ElMessageBox.confirm(
      t("strategy.submitAuditConfirm"),
      t("strategy.submitAudit"),
      { type: "warning", confirmButtonText: t("common.confirm"), cancelButtonText: t("common.cancel") },
    );
  } catch {
    return;
  }
  try {
    await submitStrategy(row.id);
    ElMessage.success(t("common.success"));
    await load();
  } catch (e) {
    ElMessage.error(formatApiError(e, "strategy"));
  }
}

// ── Delete ────────────────────────────────────────────────────────────────────

async function onDelete(row: Strategy) {
  try {
    await ElMessageBox.confirm(
      t("strategy.deleteStrategyConfirm", { name: row.name }),
      t("strategy.deleteStrategy"),
      { type: "warning", confirmButtonText: t("common.confirm"), cancelButtonText: t("common.cancel") },
    );
  } catch {
    return;
  }
  try {
    await deleteStrategy(row.id);
    ElMessage.success(t("common.success"));
    await load();
  } catch (e: unknown) {
    // 400 = 该策略有运行记录,不能删(后端 ProtectedError)
    const status = (e as { response?: { status?: number } })?.response?.status;
    if (status === 400) {
      ElMessage.error(t("strategy.deleteHasRun"));
    } else {
      ElMessage.error(formatApiError(e, "strategy"));
    }
  }
}

// ── Audit tag type ────────────────────────────────────────────────────────────

function auditTagType(status: string): "" | "info" | "warning" | "success" | "danger" {
  switch (status) {
    case "draft": return "info";
    case "pending": return "warning";
    case "approved": return "success";
    case "rejected": return "danger";
    default: return "";
  }
}

// ── Lifecycle ─────────────────────────────────────────────────────────────────

onMounted(load);
</script>

<style scoped lang="scss">
@use "@/styles/mixins" as *;

.my-strategies-page {
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

.action-btns {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
  justify-content: center;
}

.form-readonly {
  font-size: var(--font-size-sm);
  color: var(--gray-600);
  background: var(--gray-50);
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--gray-200);
}

.code-field {
  width: 100%;
}

.code-field-toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
}

.code-contract {
  font-size: var(--font-size-xs);
  color: var(--gray-500);
  line-height: 1.4;
}

.code-textarea :deep(textarea) {
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
  font-size: 13px;
  line-height: 1.5;
  white-space: pre;
  overflow-wrap: normal;
  overflow-x: auto;
}

.check-panel {
  width: 100%;
  font-size: var(--font-size-sm);
  color: var(--gray-700);
  background: var(--gray-50);
  border: 1px solid var(--gray-200);
  border-radius: var(--radius-sm);
  padding: var(--space-3);
}

.check-line {
  margin-bottom: 4px;
}

.check-list {
  margin: 4px 0 0;
  padding-left: 18px;
}

.check-err {
  color: var(--el-color-danger, #f56c6c);
}

.check-ok {
  color: var(--el-color-success, #67c23a);
}
</style>
