import { createRouter, createWebHistory } from "vue-router";
import { useAuth } from "@/stores/auth";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/login", component: () => import("@/views/Login.vue") },
    { path: "/register", component: () => import("@/views/Register.vue") },
    {
      path: "/",
      component: () => import("@/layouts/GlassLayout.vue"),
      meta: { requiresAuth: true },
      children: [
        { path: "", redirect: "/dashboard" },
        { path: "dashboard", component: () => import("@/views/Dashboard.vue") },
        { path: "trade", component: () => import("@/views/Terminal.vue") },
        { path: "market/:symbol", redirect: "/trade" },
        { path: "market", redirect: "/trade" },
        { path: "strategies", redirect: "/strategies/templates" },
        { path: "strategies/templates", component: () => import("@/views/TemplateLibrary.vue") },
        { path: "strategies/tasks", component: () => import("@/views/TaskPanel.vue") },
        { path: "strategies/editor", component: () => import("@/views/StrategyEditor.vue") },
        { path: "strategies/editor/:id", component: () => import("@/views/StrategyEditor.vue") },
        { path: "strategies/:id", component: () => import("@/views/StrategyDetail.vue") },
        { path: "backtest", component: () => import("@/views/Backtest.vue") },
        { path: "transfer", component: () => import("@/views/Transfer.vue") },
        { path: "assets/bills", component: () => import("@/views/assets/Bills.vue") },
        { path: "settings/keys", component: () => import("@/views/settings/Keys.vue") },
      ],
    },
  ],
});

router.beforeEach((to) => {
  const auth = useAuth();
  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return "/login";
  }
});

export default router;
