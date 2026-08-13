<template>
  <!-- Task 8/9 will replace this with <router-view /> -->
  <div class="app-placeholder">
    <BrandLogo :size="48" />
    <h1>quanly</h1>
    <p>量化交易平台 — 前端骨架已就绪</p>
  </div>
</template>

<script setup lang="ts">
import BrandLogo from "@/components/BrandLogo.vue";
</script>

<style scoped>
.app-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100vh;
  gap: var(--space-4);
  color: var(--color-text);
}

h1 {
  font-size: var(--font-size-3xl);
  font-weight: 700;
  background: var(--brand-gradient);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  margin: 0;
}

p {
  color: var(--color-text-muted);
  margin: 0;
}
</style>
