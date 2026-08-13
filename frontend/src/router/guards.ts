import type { Router, RouteLocationNormalized } from "vue-router";
import { useAuthStore } from "@/stores/auth";

// Return the first route the user has access to; fall back to /login.
function firstAllowed(auth: ReturnType<typeof useAuthStore>): string {
  const candidates: Array<[string, string]> = [
    ["page:dashboard", "/dashboard"],
    ["page:admin", "/admin"],
  ];
  for (const [perm, path] of candidates) {
    if (auth.hasPerm(perm)) return path;
  }
  return "/login";
}

export function installGuards(router: Router) {
  router.beforeEach((to: RouteLocationNormalized) => {
    const auth = useAuthStore();

    // Already logged in → redirect away from /login or /register
    if ((to.path === "/login" || to.path === "/register") && auth.isAuthenticated) {
      return { path: firstAllowed(auth) };
    }

    // Public pages pass through
    if (to.meta.public) return true;

    // Not authenticated → go to login
    if (!auth.isAuthenticated) {
      return { path: "/login", query: { next: to.fullPath } };
    }

    // Has perm requirement but user lacks it → go to first allowed
    const perm = to.meta.perm as string | undefined;
    if (perm && !auth.hasPerm(perm)) {
      const target = firstAllowed(auth);
      if (target === to.path) return true; // avoid self-redirect loop
      return { path: target };
    }

    return true;
  });
}
