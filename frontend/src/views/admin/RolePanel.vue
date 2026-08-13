<template>
  <div class="role-panel">
    <div class="page-header">
      <h2 class="page-title">{{ t("admin.roles.title") }}</h2>
      <el-button type="primary" @click="openCreate">
        {{ t("admin.roles.create") }}
      </el-button>
    </div>

    <el-table :data="roles" size="small" border v-loading="tableLoading">
      <el-table-column prop="name" :label="t('admin.roles.columns.name')" width="200" />
      <el-table-column prop="description" :label="t('admin.roles.columns.description')" />
      <el-table-column :label="t('admin.roles.columns.permissions')" width="120" align="center">
        <template #default="{ row }">{{ row.permissions.length }}</template>
      </el-table-column>
      <el-table-column :label="t('admin.roles.columns.system')" width="120" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.is_system" size="small" type="warning">
            {{ t("admin.roles.systemRole").split("（")[0] }}
          </el-tag>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column :label="t('admin.roles.columns.actions')" width="180" align="center">
        <template #default="{ row }">
          <el-button size="small" @click="openEdit(row)">
            {{ t("admin.roles.edit") }}
          </el-button>
          <el-button
            size="small"
            type="danger"
            :disabled="row.is_system"
            @click="onDelete(row)"
          >
            {{ t("admin.roles.delete") }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="640px">
      <el-form label-width="90px">
        <el-form-item :label="t('admin.roles.name')">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item :label="t('admin.roles.description')">
          <el-input v-model="form.description" />
        </el-form-item>
        <el-form-item :label="t('admin.roles.permissions')">
          <div class="perm-tree" v-if="Object.keys(registry).length">
            <div v-for="(group, gkey) in registry" :key="gkey" class="perm-group">
              <div class="perm-group-title">{{ groupLabel(group) }}</div>
              <el-checkbox-group v-model="form.permissions">
                <el-checkbox
                  v-for="(meta, code) in group.items"
                  :key="code"
                  :value="code"
                  :label="code"
                >
                  {{ itemLabel(meta) }}
                </el-checkbox>
              </el-checkbox-group>
            </div>
          </div>
          <div v-else class="perm-empty">{{ t("common.loading") }}…</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{ t("common.cancel") }}</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">
          {{ t("common.confirm") }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  listRoles, createRole, updateRole, deleteRole, fetchPermissions,
  type PermissionsRegistry, type PermGroup, type PermItem, type Role,
} from "@/api/accounts";
import { formatApiError } from "@/utils/errors";

const { t, locale } = useI18n();

const roles = ref<Role[]>([]);
const registry = ref<PermissionsRegistry>({});
const tableLoading = ref(false);
const dialogVisible = ref(false);
const saving = ref(false);
const editingId = ref<number | null>(null);
const form = reactive({ name: "", description: "", permissions: [] as string[] });

const dialogTitle = computed(() =>
  editingId.value ? t("admin.roles.edit") : t("admin.roles.create"),
);

function isZh() { return locale.value.startsWith("zh"); }
function groupLabel(g: PermGroup) { return isZh() ? g.label_zh : g.label_en; }
function itemLabel(m: PermItem) { return isZh() ? m.zh : m.en; }

async function reload() {
  tableLoading.value = true;
  try { roles.value = await listRoles(); }
  catch (e) { ElMessage.error(formatApiError(e, "admin")); }
  finally { tableLoading.value = false; }
}

function openCreate() {
  editingId.value = null;
  form.name = ""; form.description = ""; form.permissions = [];
  dialogVisible.value = true;
}

function openEdit(row: Role) {
  editingId.value = row.id;
  form.name = row.name;
  form.description = row.description;
  form.permissions = [...row.permissions];
  dialogVisible.value = true;
}

async function onSave() {
  saving.value = true;
  try {
    const payload = { name: form.name, description: form.description, permissions: form.permissions };
    if (editingId.value) await updateRole(editingId.value, payload);
    else await createRole(payload);
    ElMessage.success(t("admin.roles.saveSuccess"));
    dialogVisible.value = false;
    await reload();
  } catch (e) {
    ElMessage.error(formatApiError(e, "admin"));
  } finally { saving.value = false; }
}

async function onDelete(row: Role) {
  try {
    await ElMessageBox.confirm(
      t("admin.roles.deleteConfirm", { name: row.name }),
      t("admin.roles.delete"),
      { type: "warning" },
    );
  } catch { return; }
  try {
    await deleteRole(row.id);
    ElMessage.success(t("admin.roles.deleteSuccess"));
    await reload();
  } catch (e) { ElMessage.error(formatApiError(e, "admin")); }
}

onMounted(async () => {
  await reload();
  try { registry.value = await fetchPermissions(); }
  catch (e) { ElMessage.error(formatApiError(e, "admin")); }
});
</script>

<style scoped>
.role-panel {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
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
.perm-tree {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  max-height: 360px;
  overflow-y: auto;
  width: 100%;
}
.perm-group-title {
  font-weight: 600;
  margin-bottom: 4px;
  color: var(--gray-700);
}
.perm-empty { color: var(--gray-500); }
:deep(.el-table th.el-table__cell > .cell) { text-align: center; }
:deep(.el-table td.el-table__cell > .cell) { text-align: center; }
</style>
