import { createRouter, createWebHistory } from "vue-router";
import { installGuards } from "./guards";

const routes = [
  {
    path: "/login",
    component: () => import("@/views/login/Login.vue"),
    meta: { public: true },
  },
  {
    path: "/register",
    component: () => import("@/views/register/Register.vue"),
    meta: { public: true },
  },
  {
    path: "/",
    component: () => import("@/layouts/AppShell.vue"),
    redirect: "/dashboard",
    children: [
      {
        path: "dashboard",
        meta: { perm: "page:dashboard" },
        component: () => import("@/views/dashboard/Dashboard.vue"),
      },
      {
        path: "admin",
        meta: { perm: "page:admin" },
        component: () => import("@/views/admin/PermissionAdmin.vue"),
      },
      {
        path: "credentials",
        meta: { perm: "page:credentials" },
        component: () => import("@/views/credentials/CredentialPanel.vue"),
      },
      { path: "market", redirect: "/trade" },
      { path: "trading", redirect: "/trade" },
      {
        path: "trade",
        meta: { perm: "page:trading" },
        component: () => import("@/views/trade/TradeDesk.vue"),
      },
      {
        path: "strategy",
        meta: { perm: "page:strategy" },
        component: () => import("@/views/strategy/Strategy.vue"),
      },
      {
        path: "marketplace",
        meta: { perm: "page:strategy" },
        component: () => import("@/views/strategy/Marketplace.vue"),
      },
      {
        path: "my-strategies",
        meta: { perm: "page:strategy" },
        component: () => import("@/views/strategy/MyStrategies.vue"),
      },
      {
        path: "backtest",
        meta: { perm: "page:backtest" },
        component: () => import("@/views/backtest/Backtest.vue"),
      },
    ],
  },
  { path: "/:pathMatch(.*)*", redirect: "/dashboard" },
];

const router = createRouter({ history: createWebHistory(), routes });
installGuards(router);
export default router;
