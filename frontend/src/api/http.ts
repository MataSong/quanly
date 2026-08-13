import axios, {
  type AxiosInstance,
  type InternalAxiosRequestConfig,
} from "axios";
import { ElMessage } from "element-plus";
import { useAuthStore } from "@/stores/auth";
import { t } from "@/locales";

const http: AxiosInstance = axios.create({
  baseURL: "/api",
  timeout: 60_000,
});

let refreshInFlight: Promise<string> | null = null;

async function refreshAccess(): Promise<string> {
  const auth = useAuthStore();
  if (!auth.refresh) throw new Error("no refresh token");
  const resp = await axios.post("/api/auth/refresh/", {
    refresh: auth.refresh,
  });
  const newAccess = resp.data.access as string;
  // SimpleJWT rotate 模式下也可能返回新 refresh
  const newRefresh = (resp.data.refresh as string | undefined) ?? auth.refresh;
  auth.setTokens(newAccess, newRefresh);
  return newAccess;
}

http.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const auth = useAuthStore();
  if (auth.access) {
    config.headers.Authorization = `Bearer ${auth.access}`;
  }
  return config;
});

http.interceptors.response.use(
  (r) => r,
  async (error) => {
    const original = error.config;
    if (!original) return Promise.reject(error);
    if (
      error.response?.status === 401 &&
      !original._retry &&
      !original.url?.includes("/auth/")
    ) {
      original._retry = true;
      try {
        // 并发 401 共享同一个 in-flight refresh，避免 rotate 后第二次用已失效 token
        if (!refreshInFlight) {
          refreshInFlight = refreshAccess().finally(() => {
            refreshInFlight = null;
          });
        }
        const access = await refreshInFlight;
        original.headers.Authorization = `Bearer ${access}`;
        return http(original);
      } catch (e) {
        const auth = useAuthStore();
        auth.clear();
        window.location.href = "/login";
        return Promise.reject(e);
      }
    }
    if (
      error.response?.status === 403 &&
      error.response?.data?.code === "forbidden"
    ) {
      ElMessage.error(t("admin.noPermission"));
    }
    return Promise.reject(error);
  },
);

export default http;
