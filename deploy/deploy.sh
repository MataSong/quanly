#!/usr/bin/env bash
# 一键部署:自动判断首次部署还是热更新。用户只需 ./quanly deploy。
#   无 .env.prod  → 首次部署:生成配置 → 构建拉起 → 迁移 → 收集静态
#   已有 .env.prod → 热更新:按当前代码全量重建(备份 → 迁移 → 重建镜像 → 刷新)
# 部署只按当前分支/工作区的代码执行,不做 git pull;拉取最新代码由人工手动完成。
# 无论线上本地,统一 nginx:8080 纯 HTTP 对外(ALLOWED_HOSTS=*,放开所有访问)。
set -euo pipefail
cd "$(dirname "$0")/.."
source deploy/lib.sh
source deploy/preflight.sh

ENV_FILE=".env.prod"

# ============================ 策略运行器镜像 ============================
# celery-worker 通过挂载 docker.sock 动态启动策略容器,镜像名固定 quanly-strategy-runner
# (与 docker-compose.yml 的 STRATEGY_RUNNER_IMAGE 一致)。它不在 compose services 里,
# 不会被 compose 自动构建,必须单独 build,否则页面启动策略会 404: pull access denied。
STRATEGY_RUNNER_IMAGE="quanly-strategy-runner"

build_strategy_runner() {
  say "构建策略运行器镜像($STRATEGY_RUNNER_IMAGE)…"
  docker build -t "$STRATEGY_RUNNER_IMAGE" ./strategy-runner
}

# ============================ 首次部署 ============================
first_deploy() {
  say "首次初始化:生成 $ENV_FILE"

  DB_PASSWORD="$(gen_hex)"
  INFLUX_PASSWORD="$(gen_hex)"
  INFLUX_TOKEN="$(gen_hex)$(gen_hex)"
  DJANGO_SECRET_KEY="$(gen_secret)"
  SECRET_ENCRYPTION_KEY="$(gen_fernet)"

  cat > "$ENV_FILE" <<EOF
# 由 deploy/deploy.sh 自动生成于 $(date '+%Y-%m-%d %H:%M:%S')
DJANGO_SECRET_KEY=$DJANGO_SECRET_KEY
DJANGO_DEBUG=0
ALLOWED_HOSTS=*
SECRET_ENCRYPTION_KEY=$SECRET_ENCRYPTION_KEY

DB_ENGINE=django.db.backends.postgresql
DB_NAME=quanly
DB_USER=quanly
DB_PASSWORD=$DB_PASSWORD
DB_HOST=postgres
DB_PORT=5432

INFLUX_USER=quanly
INFLUX_PASSWORD=$INFLUX_PASSWORD
INFLUX_ADMIN_TOKEN=$INFLUX_TOKEN
INFLUX_URL=http://influxdb:8086
INFLUX_ORG=quanly
INFLUX_BUCKET=market

REDIS_URL=redis://redis:6379/0
OKX_SYNC_INTERVAL=20
EOF
  chmod 600 "$ENV_FILE"
  say "已生成 $ENV_FILE(密钥随机,请妥善备份该文件)。"

  say "构建并拉起全部服务…"
  compose up -d --build --remove-orphans

  # 策略运行器镜像不在 compose services 里,必须单独构建,否则页面启动策略会 404。
  build_strategy_runner

  say "等待数据库就绪…"
  until compose exec -T postgres pg_isready -U quanly >/dev/null 2>&1; do
    sleep 2; echo "  等待 postgres…"
  done

  say "数据库迁移…"
  compose exec -T backend python manage.py migrate --noinput

  say "收集静态资源…"
  compose exec -T backend python manage.py collectstatic --noinput || true

  # collectstatic 重写带哈希的静态清单,而 backend 的 WhiteNoise 在启动时已扫描过旧清单,
  # 若不重启会因找不到旧哈希文件而 worker 崩溃(exit 3)。重启让其重新扫描最终产物。
  say "重启后端以加载最新静态资源…"
  compose restart backend

  say "完成!访问 http://<本机IP>:8080(局域网内其他设备同样可访问)。"
  say "下一步:登录后到「API 密钥」页填写你的 OKX Key/Secret/Passphrase。"
}

# ============================ 热更新 ============================
# 按当前代码(当前分支/工作区)全量重建。拉取最新代码由人工手动完成,部署脚本不碰 git。
hot_update() {
  # 1) 更新前备份(失败仅警告)
  say "更新前备份…"
  bash deploy/backup.sh || warn "备份失败/跳过,继续更新。"

  # 2) 后端相关:先起基础设施 + 迁移
  BACKEND_SERVICES="backend ws market-collector celery-worker celery-beat private-ws"
  say "启动基础设施并迁移…"
  compose up -d postgres redis influxdb
  until compose exec -T postgres pg_isready -U quanly >/dev/null 2>&1; do sleep 2; done
  compose run --rm backend python manage.py migrate --noinput

  # 3) 前端重建
  say "重建前端静态资源…"
  compose up -d --no-deps --build frontend

  # 4) 后端系列重建
  say "滚动重建后端服务…"
  compose up -d --no-deps --build $BACKEND_SERVICES
  compose exec -T backend python manage.py collectstatic --noinput || true
  # collectstatic 重写静态哈希清单后,重启 backend 让 WhiteNoise 重新扫描,避免 worker 因旧哈希缺失崩溃。
  compose restart backend

  # 5) 策略运行器镜像:不在 compose services,不会被自动重建,全量重建时一并重建。
  build_strategy_runner

  # 6) 边缘代理重载(nginx)
  # backend 被 recreate 后容器 IP 变化,nginx 若缓存旧上游地址会对所有 /api 返回 502;重启 nginx 刷新 DNS 解析。
  say "重载边缘代理…"
  compose up -d --no-deps nginx
  compose restart nginx

  # 7) 清理
  docker image prune -f >/dev/null 2>&1 || true
  say "热更新完成,刷新浏览器即可。"
}

# ============================ 主流程 ============================
preflight

if [ ! -f "$ENV_FILE" ]; then
  first_deploy
else
  say "检测到已有 $ENV_FILE,执行热更新。"
  hot_update
fi
