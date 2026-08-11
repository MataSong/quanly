<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { strategyApi } from "@/api/strategy";
import Pagination from "@/components/Pagination.vue";
import ConfirmDialog from "@/components/ConfirmDialog.vue";
import { usePagination } from "@/composables/usePagination";

const router = useRouter();
const items = ref<any[]>([]);
const { page, pageSize, total, totalPages, paged } = usePagination(items, 10);
const editing = ref<any | null>(null);
const confirmId = ref<number | null>(null);
const form = ref({ name: "", source: "" });

const TEMPLATE = `# 填空式策略:实现 on_tick(ctx),平台每隔 interval 秒调用一次。
def on_tick(ctx):
    px = ctx.price(ctx.symbol)
    ctx.log("price = %.2f" % px)
    # ctx.buy(ctx.symbol, 0.001) / ctx.sell(...)
`;

async function load() {
  const r = await strategyApi.list();
  items.value = r.data;
}

function newStrategy() {
  editing.value = { id: null };
  form.value = { name: "", source: TEMPLATE };
}

function edit(s: any) {
  editing.value = s;
  form.value = { name: s.name, source: s.source };
}

async function save() {
  if (editing.value?.id) {
    await strategyApi.update(editing.value.id, form.value.name, form.value.source);
  } else {
    await strategyApi.create(form.value.name, form.value.source);
  }
  editing.value = null;
  await load();
}

async function confirmRemove() {
  const id = confirmId.value;
  confirmId.value = null;
  if (id == null) return;
  await strategyApi.remove(id);
  await load();
}

onMounted(load);
</script>

<template>
  <div class="wrap">
    <div class="glass panel">
      <div class="head">
        <h2>{{ $t("strategy.title") }}</h2>
        <button class="btn" @click="newStrategy">{{ $t("strategy.new") }}</button>
      </div>
      <table class="tbl">
        <thead>
          <tr>
            <th>{{ $t("strategy.name") }}</th>
            <th>{{ $t("strategy.kind") }}</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in paged" :key="s.id">
            <td>{{ s.name }}</td>
            <td>{{ s.kind === "builtin" ? $t("strategy.builtin") : $t("strategy.custom") }}</td>
            <td class="actions">
              <button class="btn btn-ghost sm" @click="router.push(`/strategies/${s.id}`)">
                {{ $t("strategy.open") }}
              </button>
              <button class="btn btn-ghost sm" @click="edit(s)">{{ $t("strategy.edit") }}</button>
              <button
                v-if="s.kind !== 'builtin'"
                class="btn btn-ghost sm"
                @click="confirmId = s.id"
              >
                {{ $t("strategy.delete") }}
              </button>
            </td>
          </tr>
          <tr v-if="total === 0">
            <td colspan="3" class="empty">{{ $t("strategy.empty") }}</td>
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

    <div v-if="editing" class="glass panel">
      <h3>{{ editing.id ? $t("strategy.edit") : $t("strategy.new") }}</h3>
      <input class="input" v-model="form.name" :placeholder="$t('strategy.name')" />
      <textarea class="input code" v-model="form.source" rows="16"></textarea>
      <div class="row">
        <button class="btn" @click="save">{{ $t("strategy.save") }}</button>
        <button class="btn btn-ghost" @click="editing = null">{{ $t("common.cancel") }}</button>
      </div>
    </div>

    <ConfirmDialog
      :open="confirmId !== null"
      :title="$t('strategy.delete')"
      :message="$t('strategy.confirmDelete')"
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
  padding: 22px;
}
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
}
h2,
h3 {
  margin: 0 0 6px;
}
.tbl {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}
.tbl th,
.tbl td {
  text-align: left;
  padding: 9px 6px;
  border-bottom: 1px solid var(--glass-border);
}
.tbl th {
  color: var(--fg-dim);
  font-weight: 600;
}
.actions {
  display: flex;
  gap: 6px;
}
.sm {
  padding: 4px 10px;
  font-size: 12px;
}
.empty {
  text-align: center;
  color: var(--fg-dim);
  padding: 16px;
}
.input {
  margin-top: 10px;
}
.code {
  font-family: ui-monospace, "SF Mono", monospace;
  font-size: 13px;
  resize: vertical;
}
.row {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}
</style>
