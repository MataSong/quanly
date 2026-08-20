<template>
  <div v-if="err" class="error-boundary">
    <el-result icon="error" :title="t('common.renderErrorTitle')" :sub-title="detail">
      <template #extra>
        <el-button type="primary" @click="onRetry">{{ t("common.retry") }}</el-button>
        <el-button @click="onReload">{{ t("common.refresh") }}</el-button>
      </template>
    </el-result>
  </div>
  <slot v-else />
</template>

<script setup lang="ts">
import { computed, onErrorCaptured, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute } from "vue-router";

const { t } = useI18n();
const route = useRoute();

const err = ref<unknown>(null);

const detail = computed(() => {
  if (!err.value) return "";
  const e = err.value as Error;
  return e?.message ?? String(err.value);
});

// 捕获子树渲染/setup 抛出的未捕获异常,阻断向上冒泡(return false),
// 只在内容区显示兜底 UI,不再拖垮整站(问题2 白屏治本)。
onErrorCaptured((e) => {
  // eslint-disable-next-line no-console
  console.error("[ErrorBoundary]", e);
  err.value = e;
  return false;
});

// 路由切换时自动清错,让新页面正常尝试渲染。
watch(
  () => route.fullPath,
  () => {
    err.value = null;
  },
);

function onRetry() {
  err.value = null;
}

function onReload() {
  window.location.reload();
}
</script>

<style scoped lang="scss">
.error-boundary {
  display: flex;
  justify-content: center;
  padding: var(--space-6, 32px);
}
</style>
