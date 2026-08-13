<template>
  <div class="dashboard">
    <div class="page-header">
      <h1 class="page-title">{{ t("dashboard.title") }}</h1>
      <p class="page-sub">{{ t("dashboard.subtitle") }}</p>
    </div>

    <div class="welcome-banner">
      <div class="welcome-icon">
        <el-icon :size="32"><TrendCharts /></el-icon>
      </div>
      <div class="welcome-text">
        <div class="welcome-greeting">
          {{ t("dashboard.welcome", { username: auth.user?.username ?? "—" }) }}
        </div>
        <div class="welcome-hint">{{ t("dashboard.subtitle") }}</div>
      </div>
    </div>

    <div class="stat-row">
      <div class="stat-card">
        <div class="stat-value">{{ permCount }}</div>
        <div class="stat-label">
          {{ t("dashboard.permissionCount") }}
          <span v-if="t('dashboard.permissionCountUnit')">
            {{ t("dashboard.permissionCountUnit") }}
          </span>
        </div>
      </div>
      <div class="stat-card accent">
        <div class="stat-value">{{ t("dashboard.statusNormal") }}</div>
        <div class="stat-label">{{ t("dashboard.systemStatus") }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import { TrendCharts } from "@element-plus/icons-vue";
import { useAuthStore } from "@/stores/auth";

const { t } = useI18n();
const auth = useAuthStore();

const permCount = computed(() => {
  if (!auth.user) return 0;
  if (auth.user.is_superuser) return "∞";
  return auth.user.permissions.length;
});
</script>

<style scoped>
.dashboard {
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}

.page-header { }
.page-title {
  margin: 0 0 var(--space-1);
  font-size: var(--font-size-2xl);
  font-weight: 700;
  color: var(--gray-800);
}
.page-sub {
  margin: 0;
  font-size: var(--font-size-base);
  color: var(--gray-500);
}

.welcome-banner {
  display: flex;
  align-items: center;
  gap: var(--space-5);
  padding: var(--space-6);
  background: linear-gradient(135deg, rgba(99, 91, 255, 0.08) 0%, rgba(0, 212, 255, 0.06) 100%);
  border: 1px solid rgba(99, 91, 255, 0.15);
  border-radius: var(--radius-xl);
}

.welcome-icon {
  width: 56px;
  height: 56px;
  border-radius: var(--radius-lg);
  background: var(--brand-gradient);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  flex: none;
}

.welcome-greeting {
  font-size: var(--font-size-xl);
  font-weight: 600;
  color: var(--gray-800);
}
.welcome-hint {
  font-size: var(--font-size-base);
  color: var(--gray-500);
  margin-top: 4px;
}

.stat-row {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: var(--space-4);
}

.stat-card {
  background: #fff;
  border: 1px solid var(--gray-200);
  border-radius: var(--radius-lg);
  padding: var(--space-5) var(--space-6);
  box-shadow: var(--shadow-xs);
}
.stat-card.accent {
  border-color: rgba(34, 197, 94, 0.3);
  background: var(--color-success-bg);
}

.stat-value {
  font-size: var(--font-size-2xl);
  font-weight: 700;
  color: var(--brand-primary);
  margin-bottom: var(--space-1);
}
.stat-card.accent .stat-value {
  color: var(--color-success);
}
.stat-label {
  font-size: var(--font-size-sm);
  color: var(--gray-500);
}
</style>
