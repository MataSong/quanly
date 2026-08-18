<template>
  <div class="user-panel">
    <div class="page-header">
      <h2 class="page-title">{{ t("admin.users.title") }}</h2>
      <el-button type="primary" @click="openCreate">
        {{ t("admin.users.create") }}
      </el-button>
    </div>

    <div class="table-scroll">
    <el-table :data="users" size="small" border v-loading="tableLoading">
      <el-table-column prop="username" :label="t('admin.users.columns.username')" width="160" />
      <el-table-column prop="email" :label="t('admin.users.columns.email')" />
      <el-table-column :label="t('admin.users.columns.status')" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
            {{ row.is_active ? t("admin.users.active") : t("admin.users.inactive") }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column :label="t('admin.users.columns.roles')" align="center">
        <template #default="{ row }">
          <span v-if="row.is_superuser">{{ t("admin.users.superuser") }}</span>
          <span v-else>{{ roleNames(row.roles) || "—" }}</span>
        </template>
      </el-table-column>
      <el-table-column :label="t('admin.users.columns.authSource')" width="120" align="center">
        <template #default="{ row }">
          {{ row.auth_source === "sso" ? t("admin.users.authSso") : t("admin.users.authLocal") }}
        </template>
      </el-table-column>
      <el-table-column :label="t('admin.users.columns.actions')" width="400" align="center">
        <template #default="{ row }">
          <el-button size="small" :disabled="row.is_superuser" @click="openRoles(row)">
            {{ t("admin.users.editRoles") }}
          </el-button>
          <el-button size="small" :disabled="row.is_superuser" @click="openOverrides(row)">
            {{ t("admin.users.editOverrides") }}
          </el-button>
          <el-button size="small" @click="onResetPassword(row)">
            {{ t("admin.users.resetPassword") }}
          </el-button>
          <el-button
            size="small"
            type="danger"
            :disabled="row.is_superuser || row.id === auth.user?.id"
            @click="onDeleteUser(row)"
          >
            {{ t("admin.users.delete") }}
          </el-button>
          <el-switch
            :model-value="row.is_active"
            :disabled="row.is_superuser"
            class="active-switch"
            @change="(v: boolean) => onToggleActive(row, v)"
          />
        </template>
      </el-table-column>
    </el-table>
    </div>

    <!-- 新建用户 -->
    <el-dialog v-model="createVisible" :title="t('admin.users.create')" :width="dialogWidthSm">
      <el-form label-width="100px" :label-position="isMobile ? 'top' : 'right'">
        <el-form-item :label="t('admin.users.username')">
          <el-input v-model="createForm.username" />
        </el-form-item>
        <el-form-item :label="t('admin.users.email')">
          <el-input v-model="createForm.email" />
        </el-form-item>
        <el-form-item :label="t('admin.users.authSource')">
          <el-select v-model="createForm.authSource" style="width: 100%;">
            <el-option :label="t('admin.users.authLocal')" value="local" />
            <el-option :label="t('admin.users.authSso')" value="sso" />
          </el-select>
        </el-form-item>
        <template v-if="createForm.authSource === 'local'">
          <el-form-item :label="t('admin.users.newPassword')">
            <el-input
              v-model="createForm.password"
              type="password"
              show-password
              :placeholder="t('admin.users.passwordPlaceholder')"
            />
          </el-form-item>
          <el-form-item>
            <PasswordStrength :password="createForm.password" />
          </el-form-item>
          <el-form-item :label="t('admin.users.confirmPassword')">
            <el-input v-model="createForm.password2" type="password" show-password />
          </el-form-item>
        </template>
        <el-form-item v-else :label="t('admin.users.externalId')">
          <el-input
            v-model="createForm.externalId"
            :placeholder="t('admin.users.externalIdPlaceholder')"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">{{ t("common.cancel") }}</el-button>
        <el-button type="primary" :loading="saving" @click="onCreate">
          {{ t("common.confirm") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 编辑角色 -->
    <el-dialog v-model="rolesVisible" :title="t('admin.users.editRoles')" :width="dialogWidthSm">
      <el-checkbox-group v-model="selectedRoleIds">
        <el-checkbox v-for="r in allRoles" :key="r.id" :value="r.id">
          {{ r.name }}
        </el-checkbox>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="rolesVisible = false">{{ t("common.cancel") }}</el-button>
        <el-button type="primary" :loading="saving" @click="onSaveRoles">
          {{ t("common.confirm") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 权限覆盖 -->
    <el-dialog v-model="overridesVisible" :title="t('admin.overrides.title')" :width="dialogWidthMd">
      <div class="override-add">
        <el-select
          v-model="ovPermission"
          filterable
          :placeholder="t('admin.roles.permissions')"
          :style="{ width: isMobile ? '100%' : '240px' }"
        >
          <el-option v-for="code in allCodes" :key="code" :label="code" :value="code" />
        </el-select>
        <el-select v-model="ovEffect" :style="{ width: isMobile ? '100%' : '120px' }">
          <el-option :label="t('admin.overrides.grant')" value="grant" />
          <el-option :label="t('admin.overrides.deny')" value="deny" />
        </el-select>
        <el-button type="primary" @click="onAddOverride">
          {{ t("admin.overrides.add") }}
        </el-button>
      </div>
      <el-table :data="overrides" size="small" border style="margin-top: 12px;">
        <el-table-column
          prop="permission"
          :label="t('admin.overrides.colPermission')"
          align="center"
        />
        <el-table-column
          prop="effect"
          :label="t('admin.overrides.colEffect')"
          width="120"
          align="center"
        >
          <template #default="{ row }">
            {{ row.effect === "grant" ? t("admin.overrides.grant") : t("admin.overrides.deny") }}
          </template>
        </el-table-column>
        <el-table-column :label="t('admin.overrides.colActions')" width="90" align="center">
          <template #default="{ row }">
            <el-button size="small" type="danger" @click="onDeleteOverride(row)">
              {{ t("common.delete") }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="!overrides.length" class="ov-empty">{{ t("admin.overrides.empty") }}</div>
    </el-dialog>

    <!-- 重置密码 -->
    <el-dialog v-model="resetVisible" :title="t('admin.users.resetPassword')" :width="dialogWidthSm">
      <el-form label-width="100px" :label-position="isMobile ? 'top' : 'right'">
        <el-form-item :label="t('admin.users.newPassword')">
          <el-input
            v-model="resetForm.password"
            type="password"
            show-password
            :placeholder="t('admin.users.passwordPlaceholder')"
          />
        </el-form-item>
        <el-form-item>
          <PasswordStrength :password="resetForm.password" />
        </el-form-item>
        <el-form-item :label="t('admin.users.confirmPassword')">
          <el-input v-model="resetForm.password2" type="password" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="resetVisible = false">{{ t("common.cancel") }}</el-button>
        <el-button type="primary" :loading="saving" @click="onResetSubmit">
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
  listUsers, createUser, deleteUser, setUserRoles, setUserActive,
  resetUserPassword, listOverrides, addOverride, deleteOverride, listRoles,
  fetchPermissions,
  type AdminUser, type Override, type Role,
} from "@/api/accounts";
import { formatApiError } from "@/utils/errors";
import { useAuthStore } from "@/stores/auth";
import PasswordStrength from "@/components/PasswordStrength.vue";
import { checkRules } from "@/utils/password";
import { useBreakpoint } from "@/composables/useBreakpoint";

const { t } = useI18n();
const auth = useAuthStore();
const { isMobile } = useBreakpoint();

const dialogWidthSm = computed(() => isMobile.value ? '92%' : '440px');
const dialogWidthMd = computed(() => isMobile.value ? '92%' : '560px');

const users = ref<AdminUser[]>([]);
const allRoles = ref<Role[]>([]);
const tableLoading = ref(false);
const saving = ref(false);

// All permission codes for override picker — flatten from auth.user.permissions or keep empty
const allCodes = ref<string[]>([]);

function roleNames(ids: number[]) {
  return allRoles.value.filter((r) => ids.includes(r.id)).map((r) => r.name).join(", ");
}

async function reload() {
  tableLoading.value = true;
  try {
    [users.value, allRoles.value] = await Promise.all([listUsers(), listRoles()]);
    // 填充权限覆盖下拉的候选权限码(展平权限点注册表各分组的 items keys)
    const reg = await fetchPermissions();
    allCodes.value = Object.values(reg).flatMap((g) => Object.keys(g.items));
  } catch (e) {
    ElMessage.error(formatApiError(e, "admin"));
  } finally {
    tableLoading.value = false;
  }
}

// --- Create user ---
const createVisible = ref(false);
const createForm = reactive({
  username: "", email: "", password: "", password2: "",
  authSource: "local" as "local" | "sso", externalId: "",
});
function openCreate() {
  Object.assign(createForm, {
    username: "", email: "", password: "", password2: "",
    authSource: "local", externalId: "",
  });
  createVisible.value = true;
}
async function onCreate() {
  if (createForm.authSource === "local") {
    if (!checkRules(createForm.password).valid) {
      ElMessage.error(t("admin.users.passwordTooWeak")); return;
    }
    if (createForm.password !== createForm.password2) {
      ElMessage.error(t("admin.users.passwordMismatch")); return;
    }
  }
  saving.value = true;
  try {
    await createUser({
      username: createForm.username,
      email: createForm.email,
      auth_source: createForm.authSource,
      password: createForm.authSource === "local" ? createForm.password : undefined,
      external_id: createForm.authSource === "sso" ? createForm.externalId : undefined,
    });
    ElMessage.success(t("admin.users.createSuccess"));
    createVisible.value = false;
    await reload();
  } catch (e) {
    ElMessage.error(formatApiError(e, "admin"));
  } finally { saving.value = false; }
}

// --- Edit roles ---
const rolesVisible = ref(false);
const rolesTarget = ref<AdminUser | null>(null);
const selectedRoleIds = ref<number[]>([]);
function openRoles(row: AdminUser) {
  rolesTarget.value = row;
  selectedRoleIds.value = [...row.roles];
  rolesVisible.value = true;
}
async function onSaveRoles() {
  if (!rolesTarget.value) return;
  saving.value = true;
  try {
    await setUserRoles(rolesTarget.value.id, selectedRoleIds.value);
    ElMessage.success(t("admin.users.updateSuccess"));
    rolesVisible.value = false;
    await reload();
  } catch (e) {
    ElMessage.error(formatApiError(e, "admin"));
  } finally { saving.value = false; }
}

// --- Overrides ---
const overridesVisible = ref(false);
const overridesTarget = ref<AdminUser | null>(null);
const overrides = ref<Override[]>([]);
const ovPermission = ref("");
const ovEffect = ref<"grant" | "deny">("grant");

async function openOverrides(row: AdminUser) {
  overridesTarget.value = row;
  ovPermission.value = ""; ovEffect.value = "grant";
  overridesVisible.value = true;
  try { overrides.value = await listOverrides(row.id); }
  catch (e) { ElMessage.error(formatApiError(e, "admin")); }
}
async function onAddOverride() {
  if (!overridesTarget.value || !ovPermission.value) return;
  try {
    await addOverride(overridesTarget.value.id, ovPermission.value, ovEffect.value);
    overrides.value = await listOverrides(overridesTarget.value.id);
  } catch (e) { ElMessage.error(formatApiError(e, "admin")); }
}
async function onDeleteOverride(row: Override) {
  if (!overridesTarget.value) return;
  try {
    await deleteOverride(overridesTarget.value.id, row.id);
    overrides.value = await listOverrides(overridesTarget.value.id);
  } catch (e) { ElMessage.error(formatApiError(e, "admin")); }
}

// --- Toggle active / reset password ---
async function onToggleActive(row: AdminUser, v: boolean) {
  try {
    await setUserActive(row.id, v);
    await reload();
  } catch (e) { ElMessage.error(formatApiError(e, "admin")); }
}

const resetVisible = ref(false);
const resetTarget = ref<AdminUser | null>(null);
const resetForm = reactive({ password: "", password2: "" });

function onResetPassword(row: AdminUser) {
  resetTarget.value = row;
  resetForm.password = ""; resetForm.password2 = "";
  resetVisible.value = true;
}
async function onResetSubmit() {
  if (!resetTarget.value) return;
  if (!checkRules(resetForm.password).valid) {
    ElMessage.error(t("admin.users.passwordTooWeak")); return;
  }
  if (resetForm.password !== resetForm.password2) {
    ElMessage.error(t("admin.users.passwordMismatch")); return;
  }
  saving.value = true;
  try {
    await resetUserPassword(resetTarget.value.id, resetForm.password);
    ElMessage.success(t("admin.users.updateSuccess"));
    resetVisible.value = false;
  } catch (e) {
    ElMessage.error(formatApiError(e, "admin"));
  } finally { saving.value = false; }
}

// --- Delete user ---
async function onDeleteUser(row: AdminUser) {
  try {
    await ElMessageBox.confirm(
      t("admin.users.deleteConfirm", { name: row.username }),
      t("admin.users.delete"),
      { type: "warning" },
    );
  } catch { return; }
  try {
    await deleteUser(row.id);
    ElMessage.success(t("common.success"));
    await reload();
  } catch (e) { ElMessage.error(formatApiError(e, "admin")); }
}

onMounted(reload);
</script>

<style scoped>
.user-panel {
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
.override-add {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: center;
}
.ov-empty {
  color: var(--gray-500);
  padding: var(--space-2);
}
.active-switch { margin-left: 12px; }
.table-scroll { overflow-x: auto; }
:deep(.el-table th.el-table__cell > .cell) { text-align: center; }
</style>
