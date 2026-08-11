#!/usr/bin/env bash
# 一键热更新:git pull → 备份 → 按 git diff 路径只重建变更镜像 → 按需迁移。
set -euo pipefail
cd "$(dirname "$0")/.."
source deploy/lib.sh
source deploy/preflight.sh

ENV_FILE=".env.prod"
[ -f "$ENV_FILE" ] || die "缺少 $ENV_FILE,请先运行:./quanly init"
load_mode
preflight

# 1) 记录旧 SHA(用于 diff),再 pull
IS_GIT=0
OLD_SHA=""; NEW_SHA=""
if [ -d .git ] && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  IS_GIT=1
  OLD_SHA="$(git rev-parse HEAD 2>/dev/null || echo '')"
  say "拉取最新代码…"
  git pull --ff-only || warn "git pull 失败(可能有本地改动),继续用当前代码构建。"
  NEW_SHA="$(git rev-parse HEAD 2>/dev/null || echo '')"
else
  warn "非 git 仓库,无法检测变更,将执行全量重建。"
fi

# 2) 更新前备份(失败仅警告)
say "更新前备份…"
bash deploy/backup.sh || warn "备份失败/跳过,继续更新。"

# 3) 变更检测
REBUILD_FRONTEND=0
REBUILD_BACKEND=0
RESTART_EDGE=0
if [ "$IS_GIT" = "1" ] && [ -n "$OLD_SHA" ] && [ "$OLD_SHA" != "$NEW_SHA" ]; then
  CHANGED="$(git diff --name-only "$OLD_SHA" "$NEW_SHA")"
  echo "$CHANGED" | grep -q '^frontend/' && REBUILD_FRONTEND=1
  echo "$CHANGED" | grep -qE '^backend/' && REBUILD_BACKEND=1
  echo "$CHANGED" | grep -qE '^(docker-compose.*\.yml|Caddyfile|nginx/)' && RESTART_EDGE=1
  if [ "$REBUILD_FRONTEND" = "0" ] && [ "$REBUILD_BACKEND" = "0" ] && [ "$RESTART_EDGE" = "0" ]; then
    say "无相关代码变更,无需重建。"
    docker image prune -f >/dev/null 2>&1 || true
    say "热更新完成(无改动)。"
    exit 0
  fi
else
  # 非 git 或无 diff → 全量重建(稳妥)
  REBUILD_FRONTEND=1; REBUILD_BACKEND=1; RESTART_EDGE=1
fi

# 4) 后端相关:先起基础设施 + 迁移
BACKEND_SERVICES="backend ws market-collector celery-worker celery-beat private-ws"
if [ "$REBUILD_BACKEND" = "1" ]; then
  say "启动基础设施并迁移…"
  compose up -d postgres redis influxdb
  until compose exec -T postgres pg_isready -U quanly >/dev/null 2>&1; do sleep 2; done
  compose run --rm backend python manage.py migrate --noinput
fi

# 5) 前端重建
if [ "$REBUILD_FRONTEND" = "1" ]; then
  say "重建前端静态资源…"
  compose up -d --no-deps --build frontend
fi

# 6) 后端系列重建
if [ "$REBUILD_BACKEND" = "1" ]; then
  say "滚动重建后端服务…"
  compose up -d --no-deps --build $BACKEND_SERVICES
  compose exec -T backend python manage.py collectstatic --noinput || true
  # collectstatic 重写静态哈希清单后,重启 backend 让 WhiteNoise 重新扫描,避免 worker 因旧哈希缺失崩溃。
  compose restart backend
  # backend 被 recreate 后容器 IP 变化,nginx 若缓存旧上游地址会对所有 /api 返回 502;重启 nginx 刷新 DNS 解析。
  RESTART_EDGE=1
fi

# 7) 边缘代理重载
if [ "$RESTART_EDGE" = "1" ]; then
  say "重载边缘代理…"
  if [ "$QUANLY_MODE" = "server" ]; then
    compose up -d --no-deps caddy nginx
  else
    compose up -d --no-deps nginx
  fi
  # 确保 nginx 重新解析后端上游(仅 up 在配置未变时可能不重启,故显式 restart)。
  compose restart nginx
fi

# 8) 清理
docker image prune -f >/dev/null 2>&1 || true
say "热更新完成。"
