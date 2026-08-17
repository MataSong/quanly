import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import path from "path";

// dev API 代理目标：本机开发默认 localhost:8000；容器热重载模式(docker-compose.dev.yml)
// 通过 VITE_API_TARGET=http://backend:8000 指向 compose 网络内的后端服务。
const apiTarget = process.env.VITE_API_TARGET || "http://localhost:8000";

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": { target: apiTarget, changeOrigin: true },
      "/media": { target: apiTarget, changeOrigin: true },
      "/ws": { target: apiTarget, ws: true, changeOrigin: true },
    },
  },
});

