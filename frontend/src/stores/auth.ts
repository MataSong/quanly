import { defineStore } from "pinia";
import client from "@/api/client";

interface UserInfo {
  id: number;
  username: string;
  email: string;
  locale: string;
  theme: string;
}

export const useAuth = defineStore("auth", {
  state: () => ({
    user: null as UserInfo | null,
  }),
  getters: {
    isAuthenticated: () => !!localStorage.getItem("access"),
  },
  actions: {
    async login(username: string, password: string) {
      const r = await client.post("/auth/login", { username, password });
      localStorage.setItem("access", r.data.access);
      localStorage.setItem("refresh", r.data.refresh);
      try {
        await this.fetchMe();
      } catch {
        // token 已存,登录视为成功;用户信息进入首页后再拉
      }
    },
    async register(username: string, email: string, password: string) {
      await client.post("/auth/register", { username, email, password });
    },
    async fetchMe() {
      const r = await client.get("/auth/me");
      this.user = r.data;
    },
    logout() {
      localStorage.removeItem("access");
      localStorage.removeItem("refresh");
      this.user = null;
    },
  },
});
