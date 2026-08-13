<template>
  <div class="locale-switcher" :class="variant">
    <button
      type="button"
      :class="{ active: localeStore.current === 'zh-CN' }"
      @click="localeStore.setLocale('zh-CN')"
    >
      中文
    </button>
    <span class="divider">/</span>
    <button
      type="button"
      :class="{ active: localeStore.current === 'en-US' }"
      @click="localeStore.setLocale('en-US')"
    >
      EN
    </button>
  </div>
</template>

<script setup lang="ts">
import { useLocaleStore } from "@/stores/locale";

withDefaults(defineProps<{ variant?: "glass" | "default" }>(), {
  variant: "default",
});

const localeStore = useLocaleStore();
</script>

<style scoped>
.locale-switcher {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 13px;
  user-select: none;
}
.locale-switcher button {
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 13px;
  color: inherit;
  opacity: 0.7;
  transition: opacity 0.15s, color 0.15s;
}
.locale-switcher button:hover { opacity: 1; }
.locale-switcher button.active {
  opacity: 1;
  font-weight: 600;
}
.divider { opacity: 0.4; }

/* default variant: subtle chip for main app header */
.locale-switcher.default {
  background: rgba(255, 255, 255, 0.1);
  color: rgba(255, 255, 255, 0.85);
}
.locale-switcher.default button.active { color: #fff; }

/* glass variant: for login page */
.locale-switcher.glass {
  background: rgba(255, 255, 255, 0.15);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.25);
  color: rgba(255, 255, 255, 0.85);
}
.locale-switcher.glass button.active { color: #fff; }

@supports not (backdrop-filter: blur(1px)) {
  .locale-switcher.glass { background: rgba(255, 255, 255, 0.35); }
}
</style>
