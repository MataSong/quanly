import type { Router, RouteLocationNormalized } from "vue-router";
import { useAuthStore } from "@/stores/auth";

// 按路由表顺序返回第一个用户有权限的路径；若无则返回 /login。
function firstAllowed(auth: ReturnType<typeof useAuthStore>): string {
  const candidates: Array<[string, string]> = [
    ["page:dashboard", "/dashboard"],
    ["page:admin", "/admin/users"],
  ];
  for (const [perm, path] of candidates) {
    if (auth.hasPerm(perm)) return path;
  }
  return "/login";
}

export function installGuards(router: Router) {
  router.beforeEach((to: RouteLocationNormalized) => {
    // 公开页（/login）直接放行
    if (to.meta.public) return true;

    const auth = useAuthStore();

    // 未登录：跳 /login，带 next 参数
    if (!auth.isAuthenticated) {
      return { path: "/login", query: { next: to.fullPath } };
    }

    // 已登录访问 /login → 跳首页
    if (to.path === "/login") {
      return { path: firstAllowed(auth) };
    }

    // 有 meta.perm 但无权限 → 跳第一个有权限的页
    const perm = to.meta.perm as string | undefined;
    if (perm && !auth.hasPerm(perm)) {
      const target = firstAllowed(auth);
      if (target === "/login") {
        // 所有页均无权限：注销并跳登录
        auth.clear();
        return { path: "/login" };
      }
      if (target === to.path) return true; // 避免自跳循环
      return { path: target };
    }

    return true;
  });
}
