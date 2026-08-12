<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{ modelValue: string[] }>();
const emit = defineEmits<{ (e: "update:modelValue", v: string[]): void }>();

const OPTIONS = [
  { key: "ma7", label: "MA7" },
  { key: "ma25", label: "MA25" },
  { key: "ema12", label: "EMA12" },
  { key: "boll", label: "BOLL" },
];

const selected = computed(() => props.modelValue || []);

function toggle(key: string) {
  const cur = [...selected.value];
  const i = cur.indexOf(key);
  if (i >= 0) cur.splice(i, 1);
  else cur.push(key);
  emit("update:modelValue", cur);
}
</script>

<template>
  <div class="indicators">
    <span class="lbl">{{ $t("terminal.indicators") }}</span>
    <button
      v-for="o in OPTIONS"
      :key="o.key"
      class="chip"
      :class="{ on: selected.includes(o.key) }"
      @click="toggle(o.key)"
    >
      {{ o.label }}
    </button>
  </div>
</template>

<style scoped>
.indicators {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.lbl {
  font-size: 12px;
  color: var(--fg-dim);
  margin-right: 4px;
}
.chip {
  background: transparent;
  border: 1px solid var(--glass-border);
  color: var(--fg-dim);
  padding: 3px 10px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
}
.chip.on {
  color: var(--fg);
  border-color: var(--accent, #4a9eff);
}
</style>
