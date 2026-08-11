<script setup lang="ts">
import { computed } from 'vue'
const props = defineProps<{ modelValue: number; min?: number; max?: number; step?: number }>()
const emit = defineEmits<{ 'update:modelValue': [number] }>()
const min = computed(() => props.min ?? 1)
const max = computed(() => props.max ?? 125)
const pct = computed(() => ((props.modelValue - min.value) / (max.value - min.value)) * 100)
function onInput(e: Event) {
  emit('update:modelValue', Number((e.target as HTMLInputElement).value))
}
</script>

<template>
  <div class="glass-slider">
    <input
      type="range" class="gs-range" :min="min" :max="max" :step="step ?? 1"
      :value="modelValue" :style="{ '--pct': pct + '%' }" @input="onInput"
    />
    <span class="gs-value">{{ modelValue }}x</span>
  </div>
</template>

<style scoped>
.glass-slider { display: flex; align-items: center; gap: 12px; }
.gs-range {
  flex: 1; -webkit-appearance: none; appearance: none; height: 6px; border-radius: 6px;
  background: linear-gradient(to right, var(--accent) var(--pct), var(--glass-border) var(--pct));
  outline: none;
}
.gs-range::-webkit-slider-thumb {
  -webkit-appearance: none; width: 18px; height: 18px; border-radius: 50%;
  background: var(--accent); cursor: pointer; border: 2px solid #fff;
  box-shadow: 0 2px 6px rgba(0,0,0,.3);
}
.gs-range::-moz-range-thumb {
  width: 18px; height: 18px; border-radius: 50%; background: var(--accent);
  cursor: pointer; border: 2px solid #fff;
}
.gs-value { min-width: 44px; text-align: right; color: var(--fg); font-variant-numeric: tabular-nums; }
</style>
