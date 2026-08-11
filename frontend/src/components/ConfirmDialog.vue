<script setup lang="ts">
import { useI18n } from "vue-i18n";

defineProps<{
  open: boolean;
  title?: string;
  message?: string;
  danger?: boolean;
}>();
const emit = defineEmits<{ confirm: []; cancel: [] }>();
const { t } = useI18n();
</script>

<template>
  <Teleport to="body">
    <transition name="cd-fade">
      <div v-if="open" class="cd-mask" @click.self="emit('cancel')">
        <div class="glass cd-box">
          <h3 class="cd-title">{{ title ?? t("common.confirm") }}</h3>
          <p class="cd-msg">{{ message }}</p>
          <div class="cd-actions">
            <button class="btn btn-ghost" @click="emit('cancel')">
              {{ t("common.cancel") }}
            </button>
            <button
              class="btn"
              :class="{ 'btn-danger': danger }"
              @click="emit('confirm')"
            >
              {{ t("common.confirm") }}
            </button>
          </div>
        </div>
      </div>
    </transition>
  </Teleport>
</template>

<style scoped>
.cd-mask {
  position: fixed;
  inset: 0;
  z-index: 10000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(4px);
}
.cd-box {
  width: min(90vw, 380px);
  padding: 24px;
  border-radius: 16px;
}
.cd-title {
  margin: 0 0 10px;
  font-size: 17px;
}
.cd-msg {
  margin: 0 0 20px;
  color: var(--fg-dim);
  font-size: 14px;
  line-height: 1.5;
}
.cd-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
.btn-danger {
  background: #ff453a;
  border-color: #ff453a;
  color: #fff;
}
.cd-fade-enter-active,
.cd-fade-leave-active {
  transition: opacity 0.18s;
}
.cd-fade-enter-from,
.cd-fade-leave-to {
  opacity: 0;
}
</style>
