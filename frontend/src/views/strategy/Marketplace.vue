<template>
  <div class="marketplace-page">
    <!-- Header -->
    <div class="page-header">
      <h2 class="page-title">{{ t("strategy.marketplace") }}</h2>
      <el-button :loading="loading" size="small" @click="load">
        {{ t("common.refresh") }}
      </el-button>
    </div>

    <!-- Filter tabs -->
    <div class="filter-row">
      <el-radio-group v-model="filter" size="small">
        <el-radio-button value="all">{{ t("strategy.filterAll") }}</el-radio-button>
        <el-radio-button value="builtin">{{ t("strategy.filterBuiltin") }}</el-radio-button>
        <el-radio-button value="user">{{ t("strategy.filterUserPublic") }}</el-radio-button>
      </el-radio-group>
    </div>

    <!-- Cards grid -->
    <div v-loading="loading" class="cards-grid">
      <el-empty v-if="!loading && filteredList.length === 0" :description="t('common.empty')" />
      <div
        v-for="item in filteredList"
        :key="item.id"
        class="strategy-card"
        @click="openDetail(item)"
      >
        <!-- Card header -->
        <div class="card-head">
          <span class="card-name">{{ item.name }}</span>
          <el-tag
            :type="isBuiltin(item) ? 'info' : 'success'"
            size="small"
            class="card-tag"
          >
            {{ isBuiltin(item) ? t("strategy.builtinTag") : t("strategy.userTag") + " · " + item.owner_username }}
          </el-tag>
        </div>

        <!-- Description -->
        <p class="card-desc" :title="item.description || ''">
          {{ item.description || "—" }}
        </p>

        <!-- Params summary -->
        <div class="card-params">
          <span
            v-for="(val, key) in displayParams(item)"
            :key="String(key)"
            class="param-chip"
          >{{ key }}: {{ val }}</span>
        </div>

        <!-- Footer stats -->
        <div class="card-footer">
          <span v-if="item.performance" class="stat">
            <el-icon><User /></el-icon>
            {{ item.performance.user_count }}
          </span>
          <span v-else class="stat stat-empty">—</span>
          <el-button
            type="primary"
            size="small"
            text
            class="use-btn"
            @click.stop="useStrategy(item)"
          >
            {{ t("strategy.useStrategy") }}
          </el-button>
        </div>
      </div>
    </div>

    <!-- Detail drawer -->
    <el-drawer
      v-model="drawerVisible"
      :title="detailItem?.name ?? ''"
      :size="isMobile ? '92%' : '480px'"
      direction="rtl"
    >
      <div v-if="detailLoading" class="detail-loading">
        <el-skeleton :rows="6" animated />
      </div>
      <template v-else-if="detailStrategy">
        <!-- Source tag -->
        <div class="detail-section">
          <el-tag :type="isBuiltin(detailStrategy) ? 'info' : 'success'" size="small">
            {{ isBuiltin(detailStrategy) ? t("strategy.builtinTag") : t("strategy.userTag") + " · " + detailStrategy.owner_username }}
          </el-tag>
        </div>

        <!-- Description -->
        <div class="detail-section">
          <div class="detail-label">{{ t("common.description") }}</div>
          <div class="detail-value">{{ detailStrategy.description || "—" }}</div>
        </div>

        <!-- Template -->
        <div class="detail-section">
          <div class="detail-label">{{ t("strategy.template") }}</div>
          <div class="detail-value">
            {{ detailStrategy.template_ref || detailStrategy.code_ref || "—" }}
          </div>
        </div>

        <!-- Params -->
        <div class="detail-section">
          <div class="detail-label">{{ t("common.name") }} / Params</div>
          <div class="param-list">
            <div
              v-for="(val, key) in (detailStrategy.params || detailStrategy.default_params || {})"
              :key="String(key)"
              class="param-row"
            >
              <span class="param-key">{{ key }}</span>
              <span class="param-val">{{ val }}</span>
            </div>
          </div>
        </div>

        <!-- Performance -->
        <div class="detail-section">
          <div class="detail-label">{{ t("strategy.referenceBacktest") }}</div>
          <template v-if="detailStrategy.performance">
            <div class="perf-grid">
              <div class="perf-item">
                <div class="perf-val">{{ detailStrategy.performance.run_count }}</div>
                <div class="perf-name">{{ t("strategy.runCount") }}</div>
              </div>
              <div class="perf-item">
                <div class="perf-val">{{ detailStrategy.performance.user_count }}</div>
                <div class="perf-name">{{ t("strategy.userCount") }}</div>
              </div>
              <div class="perf-item">
                <div class="perf-val">{{ detailStrategy.performance.order_count }}</div>
                <div class="perf-name">{{ t("strategy.orderCount") }}</div>
              </div>
            </div>
            <!-- Reference backtest metrics -->
            <template v-if="detailStrategy.performance.reference_backtest">
              <div class="backtest-metrics">
                <div
                  v-for="(val, key) in detailStrategy.performance.reference_backtest"
                  :key="String(key)"
                  class="metric-row"
                >
                  <span class="metric-key">{{ key }}</span>
                  <span class="metric-val">{{ val }}</span>
                </div>
              </div>
            </template>
          </template>
          <template v-else>
            <div class="no-perf">{{ t("strategy.noPerformance") }}</div>
          </template>
        </div>

        <!-- Use button -->
        <div class="detail-actions">
          <el-button type="primary" style="width: 100%" @click="useStrategy(detailStrategy)">
            {{ t("strategy.useStrategy") }}
          </el-button>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { User } from "@element-plus/icons-vue";
import { getMarketplace, getStrategyDetail, type Strategy } from "@/api/strategy";
import { formatApiError } from "@/utils/errors";
import { useBreakpoint } from "@/composables/useBreakpoint";

const { t } = useI18n();
const router = useRouter();
const { isMobile } = useBreakpoint();

// ── Data ──────────────────────────────────────────────────────────────────────

const list = ref<Strategy[]>([]);
const loading = ref(false);

async function load() {
  loading.value = true;
  try {
    list.value = await getMarketplace();
  } catch (e) {
    ElMessage.error(formatApiError(e, "strategy"));
  } finally {
    loading.value = false;
  }
}

// ── Filter ────────────────────────────────────────────────────────────────────

const filter = ref<"all" | "builtin" | "user">("all");

function isBuiltin(s: Strategy): boolean {
  return s.is_builtin || !s.owner_username;
}

const filteredList = computed<Strategy[]>(() => {
  if (filter.value === "builtin") return list.value.filter(isBuiltin);
  if (filter.value === "user") return list.value.filter((s) => !isBuiltin(s));
  return list.value;
});

// ── Params display ────────────────────────────────────────────────────────────

function displayParams(s: Strategy): Record<string, unknown> {
  return s.params ?? s.default_params ?? {};
}

// ── Detail drawer ─────────────────────────────────────────────────────────────

const drawerVisible = ref(false);
const detailItem = ref<Strategy | null>(null);
const detailStrategy = ref<Strategy | null>(null);
const detailLoading = ref(false);

async function openDetail(item: Strategy) {
  detailItem.value = item;
  detailStrategy.value = item; // show immediately with card data
  drawerVisible.value = true;
  detailLoading.value = true;
  try {
    detailStrategy.value = await getStrategyDetail(item.id);
  } catch (e) {
    ElMessage.error(formatApiError(e, "strategy"));
    detailStrategy.value = item; // fallback to card data
  } finally {
    detailLoading.value = false;
  }
}

// ── Use strategy → jump to /strategy with pre-filled strategyId ───────────────

function useStrategy(s: Strategy) {
  drawerVisible.value = false;
  router.push({ path: "/strategy", query: { strategyId: String(s.id) } });
}

// ── Lifecycle ─────────────────────────────────────────────────────────────────

onMounted(load);
</script>

<style scoped lang="scss">
@use "@/styles/mixins" as *;

.marketplace-page {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.page-title {
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: 600;
  color: var(--gray-800);
}

.filter-row {
  display: flex;
  align-items: center;
}

/* Cards grid — responsive auto-fill */
.cards-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: var(--space-4);

  @include mobile {
    grid-template-columns: 1fr;
  }
}

.strategy-card {
  background: #fff;
  border: 1px solid var(--gray-200);
  border-radius: var(--radius-lg);
  padding: var(--space-4);
  cursor: pointer;
  transition: box-shadow var(--duration-fast) var(--ease),
              border-color var(--duration-fast) var(--ease);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);

  &:hover {
    box-shadow: var(--shadow-md);
    border-color: var(--brand-primary);
  }
}

.card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-2);
}

.card-name {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--gray-800);
  word-break: break-word;
  flex: 1;
}

.card-tag {
  flex-shrink: 0;
}

.card-desc {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--gray-500);
  /* 2-line truncation */
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 34px;
}

.card-params {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  min-height: 22px;
}

.param-chip {
  font-size: var(--font-size-xs);
  color: var(--gray-600);
  background: var(--gray-100);
  padding: 2px 6px;
  border-radius: 4px;
}

.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: auto;
  padding-top: var(--space-2);
  border-top: 1px solid var(--gray-100);
}

.stat {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: var(--font-size-sm);
  color: var(--gray-500);
}

.stat-empty {
  color: var(--gray-300);
}

.use-btn {
  padding: 0;
}

/* Drawer detail */
.detail-loading {
  padding: var(--space-4);
}

.detail-section {
  margin-bottom: var(--space-5);
}

.detail-label {
  font-size: var(--font-size-sm);
  color: var(--gray-500);
  margin-bottom: var(--space-1);
  text-transform: uppercase;
  letter-spacing: 0.4px;
}

.detail-value {
  font-size: var(--font-size-base);
  color: var(--gray-800);
  line-height: 1.5;
}

.param-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.param-row {
  display: flex;
  justify-content: space-between;
  font-size: var(--font-size-sm);
  padding: 3px 0;
  border-bottom: 1px solid var(--gray-100);
}
.param-row:last-child { border-bottom: none; }

.param-key {
  color: var(--gray-600);
  font-weight: 500;
}

.param-val {
  color: var(--gray-800);
  font-variant-numeric: tabular-nums;
}

.perf-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}

.perf-item {
  text-align: center;
  padding: var(--space-3);
  background: var(--gray-50);
  border-radius: var(--radius-md);
}

.perf-val {
  font-size: var(--font-size-xl);
  font-weight: 700;
  color: var(--brand-primary);
}

.perf-name {
  font-size: var(--font-size-xs);
  color: var(--gray-500);
  margin-top: 2px;
}

.backtest-metrics {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.metric-row {
  display: flex;
  justify-content: space-between;
  font-size: var(--font-size-sm);
  padding: 3px 0;
  border-bottom: 1px solid var(--gray-100);
}
.metric-row:last-child { border-bottom: none; }

.metric-key {
  color: var(--gray-600);
}

.metric-val {
  color: var(--gray-800);
  font-variant-numeric: tabular-nums;
}

.no-perf {
  font-size: var(--font-size-sm);
  color: var(--gray-400);
  font-style: italic;
}

.detail-actions {
  margin-top: var(--space-6);
}
</style>
