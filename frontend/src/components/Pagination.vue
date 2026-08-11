<script setup lang="ts">
import { computed } from "vue";
import { PAGE_SIZE_OPTIONS } from "@/composables/usePagination";
import GlassSelect from "@/components/GlassSelect.vue";

const props = defineProps<{
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
}>();

const emit = defineEmits<{
  (e: "update:page", v: number): void;
  (e: "update:pageSize", v: number): void;
}>();

const rangeText = computed(() => {
  if (props.total === 0) return "0";
  const start = (props.page - 1) * props.pageSize + 1;
  const end = Math.min(props.page * props.pageSize, props.total);
  return `${start}-${end} / ${props.total}`;
});

// 可点击页码,带省略号:1 … 4 5 [6] 7 8 … 20
const pages = computed<(number | "...")[]>(() => {
  const tp = props.totalPages;
  const cur = props.page;
  if (tp <= 7) return Array.from({ length: tp }, (_, i) => i + 1);
  const out: (number | "...")[] = [1];
  const left = Math.max(2, cur - 1);
  const right = Math.min(tp - 1, cur + 1);
  if (left > 2) out.push("...");
  for (let i = left; i <= right; i++) out.push(i);
  if (right < tp - 1) out.push("...");
  out.push(tp);
  return out;
});

const sizeOptions = computed(() =>
  PAGE_SIZE_OPTIONS.map((n) => ({ label: String(n), value: n }))
);

function go(p: number | "...") {
  if (p !== "..." && p !== props.page) emit("update:page", p);
}

function prev() {
  if (props.page > 1) emit("update:page", props.page - 1);
}
function next() {
  if (props.page < props.totalPages) emit("update:page", props.page + 1);
}
function changeSize(v: string | number) {
  emit("update:pageSize", Number(v));
  emit("update:page", 1);
}
</script>

<template>
  <div class="pager">
    <div class="left">
      <span class="lbl">{{ $t("pager.perPage") }}</span>
      <GlassSelect
        :model-value="pageSize"
        :options="sizeOptions"
        class="size-select"
        @update:modelValue="changeSize"
      />
      <span class="range">{{ rangeText }}</span>
    </div>
    <div class="right">
      <button class="pbtn" :disabled="page <= 1" @click="prev">‹</button>
      <button
        v-for="(p, i) in pages"
        :key="i"
        class="pbtn num"
        :class="{ active: p === page, dots: p === '...' }"
        :disabled="p === '...'"
        @click="go(p)"
      >
        {{ p }}
      </button>
      <button class="pbtn" :disabled="page >= totalPages" @click="next">›</button>
    </div>
  </div>
</template>

<style scoped>
.pager {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 12px;
  flex-wrap: wrap;
  gap: 8px;
}
.left,
.right {
  display: flex;
  align-items: center;
  gap: 8px;
}
.lbl,
.range,
.pageinfo {
  font-size: 12px;
  color: var(--fg-dim);
}
.size-select {
  min-width: 72px;
}
.pbtn {
  background: transparent;
  border: 1px solid var(--glass-border);
  color: var(--fg);
  border-radius: 8px;
  width: 30px;
  height: 28px;
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
}
.pbtn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.pbtn.num {
  min-width: 30px;
  width: auto;
  padding: 0 8px;
  font-size: 13px;
}
.pbtn.num.active {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}
.pbtn.dots {
  border: none;
  opacity: 0.6;
  cursor: default;
}
</style>
