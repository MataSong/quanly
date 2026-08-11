<script setup lang="ts">
defineProps<{ size?: number; label?: string }>();
</script>

<template>
  <div class="spinner-wrap">
    <span
      class="spinner"
      :style="{ width: (size ?? 24) + 'px', height: (size ?? 24) + 'px' }"
    />
    <span v-if="label" class="spinner-label">{{ label }}</span>
  </div>
</template>

<style scoped>
.spinner-wrap {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.spinner {
  display: inline-block;
  border-radius: 50%;
  border: 2px solid var(--glass-border);
  border-top-color: var(--accent);
  animation: spin 0.7s linear infinite;
}
.spinner-label {
  color: var(--fg);
  opacity: 0.8;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
