<template>
  <div class="credential-panel">
    <div class="page-header">
      <h2 class="page-title">{{ t("credentials.title") }}</h2>
      <el-button type="primary" @click="openCreate">
        {{ t("credentials.create") }}
      </el-button>
    </div>

    <el-table :data="credentials" size="small" border v-loading="tableLoading">
      <el-table-column prop="env" :label="t('credentials.columns.env')" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="row.env === 'live' ? 'danger' : 'warning'" size="small">
            {{ row.env === "live" ? t("credentials.envLive") : t("credentials.envSim") }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="label" :label="t('credentials.columns.label')" />
      <el-table-column
        prop="api_key_masked"
        :label="t('credentials.columns.apiKey')"
        align="center"
      />
      <el-table-column
        prop="created_at"
        :label="t('credentials.columns.createdAt')"
        width="180"
        align="center"
      >
        <template #default="{ row }">
          {{ formatDate(row.created_at) }}
        </template>
      </el-table-column>
      <el-table-column :label="t('credentials.columns.actions')" width="120" align="center">
        <template #default="{ row }">
          <el-button size="small" type="danger" @click="onDelete(row)">
            {{ t("common.delete") }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 新建密钥 dialog -->
    <el-dialog v-model="createVisible" :title="t('credentials.create')" width="480px">
      <el-form label-width="110px">
        <el-form-item :label="t('credentials.form.env')">
          <el-select v-model="form.env" style="width: 100%;">
            <el-option :label="t('credentials.envSim')" value="sim" />
            <el-option :label="t('credentials.envLive')" value="live" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('credentials.form.label')">
          <el-input v-model="form.label" :placeholder="t('credentials.form.labelPlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('credentials.form.apiKey')">
          <el-input
            v-model="form.api_key"
            :placeholder="t('credentials.form.apiKeyPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('credentials.form.secret')">
          <el-input
            v-model="form.secret"
            type="password"
            show-password
            :placeholder="t('credentials.form.secretPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('credentials.form.passphrase')">
          <el-input
            v-model="form.passphrase"
            type="password"
            show-password
            :placeholder="t('credentials.form.passphrasePlaceholder')"
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
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  listCredentials,
  createCredential,
  deleteCredential,
  type Credential,
} from "@/api/credentials";
import { formatApiError } from "@/utils/errors";

const { t } = useI18n();

const credentials = ref<Credential[]>([]);
const tableLoading = ref(false);
const saving = ref(false);
const createVisible = ref(false);

const form = reactive<{
  env: "sim" | "live";
  label: string;
  api_key: string;
  secret: string;
  passphrase: string;
}>({
  env: "sim",
  label: "",
  api_key: "",
  secret: "",
  passphrase: "",
});

function formatDate(iso: string): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

async function reload() {
  tableLoading.value = true;
  try {
    credentials.value = await listCredentials();
  } catch (e) {
    ElMessage.error(formatApiError(e, "credentials"));
  } finally {
    tableLoading.value = false;
  }
}

function openCreate() {
  Object.assign(form, { env: "sim", label: "", api_key: "", secret: "", passphrase: "" });
  createVisible.value = true;
}

async function onCreate() {
  if (!form.label.trim()) {
    ElMessage.error(t("credentials.form.labelRequired"));
    return;
  }
  if (!form.api_key.trim()) {
    ElMessage.error(t("credentials.form.apiKeyRequired"));
    return;
  }
  if (!form.secret.trim()) {
    ElMessage.error(t("credentials.form.secretRequired"));
    return;
  }
  if (!form.passphrase.trim()) {
    ElMessage.error(t("credentials.form.passphraseRequired"));
    return;
  }
  saving.value = true;
  try {
    await createCredential({ ...form });
    ElMessage.success(t("credentials.createSuccess"));
    createVisible.value = false;
    await reload();
  } catch (e) {
    ElMessage.error(formatApiError(e, "credentials"));
  } finally {
    saving.value = false;
  }
}

async function onDelete(row: Credential) {
  try {
    await ElMessageBox.confirm(
      t("credentials.deleteConfirm", { label: row.label }),
      t("common.delete"),
      { type: "warning" },
    );
  } catch {
    return;
  }
  try {
    await deleteCredential(row.id);
    ElMessage.success(t("common.success"));
    await reload();
  } catch (e) {
    ElMessage.error(formatApiError(e, "credentials"));
  }
}

onMounted(reload);
</script>

<style scoped>
.credential-panel {
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
:deep(.el-table th.el-table__cell > .cell) { text-align: center; }
</style>
