<script setup lang="ts">
defineProps<{ modelValue: boolean; label?: string }>()
const emit = defineEmits<{ 'update:modelValue': [boolean] }>()
</script>

<template>
  <label class="glass-checkbox" @click="emit('update:modelValue', !modelValue)">
    <span class="gc-box" :class="{ checked: modelValue }">
      <span v-if="modelValue" class="gc-tick">✓</span>
    </span>
    <span v-if="label" class="gc-label">{{ label }}</span>
  </label>
</template>

<style scoped>
.glass-checkbox { display: inline-flex; align-items: center; gap: 8px; cursor: pointer; user-select: none; }
.gc-box {
  width: 20px; height: 20px; border-radius: 6px; display: flex; align-items: center;
  justify-content: center; background: var(--glass-bg); border: 1px solid var(--glass-border);
  transition: background .15s, border-color .15s;
}
.gc-box.checked { background: var(--accent); border-color: var(--accent); }
.gc-tick { color: #fff; font-size: 13px; line-height: 1; }
.gc-label { color: var(--fg); }
</style>
