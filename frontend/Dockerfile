# ---- 构建阶段 ----
# 使用 node:18-alpine（node:20 中 npm 10.8.2 存在 "Exit handler never called" bug）
FROM node:18-alpine AS builder

WORKDIR /app

# 先拷贝 package*.json，利用 layer 缓存
COPY package*.json ./

# 用淘宝镜像安装依赖（npm 官方源在国内不稳定）
RUN npm install --registry=https://registry.npmmirror.com

# 拷贝源码
COPY . .

# 构建生产产物（通过 npx 显式调用，避免 PATH 问题）
RUN node_modules/.bin/vue-tsc -b && node_modules/.bin/vite build

# ---- 生产阶段：nginx 托管 ----
FROM nginx:1.25-alpine

# 删除默认站点
RUN rm /etc/nginx/conf.d/default.conf

# 拷贝前端构建产物到 nginx 根目录
COPY --from=builder /app/dist /usr/share/nginx/html

# nginx 配置由 docker-compose 通过 volume 挂载（nginx/default.conf），
# 若单独运行此镜像可提供一个简单默认 conf。
# 此处不复制 nginx 配置，由 compose 统一控制。

EXPOSE 80
