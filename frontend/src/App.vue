<script setup lang="ts">
import { useToast } from "@/composables/useToast";

const { toasts } = useToast();
</script>

<template>
  <router-view />
  <div class="toast-stack">
    <transition-group name="toast">
      <div
        v-for="t in toasts"
        :key="t.id"
        class="toast glass"
        :class="'toast-' + t.type"
      >
        {{ t.text }}
      </div>
    </transition-group>
  </div>
</template>

<style scoped>
.toast-stack {
  position: fixed;
  top: 20px;
  right: 20px;
  z-index: 1000;
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-width: 360px;
}
.toast {
  padding: 12px 16px;
  border-radius: 12px;
  color: var(--fg);
  font-size: 13px;
  border: 1px solid var(--glass-border);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.25);
  backdrop-filter: blur(20px);
}
.toast-error {
  border-color: #ff453a;
}
.toast-success {
  border-color: #30d158;
}
.toast-enter-active,
.toast-leave-active {
  transition: opacity 0.2s, transform 0.2s;
}
.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateX(20px);
}
</style>
