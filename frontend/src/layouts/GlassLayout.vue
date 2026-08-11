<script setup lang="ts">
import { ref } from "vue";
import { useRouter, useRoute } from "vue-router";
import { useI18n } from "vue-i18n";
import { setLocale, type Locale } from "@/i18n";
import { useAuth } from "@/stores/auth";

const router = useRouter();
const route = useRoute();
const { locale } = useI18n();
const auth = useAuth();

const theme = ref(document.documentElement.dataset.theme || "dark");

function toggleTheme() {
  theme.value = theme.value === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = theme.value;
  localStorage.setItem("theme", theme.value);
}

function toggleLocale() {
  const next: Locale = locale.value === "zh-CN" ? "en-US" : "zh-CN";
  setLocale(next);
}

function logout() {
  auth.logout();
  router.push("/login");
}

const navItems = [
  { path: "/dashboard", key: "nav.dashboard" },
  { path: "/market/BTC-USDT", key: "nav.market" },
  { path: "/trade", key: "nav.trade" },
  { path: "/strategies", key: "nav.strategies" },
  { path: "/backtest", key: "nav.backtest" },
  { path: "/finance", key: "nav.finance" },
  { path: "/transfer", key: "nav.transfer" },
  { path: "/assets/bills", key: "nav.bills" },
  { path: "/settings/keys", key: "nav.keys" },
];

function isActive(item: { path: string }) {
  if (item.path.startsWith("/market")) return route.path.startsWith("/market");
  if (item.path === "/strategies") return route.path.startsWith("/strategies");
  return route.path === item.path;
}
</script>

<template>
  <div class="shell">
    <aside class="sidebar glass">
      <div class="brand">Quanly</div>
      <nav>
        <router-link
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          class="nav-link"
          :class="{ active: isActive(item) }"
        >
          {{ $t(item.key) }}
        </router-link>
      </nav>
    </aside>

    <div class="main">
      <header class="topbar glass">
        <span class="title">{{ $t("app.title") }}</span>
        <div class="actions">
          <button class="btn btn-ghost" @click="toggleLocale">
            {{ locale === "zh-CN" ? "EN" : "中" }}
          </button>
          <button class="btn btn-ghost" @click="toggleTheme">
            {{ theme === "dark" ? "☀︎" : "☾" }}
          </button>
          <button class="btn btn-ghost" @click="logout">{{ $t("nav.logout") }}</button>
        </div>
      </header>
      <section class="content">
        <router-view />
      </section>
    </div>
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  min-height: 100vh;
  gap: 16px;
  padding: 16px;
}
.sidebar {
  width: 220px;
  padding: 20px 14px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.brand {
  font-size: 22px;
  font-weight: 700;
  letter-spacing: 0.5px;
  padding-left: 8px;
}
nav {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.nav-link {
  padding: 10px 12px;
  border-radius: 10px;
  color: var(--fg-dim);
  text-decoration: none;
  font-size: 14px;
  font-weight: 500;
}
.nav-link:hover {
  color: var(--fg);
}
.nav-link.active {
  background: var(--glass-bg-strong);
  color: var(--fg);
}
.main {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
}
.title {
  font-weight: 600;
}
.actions {
  display: flex;
  gap: 8px;
}
.content {
  flex: 1;
}
</style>
