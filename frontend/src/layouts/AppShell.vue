<template>
  <div class="app-shell" :class="{ 'sidebar-collapsed': collapsed }">
    <!-- Topbar -->
    <header class="topbar">
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

    <!-- Sidebar -->
    <aside class="sidebar" :class="{ collapsed }">
      <div class="nav-groups">
        <div class="group" v-if="navItems.length">
          <el-tooltip
            v-for="item in navItems"
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

        <!-- Admin sub-navigation (visible when on /admin/* and not collapsed) -->
        <div class="group sub-group" v-if="isAdminRoute && adminSubItems.length && !collapsed">
          <div class="group-label">{{ t("layout.nav.admin") }}</div>
          <router-link
            v-for="sub in adminSubItems"
            :key="sub.to"
            class="item sub-item"
            :to="sub.to"
            active-class="active"
          >
            <el-icon><component :is="sub.icon" /></el-icon>
            <span>{{ sub.label }}</span>
          </router-link>
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
import { useRouter, useRoute } from "vue-router";
import {
  ArrowDown,
  Expand,
  Fold,
  Grid,
  Key,
  Setting,
  User,
  UserFilled,
} from "@element-plus/icons-vue";
import { useI18n } from "vue-i18n";
import { useAuthStore } from "@/stores/auth";
import BrandLogo from "@/components/BrandLogo.vue";
import LocaleSwitcher from "@/components/LocaleSwitcher.vue";

const { t } = useI18n();
const auth = useAuthStore();
const router = useRouter();
const route = useRoute();

const SIDEBAR_KEY = "quanly.sidebar_collapsed";
const collapsed = ref(localStorage.getItem(SIDEBAR_KEY) === "1");

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

const navItems = computed<NavItem[]>(() =>
  (
    [
      { to: "/dashboard", icon: Grid, label: t("layout.nav.dashboard"), perm: "page:dashboard" },
      { to: "/admin/users", icon: Setting, label: t("layout.nav.admin"), perm: "page:admin" },
    ] as NavItem[]
  ).filter((i) => auth.hasPerm(i.perm)),
);

const isAdminRoute = computed(() => route.path.startsWith("/admin"));

const adminSubItems = computed<NavItem[]>(() => {
  if (!auth.hasPerm("page:admin")) return [];
  return [
    { to: "/admin/users", icon: UserFilled, label: t("layout.nav.users"), perm: "page:admin" },
    { to: "/admin/roles", icon: User, label: t("layout.nav.roles"), perm: "page:admin" },
    { to: "/admin/permissions", icon: Key, label: t("admin.permissions.title"), perm: "page:admin" },
  ];
});

async function signOut() {
  await auth.logout();
  router.replace("/login");
}
</script>

<style scoped>
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

.sub-group {
  border-top: 1px solid var(--gray-100);
  padding-top: var(--space-3);
  margin-top: var(--space-1);
}

.group-label {
  font-size: var(--font-size-xs);
  color: var(--gray-400);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 0 var(--space-3) var(--space-1);
}

.sub-item {
  padding-left: calc(var(--space-3) + 12px);
  font-size: var(--font-size-sm);
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
</style>
