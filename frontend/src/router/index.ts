import { createRouter, createWebHistory } from "vue-router";
import { installGuards } from "./guards";

const routes = [
  {
    path: "/login",
    component: () => import("@/views/login/Login.vue"),
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
        // Task 9 占位: 替换为真实 Dashboard 组件
        component: () => import("@/views/dashboard/Dashboard.vue"),
      },
      {
        path: "admin/users",
        meta: { perm: "page:admin" },
        // Task 9 占位: 替换为 Users 子页面
        component: () => import("@/views/admin/Admin.vue"),
      },
      {
        path: "admin/roles",
        meta: { perm: "page:admin" },
        // Task 9 占位: 替换为 Roles 子页面
        component: () => import("@/views/admin/Admin.vue"),
      },
      {
        path: "admin/permissions",
        meta: { perm: "page:admin" },
        // Task 9 占位: 替换为 Permissions 子页面
        component: () => import("@/views/admin/Admin.vue"),
      },
    ],
  },
  { path: "/:pathMatch(.*)*", redirect: "/dashboard" },
];

const router = createRouter({ history: createWebHistory(), routes });
installGuards(router);
export default router;
