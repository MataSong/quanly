<template>
  <div class="permission-admin">
    <el-tabs v-model="activeTab" class="admin-tabs">
      <el-tab-pane :label="t('admin.tabs.users')" name="users">
        <UserPanel v-if="activeTab === 'users'" />
      </el-tab-pane>
      <el-tab-pane :label="t('admin.tabs.roles')" name="roles">
        <RolePanel v-if="activeTab === 'roles'" />
      </el-tab-pane>
      <el-tab-pane :label="t('admin.tabs.permissions')" name="permissions">
        <div v-if="activeTab === 'permissions'" class="perm-tab">
          <el-table
            :data="tableData"
            size="small"
            border
            v-loading="loading"
          >
            <el-table-column
              prop="code"
              :label="t('admin.permissions.columns.code')"
              width="260"
            />
            <el-table-column
              prop="group"
              :label="t('admin.permissions.columns.group')"
              width="180"
            />
            <el-table-column
              prop="description"
              :label="t('admin.permissions.columns.description')"
            />
          </el-table>
        </div>
      </el-tab-pane>

      <!-- Strategy audit tab — visible only to users with strategy:audit perm -->
      <el-tab-pane
        v-if="auth.hasPerm('strategy:audit')"
        :label="t('strategy.audit')"
        name="strategy-audit"
      >
        <div v-if="activeTab === 'strategy-audit'" class="audit-tab">
          <div class="audit-header">
            <span class="audit-title">{{ t("strategy.audit") }}</span>
            <el-button size="small" :loading="auditLoading" @click="loadPending">
              {{ t("common.refresh") }}
            </el-button>
          </div>
          <ResponsiveTable
            :columns="auditCols"
            :data="pendingList"
            row-key="id"
            :empty-text="t('common.empty')"
            v-loading="auditLoading"
          >
            <!-- Params summary -->
            <template #cell-params="{ row }">
              <div class="param-chips">
                <span
                  v-for="(val, key) in (row.params || row.default_params || {})"
                  :key="String(key)"
                  class="param-chip"
                >{{ key }}: {{ val }}</span>
              </div>
            </template>
            <!-- Actions -->
            <template #cell-audit_actions="{ row }">
              <div class="audit-btns">
                <el-button
                  size="small"
                  type="success"
                  :loading="auditId === row.id && auditAction === 'approve'"
                  @click="onApprove(row as Strategy)"
                >
                  {{ t("strategy.approve") }}
                </el-button>
                <el-button
                  size="small"
                  type="danger"
                  :loading="auditId === row.id && auditAction === 'reject'"
                  @click="openReject(row as Strategy)"
                >
                  {{ t("strategy.reject") }}
                </el-button>
              </div>
            </template>
          </ResponsiveTable>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>

  <!-- Reject reason dialog -->
  <el-dialog
    v-model="rejectDialogVisible"
    :title="t('strategy.reject')"
    width="400px"
    :close-on-click-modal="false"
  >
    <el-form :model="rejectForm" label-position="top">
      <el-form-item :label="t('strategy.rejectReason')">
        <el-input
          v-model="rejectForm.reason"
          type="textarea"
          :rows="3"
          :placeholder="t('strategy.rejectReasonPlaceholder')"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="rejectDialogVisible = false">{{ t("common.cancel") }}</el-button>
      <el-button type="danger" :loading="auditAction === 'reject'" @click="onRejectConfirm">
        {{ t("strategy.reject") }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage } from "element-plus";
import UserPanel from "./UserPanel.vue";
import RolePanel from "./RolePanel.vue";
import { fetchPermissions, type PermissionsRegistry } from "@/api/accounts";
import { getAdminPending, reviewStrategy, type Strategy } from "@/api/strategy";
import { formatApiError } from "@/utils/errors";
import { useAuthStore } from "@/stores/auth";
import ResponsiveTable, { type RTColumn } from "@/components/ResponsiveTable.vue";

const { t, locale } = useI18n();
const auth = useAuthStore();
const activeTab = ref("users");
const loading = ref(false);
const registry = ref<PermissionsRegistry>({});

interface PermRow { code: string; group: string; description: string; }

const tableData = computed<PermRow[]>(() => {
  const rows: PermRow[] = [];
  const isZh = locale.value.startsWith("zh");
  for (const [, group] of Object.entries(registry.value)) {
    const groupName = isZh ? group.label_zh : group.label_en;
    for (const [code, meta] of Object.entries(group.items)) {
      rows.push({
        code,
        group: groupName,
        description: isZh ? meta.zh : meta.en,
      });
    }
  }
  return rows;
});

// Load permissions data lazily when user switches to permissions tab
watch(activeTab, async (tab) => {
  if (tab === "permissions" && Object.keys(registry.value).length === 0) {
    loading.value = true;
    try { registry.value = await fetchPermissions(); }
    catch (e) { ElMessage.error(formatApiError(e, "admin")); }
    finally { loading.value = false; }
  }
  if (tab === "strategy-audit") {
    await loadPending();
  }
});

// ── Strategy audit ─────────────────────────────────────────────────────────────

const pendingList = ref<Strategy[]>([]);
const auditLoading = ref(false);
const auditId = ref<number | null>(null);
const auditAction = ref<"approve" | "reject" | null>(null);

const auditCols = computed<RTColumn[]>(() => [
  { prop: "name", label: t("strategy.strategyName"), minWidth: 140 },
  { prop: "owner_username", label: t("strategy.reviewOwner"), width: 120 },
  { prop: "template_ref", label: t("strategy.template"), width: 120 },
  { prop: "params", label: t("strategy.paramsCol"), minWidth: 160 },
  { prop: "description", label: t("common.description"), minWidth: 160 },
  { prop: "audit_actions", label: t("common.actions"), width: 160, align: "center", fixed: "right" },
]);

async function loadPending() {
  auditLoading.value = true;
  try {
    pendingList.value = await getAdminPending();
  } catch (e) {
    ElMessage.error(formatApiError(e, "strategy"));
  } finally {
    auditLoading.value = false;
  }
}

async function onApprove(row: Strategy) {
  auditId.value = row.id;
  auditAction.value = "approve";
  try {
    await reviewStrategy(row.id, "approve");
    ElMessage.success(t("common.success"));
    await loadPending();
  } catch (e) {
    ElMessage.error(formatApiError(e, "strategy"));
  } finally {
    auditId.value = null;
    auditAction.value = null;
  }
}

// Reject flow — open dialog for reason
const rejectDialogVisible = ref(false);
const rejectTargetId = ref<number | null>(null);
const rejectForm = reactive({ reason: "" });

function openReject(row: Strategy) {
  rejectTargetId.value = row.id;
  rejectForm.reason = "";
  rejectDialogVisible.value = true;
}

async function onRejectConfirm() {
  if (!rejectTargetId.value) return;
  auditId.value = rejectTargetId.value;
  auditAction.value = "reject";
  try {
    await reviewStrategy(rejectTargetId.value, "reject", rejectForm.reason || undefined);
    ElMessage.success(t("common.success"));
    rejectDialogVisible.value = false;
    await loadPending();
  } catch (e) {
    ElMessage.error(formatApiError(e, "strategy"));
  } finally {
    auditId.value = null;
    auditAction.value = null;
  }
}
</script>

<style scoped>
.permission-admin { padding: 0; }
.admin-tabs { margin-top: 0; }
.perm-tab { margin-top: var(--space-4, 16px); overflow-x: auto; }

.audit-tab { margin-top: var(--space-4, 16px); }
.audit-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-3, 12px);
}
.audit-title {
  font-size: var(--font-size-md, 13px);
  font-weight: 600;
  color: var(--gray-700, #2d3748);
}
.audit-btns {
  display: flex;
  gap: 6px;
  justify-content: center;
}
.param-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.param-chip {
  font-size: 11px;
  color: var(--gray-600, #4a5568);
  background: var(--gray-100, #f0f4f8);
  padding: 2px 5px;
  border-radius: 4px;
}
</style>
