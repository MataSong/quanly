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
      {
        path: "market",
        meta: { perm: "page:market" },
        component: () => import("@/views/market/Market.vue"),
      },
      {
        path: "trading",
        meta: { perm: "page:trading" },
        component: () => import("@/views/trading/Trading.vue"),
      },
    ],
  },
  { path: "/:pathMatch(.*)*", redirect: "/dashboard" },
];

const router = createRouter({ history: createWebHistory(), routes });
installGuards(router);
export default router;
