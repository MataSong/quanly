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
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage } from "element-plus";
import UserPanel from "./UserPanel.vue";
import RolePanel from "./RolePanel.vue";
import { fetchPermissions, type PermissionsRegistry } from "@/api/accounts";
import { formatApiError } from "@/utils/errors";

const { t, locale } = useI18n();
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
});
</script>

<style scoped>
.permission-admin { padding: 0; }
.admin-tabs { margin-top: 0; }
.perm-tab { margin-top: var(--space-4, 16px); overflow-x: auto; }
</style>
