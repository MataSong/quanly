<script setup lang="ts">
const props = defineProps<{
  modelValue: number | string
  step?: number
  min?: number
  max?: number
  placeholder?: string
}>()
const emit = defineEmits<{ 'update:modelValue': [number] }>()

function clamp(v: number): number {
  if (props.min != null && v < props.min) v = props.min
  if (props.max != null && v > props.max) v = props.max
  return v
}
function bump(dir: number) {
  const step = props.step ?? 1
  const cur = Number(props.modelValue) || 0
  emit('update:modelValue', clamp(cur + dir * step))
}
function onInput(e: Event) {
  const v = Number((e.target as HTMLInputElement).value)
  emit('update:modelValue', Number.isNaN(v) ? 0 : v)
}
</script>

<template>
  <div class="glass-number">
    <button type="button" class="gn-btn" @click="bump(-1)">−</button>
    <input
      class="gn-input" type="text" inputmode="decimal"
      :value="modelValue" :placeholder="placeholder" @input="onInput"
    />
    <button type="button" class="gn-btn" @click="bump(1)">+</button>
  </div>
</template>

<style scoped>
.glass-number {
  display: inline-flex; align-items: stretch; border-radius: 10px; overflow: hidden;
  background: var(--glass-bg); border: 1px solid var(--glass-border);
  backdrop-filter: blur(12px); min-width: 160px;
}
.gn-btn {
  width: 34px; flex: none; border: none; background: transparent; color: var(--fg);
  font-size: 18px; cursor: pointer; transition: background .15s;
}
.gn-btn:hover { background: rgba(255,255,255,.1); }
.gn-input {
  flex: 1; min-width: 0; width: 100%; border: none; background: transparent; color: var(--fg);
  text-align: center; padding: 8px 6px; outline: none;
  font-variant-numeric: tabular-nums;
}
</style>
