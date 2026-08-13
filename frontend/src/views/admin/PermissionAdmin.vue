<template>
  <div class="permission-admin">
    <div class="page-header">
      <h2 class="page-title">{{ t("admin.permissions.title") }}</h2>
    </div>

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
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage } from "element-plus";
import { fetchPermissions, type PermissionsRegistry } from "@/api/accounts";
import { formatApiError } from "@/utils/errors";

const { t, locale } = useI18n();

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

onMounted(async () => {
  loading.value = true;
  try { registry.value = await fetchPermissions(); }
  catch (e) { ElMessage.error(formatApiError(e, "admin")); }
  finally { loading.value = false; }
});
</script>

<style scoped>
.permission-admin {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}
.page-header {
  display: flex;
  align-items: center;
}
.page-title {
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: 600;
  color: var(--gray-800);
}
</style>
