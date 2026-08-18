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

        <!-- Actions -->
        <template #cell-actions="{ row }">
          <div class="action-btns">
            <!-- Edit -->
            <el-button size="small" @click.stop="openEdit(row as Strategy)">
              {{ t("common.edit") }}
            </el-button>

            <!-- Submit for audit (draft / rejected only) -->
            <el-button
              v-if="row.status === 'draft' || row.status === 'rejected'"
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
        <!-- Template (only when creating) -->
        <el-form-item v-if="!editingId" :label="t('strategy.template')" prop="template_ref">
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
        <el-form-item v-else :label="t('strategy.template')">
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

        <!-- Dynamic params based on selected template's default_params -->
        <template v-if="selectedTemplate">
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

        <!-- Visibility -->
        <el-form-item :label="t('strategy.visibility')">
          <el-radio-group v-model="form.visibility">
            <el-radio value="private">{{ t("strategy.visibilityOpt.private") }}</el-radio>
            <el-radio value="public">{{ t("strategy.visibilityOpt.public") }}</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">{{ t("common.cancel") }}</el-button>
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
    const all = await getMarketplace();
    templates.value = all.filter((s) => s.is_builtin || !s.owner_username);
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
  { prop: "actions", label: t("common.actions"), minWidth: 240, align: "center", fixed: "right" },
]);

// ── Dialog form ───────────────────────────────────────────────────────────────

const dialogVisible = ref(false);
const editingId = ref<number | null>(null);
const saving = ref(false);
const formRef = ref<FormInstance>();

const form = reactive<{
  name: string;
  template_ref: string;
  description: string;
  visibility: "private" | "public";
  params: Record<string, unknown>;
}>({
  name: "",
  template_ref: "",
  description: "",
  visibility: "private",
  params: {},
});

const rules: FormRules = {
  name: [{ required: true, message: t("strategy.strategyName"), trigger: "blur" }],
  template_ref: [{ required: true, message: t("strategy.selectTemplate"), trigger: "change" }],
};

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
  form.template_ref = "";
  form.description = "";
  form.visibility = "private";
  form.params = {};
  loadTemplates();
  dialogVisible.value = true;
}

function openEdit(row: Strategy) {
  editingId.value = row.id;
  form.name = row.name ?? "";
  form.template_ref = row.template_ref ?? row.code_ref ?? "";
  form.description = row.description ?? "";
  form.visibility = row.visibility ?? "private";
  form.params = row.params ? { ...row.params } : {};
  loadTemplates();
  dialogVisible.value = true;
}

async function onSave() {
  await formRef.value?.validate().catch(() => { throw new Error("invalid"); });
  saving.value = true;
  try {
    if (editingId.value) {
      await updateStrategy(editingId.value, {
        name: form.name,
        params: { ...form.params },
        description: form.description,
        visibility: form.visibility,
      });
    } else {
      await createStrategy({
        name: form.name,
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
</style>
