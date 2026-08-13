import { defineStore } from "pinia";
import http from "@/api/http";

export interface UserInfo {
  id: number;
  username: string;
  is_superuser: boolean;
  permissions: string[];
  auth_source: string;
}

interface State {
  access: string;
  refresh: string;
  user: UserInfo | null;
}

export const useAuthStore = defineStore("auth", {
  state: (): State => ({
    access: localStorage.getItem("quanly_access") || "",
    refresh: localStorage.getItem("quanly_refresh") || "",
    user: JSON.parse(localStorage.getItem("quanly_user") || "null"),
  }),
  getters: {
    isAuthenticated: (s) => !!s.access,
    hasPerm: (s) => (perm: string): boolean => {
      if (!s.user) return false;
      if (s.user.is_superuser) return true;
      return (s.user.permissions ?? []).includes(perm);
    },
  },
  actions: {
    setTokens(access: string, refresh: string) {
      this.access = access;
      this.refresh = refresh;
      localStorage.setItem("quanly_access", access);
      localStorage.setItem("quanly_refresh", refresh);
    },
    setUser(user: UserInfo | null) {
      this.user = user;
      localStorage.setItem("quanly_user", JSON.stringify(user));
    },
    async login(username: string, password: string) {
      const resp = await http.post<{
        access: string;
        refresh: string;
        user: UserInfo;
      }>("/auth/", { username, password });
      this.setTokens(resp.data.access, resp.data.refresh);
      this.setUser(resp.data.user);
    },
    async register(username: string, password: string, email?: string) {
      const resp = await http.post<{
        access: string;
        refresh: string;
        user: UserInfo;
      }>("/auth/register/", { username, password, ...(email ? { email } : {}) });
      this.setTokens(resp.data.access, resp.data.refresh);
      this.setUser(resp.data.user);
    },
    async logout() {
      try {
        if (this.refresh) {
          await http.post("/auth/logout/", { refresh: this.refresh });
        }
      } catch {
        // 忽略注销 API 错误，本地一定要清
      } finally {
        this.clear();
      }
    },
    async fetchMe() {
      const resp = await http.get<UserInfo>("/auth/me/");
      this.setUser(resp.data);
    },
    clear() {
      this.access = "";
      this.refresh = "";
      this.user = null;
      localStorage.removeItem("quanly_access");
      localStorage.removeItem("quanly_refresh");
      localStorage.removeItem("quanly_user");
    },
  },
});
