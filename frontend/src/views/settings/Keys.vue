<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import client from "@/api/client";
import Pagination from "@/components/Pagination.vue";
import GlassSelect from "@/components/GlassSelect.vue";
import ConfirmDialog from "@/components/ConfirmDialog.vue";
import { usePagination } from "@/composables/usePagination";
import { useToast } from "@/composables/useToast";

const { t } = useI18n();
const toast = useToast();

interface Credential {
  id: number;
  exchange: string;
  env: string;
  label: string;
  api_key_masked: string;
  created_at: string;
}

const items = ref<Credential[]>([]);
const { page, pageSize, total, totalPages, paged } = usePagination(items, 10);
const form = ref({
  env: "sim",
  label: "default",
  api_key: "",
  secret: "",
  passphrase: "",
});

const adding = ref(false);
const testing = ref<number | null>(null);
const confirmId = ref<number | null>(null);

async function load() {
  const r = await client.get("/credentials/");
  items.value = r.data;
}

async function add() {
  adding.value = true;
  try {
    await client.post("/credentials/", form.value);
    form.value.api_key = "";
    form.value.secret = "";
    form.value.passphrase = "";
    toast.success(t("keys.addOk"));
    await load();
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t("keys.addFail"));
  } finally {
    adding.value = false;
  }
}

async function test(id: number) {
  testing.value = id;
  try {
    const r = await client.post(`/credentials/${id}/test/`);
    if (r.data.detail === "OK") toast.success(t("keys.testOk"));
    else toast.info(r.data.detail);
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t("keys.testFail"));
  } finally {
    testing.value = null;
  }
}

async function confirmRemove() {
  const id = confirmId.value;
  confirmId.value = null;
  if (id == null) return;
  await client.delete(`/credentials/${id}/`);
  await load();
}

const envOptions = computed(() => [
  { label: t("keys.sim"), value: "sim" },
  { label: t("keys.live"), value: "live" },
]);

onMounted(load);
</script>

<template>
  <div class="wrap">
    <div class="glass panel">
      <h2>{{ $t("keys.title") }}</h2>
      <p class="hint">{{ $t("keys.secretHint") }}</p>
      <div class="form">
        <GlassSelect v-model="form.env" :options="envOptions" />
        <input class="input" v-model="form.label" :placeholder="$t('keys.label')" />
        <input class="input" v-model="form.api_key" :placeholder="$t('keys.apiKey')" />
        <input
          class="input"
          v-model="form.secret"
          type="password"
          :placeholder="$t('keys.secret')"
        />
        <input
          class="input"
          v-model="form.passphrase"
          type="password"
          :placeholder="$t('keys.passphrase')"
        />
        <button class="btn" :disabled="adding" @click="add">
          {{ adding ? $t("keys.verifying") : $t("keys.add") }}
        </button>
      </div>
    </div>

    <div class="glass panel">
      <p v-if="total === 0" class="hint">{{ $t("keys.empty") }}</p>
      <table v-else class="tbl">
        <thead>
          <tr>
            <th>{{ $t("keys.env") }}</th>
            <th>{{ $t("keys.label") }}</th>
            <th>{{ $t("keys.apiKey") }}</th>
            <th>{{ $t("keys.created") }}</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="it in paged" :key="it.id">
            <td>{{ it.env === "sim" ? $t("keys.sim") : $t("keys.live") }}</td>
            <td>{{ it.label }}</td>
            <td class="mono">{{ it.api_key_masked }}</td>
            <td>{{ new Date(it.created_at).toLocaleString() }}</td>
            <td class="actions">
              <button
                class="btn btn-ghost sm"
                :disabled="testing === it.id"
                @click="test(it.id)"
              >
                {{ testing === it.id ? $t("keys.testing") : $t("keys.test") }}
              </button>
              <button class="btn btn-ghost sm" @click="confirmId = it.id">
                {{ $t("keys.delete") }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <Pagination
        v-if="total > 0"
        v-model:page="page"
        v-model:pageSize="pageSize"
        :total="total"
        :totalPages="totalPages"
      />
    </div>

    <ConfirmDialog
      :open="confirmId !== null"
      :title="$t('keys.deleteTitle')"
      :message="$t('keys.deleteConfirm')"
      danger
      @confirm="confirmRemove"
      @cancel="confirmId = null"
    />
  </div>
</template>

<style scoped>
.wrap {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.panel {
  padding: 24px;
}
h2 {
  margin: 0 0 6px;
}
.hint {
  color: var(--fg-dim);
  font-size: 13px;
  margin: 0 0 16px;
}
.form {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px;
  align-items: center;
}
.tbl {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}
.tbl th,
.tbl td {
  text-align: left;
  padding: 10px 8px;
  border-bottom: 1px solid var(--glass-border);
}
.tbl th {
  color: var(--fg-dim);
  font-weight: 600;
}
.actions {
  display: flex;
  gap: 8px;
}
.mono {
  font-family: ui-monospace, "SF Mono", monospace;
}
</style>
