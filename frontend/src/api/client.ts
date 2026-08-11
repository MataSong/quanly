import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";
import { useToast } from "@/composables/useToast";
import i18n from "@/i18n";

const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || "/api",
});

function notifyError(error: AxiosError) {
  const data = error.response?.data as any;
  const fallback = (i18n.global.t as any)("common.requestFailed");
  const msg = data?.detail || data?.msg || error.message || fallback;
  useToast().error(String(msg));
}

client.interceptors.request.use((config) => {
  const token = localStorage.getItem("access");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  // 传递界面语言,后端据此返回对应语言的业务错误信息
  const locale = (i18n.global.locale as any).value ?? i18n.global.locale;
  config.headers["Accept-Language"] = locale === "en-US" ? "en" : "zh-hans";
  return config;
});

function redirectToLogin() {
  localStorage.removeItem("access");
  localStorage.removeItem("refresh");
  if (!location.pathname.startsWith("/login")) {
    location.href = "/login";
  }
}

// 401 时用 refresh token 换新 access,自动重试原请求;refresh 也失效则回登录页。
client.interceptors.response.use(
  (resp) => resp,
  async (error: AxiosError) => {
    const original = error.config as InternalAxiosRequestConfig & {
      _retry?: boolean;
    };
    const isAuthCall = original?.url?.includes("/auth/");

    if (error.response?.status !== 401 || original?._retry || isAuthCall) {
      notifyError(error);
      return Promise.reject(error);
    }

    const refresh = localStorage.getItem("refresh");
    if (!refresh) {
      redirectToLogin();
      return Promise.reject(error);
    }

    try {
      original._retry = true;
      const r = await axios.post(
        (import.meta.env.VITE_API_BASE || "/api") + "/auth/refresh",
        { refresh }
      );
      localStorage.setItem("access", r.data.access);
      original.headers.Authorization = `Bearer ${r.data.access}`;
      return client(original);
    } catch (e) {
      redirectToLogin();
      return Promise.reject(e);
    }
  }
);

export default client;
