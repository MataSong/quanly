<template>
  <div class="app-shell" :class="{ 'sidebar-collapsed': collapsed }">
    <!-- Topbar -->
    <header class="topbar">
      <button class="hamburger" @click="drawerOpen = true" :aria-label="t('layout.menu')">
        <el-icon :size="20"><Menu /></el-icon>
      </button>
      <div class="brand">
        <BrandLogo :size="30" variant="light" />
        <div class="brand-text">
          <div class="brand-title">{{ t("layout.appTitle") }}</div>
        </div>
      </div>
      <div class="spacer"></div>
      <LocaleSwitcher variant="default" />
      <el-dropdown trigger="click">
        <div class="user-chip">
          <div class="avatar">{{ initial }}</div>
          <el-icon><ArrowDown /></el-icon>
        </div>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item disabled>{{ username || "—" }}</el-dropdown-item>
            <el-dropdown-item divided @click="signOut">
              {{ t("layout.logout") }}
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </header>

    <!-- Sidebar (PC) -->
    <aside class="sidebar" :class="{ collapsed }">
      <div class="nav-groups">
        <div class="group" v-if="featureItems.length">
          <div class="group-title">{{ t("layout.groups.features") }}</div>
          <el-tooltip
            v-for="item in featureItems"
            :key="item.to"
            :content="item.label"
            placement="right"
            :disabled="!collapsed"
          >
            <router-link class="item" :to="item.to" active-class="active">
              <el-icon><component :is="item.icon" /></el-icon>
              <span>{{ item.label }}</span>
            </router-link>
          </el-tooltip>
        </div>

        <div class="group" v-if="accountItems.length">
          <div class="group-title">{{ t("layout.groups.account") }}</div>
          <el-tooltip
            v-for="item in accountItems"
            :key="item.to"
            :content="item.label"
            placement="right"
            :disabled="!collapsed"
          >
            <router-link class="item" :to="item.to" active-class="active">
              <el-icon><component :is="item.icon" /></el-icon>
              <span>{{ item.label }}</span>
            </router-link>
          </el-tooltip>
        </div>

        <div class="group" v-if="systemItems.length">
          <div class="group-title">{{ t("layout.groups.system") }}</div>
          <el-tooltip
            v-for="item in systemItems"
            :key="item.to"
            :content="item.label"
            placement="right"
            :disabled="!collapsed"
          >
            <router-link class="item" :to="item.to" active-class="active">
              <el-icon><component :is="item.icon" /></el-icon>
              <span>{{ item.label }}</span>
            </router-link>
          </el-tooltip>
        </div>
      </div>

      <div class="sidebar-bottom">
        <div class="sidebar-footer">
          <div class="footer-username">{{ username || "—" }}</div>
        </div>
        <button
          class="collapse-toggle"
          @click="toggleCollapse"
          :title="collapsed ? t('layout.expandSidebar') : t('layout.collapseSidebar')"
        >
          <el-icon><Fold v-if="!collapsed" /><Expand v-else /></el-icon>
        </button>
      </div>
    </aside>

    <!-- Sidebar (手机抽屉) -->
    <el-drawer
      v-model="drawerOpen"
      direction="ltr"
      :with-header="false"
      size="256px"
      class="mobile-drawer"
    >
      <div class="drawer-nav">
        <div class="drawer-brand">
          <BrandLogo :size="26" variant="light" />
          <span class="drawer-brand-title">{{ t("layout.appTitle") }}</span>
        </div>
        <div class="nav-groups">
          <div class="group" v-if="featureItems.length">
            <div class="group-title">{{ t("layout.groups.features") }}</div>
            <router-link
              v-for="item in featureItems"
              :key="item.to"
              class="item"
              :to="item.to"
              active-class="active"
              @click="drawerOpen = false"
            >
              <el-icon><component :is="item.icon" /></el-icon>
              <span>{{ item.label }}</span>
            </router-link>
          </div>
          <div class="group" v-if="accountItems.length">
            <div class="group-title">{{ t("layout.groups.account") }}</div>
            <router-link
              v-for="item in accountItems"
              :key="item.to"
              class="item"
              :to="item.to"
              active-class="active"
              @click="drawerOpen = false"
            >
              <el-icon><component :is="item.icon" /></el-icon>
              <span>{{ item.label }}</span>
            </router-link>
          </div>
          <div class="group" v-if="systemItems.length">
            <div class="group-title">{{ t("layout.groups.system") }}</div>
            <router-link
              v-for="item in systemItems"
              :key="item.to"
              class="item"
              :to="item.to"
              active-class="active"
              @click="drawerOpen = false"
            >
              <el-icon><component :is="item.icon" /></el-icon>
              <span>{{ item.label }}</span>
            </router-link>
          </div>
        </div>
      </div>
    </el-drawer>

    <!-- Main content -->
    <main class="main">
      <div class="main-inner">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import {
  ArrowDown,
  Cpu,
  DataLine,
  Expand,
  Fold,
  Grid,
  Key,
  Menu,
  Money,
  Setting,
  TrendCharts,
} from "@element-plus/icons-vue";
import { useI18n } from "vue-i18n";
import { useAuthStore } from "@/stores/auth";
import BrandLogo from "@/components/BrandLogo.vue";
import LocaleSwitcher from "@/components/LocaleSwitcher.vue";

const { t } = useI18n();
const auth = useAuthStore();
const router = useRouter();

const SIDEBAR_KEY = "quanly.sidebar_collapsed";
const collapsed = ref(localStorage.getItem(SIDEBAR_KEY) === "1");

// 手机抽屉开关
const drawerOpen = ref(false);

function toggleCollapse() {
  collapsed.value = !collapsed.value;
  localStorage.setItem(SIDEBAR_KEY, collapsed.value ? "1" : "0");
}

const username = computed(() => auth.user?.username ?? "");
const initial = computed(() => (auth.user?.username?.[0] ?? "?").toUpperCase());

interface NavItem {
  to: string;
  icon: unknown;
  label: string;
  perm: string;
}

const featureItems = computed<NavItem[]>(() =>
  (
    [
      { to: "/dashboard", icon: Grid, label: t("layout.nav.dashboard"), perm: "page:dashboard" },
      { to: "/market", icon: TrendCharts, label: t("layout.nav.market"), perm: "page:market" },
      { to: "/trading", icon: Money, label: t("layout.nav.trading"), perm: "page:trading" },
      { to: "/strategy", icon: Cpu, label: t("layout.nav.strategy"), perm: "page:strategy" },
      { to: "/backtest", icon: DataLine, label: t("layout.nav.backtest"), perm: "page:backtest" },
    ] as NavItem[]
  ).filter((i) => auth.hasPerm(i.perm)),
);

const accountItems = computed<NavItem[]>(() =>
  (
    [
      { to: "/credentials", icon: Key, label: t("layout.nav.credentials"), perm: "page:credentials" },
    ] as NavItem[]
  ).filter((i) => auth.hasPerm(i.perm)),
);

const systemItems = computed<NavItem[]>(() =>
  (
    [
      { to: "/admin", icon: Setting, label: t("layout.nav.admin"), perm: "page:admin" },
    ] as NavItem[]
  ).filter((i) => auth.hasPerm(i.perm)),
);

async function signOut() {
  await auth.logout();
  router.replace("/login");
}
</script>

<style scoped lang="scss">
@use "@/styles/mixins" as *;

.app-shell {
  display: grid;
  grid-template-columns: 240px 1fr;
  grid-template-rows: 56px 1fr;
  grid-template-areas:
    "top top"
    "side main";
  height: 100vh;
  overflow: hidden;
  background: var(--gray-50);
  transition: grid-template-columns var(--duration-normal) var(--ease);
}
.app-shell.sidebar-collapsed {
  grid-template-columns: 64px 1fr;
}

/* Topbar */
.topbar {
  grid-area: top;
  display: flex;
  align-items: center;
  gap: var(--space-4);
  padding: 0 var(--space-6);
  background: var(--brand-dark);
  color: #fff;
  box-shadow: var(--shadow-sm);
  z-index: 20;
}

/* 汉堡按钮:仅手机显示 */
.hamburger {
  display: none;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  margin-left: calc(var(--space-2) * -1);
  border: none;
  background: transparent;
  color: #fff;
  border-radius: var(--radius-md);
  cursor: pointer;
}
.hamburger:hover {
  background: rgba(255, 255, 255, 0.1);
}
.brand {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}
.brand-title {
  font-size: var(--font-size-lg);
  font-weight: 600;
  line-height: 1.2;
}
.spacer { flex: 1; }

.user-chip {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: 4px 8px;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background var(--duration-fast) var(--ease);
}
.user-chip:hover { background: rgba(255, 255, 255, 0.08); }

.avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #fff;
  color: var(--brand-dark);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: var(--font-size-sm);
}

/* Sidebar */
.sidebar {
  grid-area: side;
  background: #fff;
  border-right: 1px solid var(--gray-200);
  padding: var(--space-5) var(--space-3);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: transparent transparent;
}
.sidebar:hover { scrollbar-color: var(--gray-300) transparent; }
.sidebar::-webkit-scrollbar { width: 6px; }
.sidebar::-webkit-scrollbar-thumb {
  background: transparent;
  border-radius: 3px;
}
.sidebar:hover::-webkit-scrollbar-thumb { background: var(--gray-300); }

.nav-groups {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}
.group {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.group-title {
  font-size: var(--font-size-xs);
  color: var(--gray-500);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 0 12px 4px;
}

.item {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: 8px var(--space-3);
  border-radius: var(--radius-md);
  color: var(--gray-600);
  font-size: var(--font-size-md);
  text-decoration: none;
  border-left: 3px solid transparent;
  transition: background var(--duration-fast) var(--ease),
    color var(--duration-fast) var(--ease);
}
.item:hover { background: var(--gray-100); }
.item.active {
  background: rgba(99, 91, 255, 0.08);
  color: var(--brand-primary);
  border-left-color: var(--brand-primary);
  font-weight: 500;
}

/* Sidebar bottom */
.sidebar-bottom {
  margin-top: auto;
  padding-top: var(--space-4);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  padding-left: var(--space-3);
  padding-right: var(--space-3);
}
.sidebar-footer {
  font-size: var(--font-size-xs);
  color: var(--gray-400);
}
.footer-username { font-weight: 500; }

.collapse-toggle {
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border: 1px solid var(--gray-200);
  border-radius: var(--radius-md);
  background: #fff;
  color: var(--gray-500);
  cursor: pointer;
  transition: background var(--duration-fast) var(--ease),
    color var(--duration-fast) var(--ease);
}
.collapse-toggle:hover {
  background: var(--gray-100);
  color: var(--brand-primary);
}

/* Collapsed state */
.sidebar.collapsed {
  padding-left: var(--space-2);
  padding-right: var(--space-2);
}
.sidebar.collapsed .item {
  justify-content: center;
  padding-left: 0;
  padding-right: 0;
  border-left-color: transparent;
}
.sidebar.collapsed .item.active { border-left-color: transparent; }
.sidebar.collapsed .item span { display: none; }
.sidebar.collapsed .sidebar-bottom {
  justify-content: center;
  padding: var(--space-4) 0 0;
}
.sidebar.collapsed .sidebar-footer { display: none; }
.sidebar.collapsed .group-title { display: none; }

/* Main */
.main {
  grid-area: main;
  overflow-y: auto;
}
.main-inner {
  padding: var(--space-7);
  max-width: 1400px;
  width: 100%;
  margin: 0 auto;
}

/* Transitions */
.fade-enter-active,
.fade-leave-active {
  transition: opacity var(--duration-normal) var(--ease);
}
.fade-enter-from,
.fade-leave-to { opacity: 0; }

/* 手机抽屉内导航样式(复用侧边栏视觉) */
.drawer-nav {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
  padding: var(--space-4) var(--space-3);
}
.drawer-brand {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 0 var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--gray-200);
}
.drawer-brand-title {
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--gray-800);
}
.drawer-nav .item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 10px var(--space-3);
  border-radius: var(--radius-md);
  color: var(--gray-700);
  font-size: var(--font-size-base);
  text-decoration: none;
  border-left: 3px solid transparent;
}
.drawer-nav .item:hover { background: var(--gray-100); }
.drawer-nav .item.active {
  background: rgba(99, 91, 255, 0.08);
  color: var(--brand-primary);
  border-left-color: var(--brand-primary);
  font-weight: 500;
}

/* ============ 手机端(≤768px) ============ */
@include mobile {
  .app-shell,
  .app-shell.sidebar-collapsed {
    grid-template-columns: 1fr;
    grid-template-areas:
      "top"
      "main";
  }
  .hamburger { display: inline-flex; }
  .sidebar { display: none; }        /* PC 侧边栏隐藏,导航移到抽屉 */
  .topbar { padding: 0 var(--space-4); }
  .main-inner { padding: var(--space-4); }
  .brand-title { font-size: var(--font-size-base); }
}
</style>
