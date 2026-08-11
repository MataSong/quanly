#!/usr/bin/env bash
# 一键初始化:双模式(本地/服务器)。首次生成 .env.prod(随机密钥),
# 已存在则保留不覆盖。拉起服务、迁移、收集静态资源。
set -euo pipefail
cd "$(dirname "$0")/.."
source deploy/lib.sh
source deploy/preflight.sh   # 载入 preflight 函数

ENV_FILE=".env.prod"

# 1) 环境自检(端口检查依赖 QUANLY_MODE,若已有配置则先读)
[ -f "$ENV_FILE" ] && export QUANLY_MODE="$(env_get QUANLY_MODE)"
preflight

# 2) 生成或保留 .env.prod
if [ -f "$ENV_FILE" ]; then
  export QUANLY_MODE="${QUANLY_MODE:-local}"
  say "检测到已有 $ENV_FILE,保留不覆盖(模式:$QUANLY_MODE)。"
else
  say "首次初始化:生成 $ENV_FILE"
  echo "请选择部署模式:"
  echo "  [1] 本地(localhost,免域名/证书)"
  echo "  [2] 服务器(带域名,自动 HTTPS)"
  read -rp "输入 1 或 2 [默认 1]: " mode_choice
  mode_choice="${mode_choice:-1}"

  if [ "$mode_choice" = "2" ]; then
    QUANLY_MODE="server"
    read -rp "域名(如 trade.example.com): " DOMAIN
    read -rp "证书邮箱(Let's Encrypt): " ACME_EMAIL
    ALLOWED_HOSTS="$DOMAIN"
  else
    QUANLY_MODE="local"
    DOMAIN="localhost"
    ACME_EMAIL=""
    ALLOWED_HOSTS="localhost,127.0.0.1"
  fi

  DB_PASSWORD="$(gen_hex)"
  INFLUX_PASSWORD="$(gen_hex)"
  INFLUX_TOKEN="$(gen_hex)$(gen_hex)"
  DJANGO_SECRET_KEY="$(gen_secret)"
  SECRET_ENCRYPTION_KEY="$(gen_fernet)"

  cat > "$ENV_FILE" <<EOF
# 由 deploy/init.sh 自动生成于 $(date '+%Y-%m-%d %H:%M:%S')
QUANLY_MODE=$QUANLY_MODE
DOMAIN=$DOMAIN
ACME_EMAIL=$ACME_EMAIL

DJANGO_SECRET_KEY=$DJANGO_SECRET_KEY
DJANGO_DEBUG=0
ALLOWED_HOSTS=$ALLOWED_HOSTS
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
  export QUANLY_MODE
  say "已生成 $ENV_FILE(密钥随机,请妥善备份该文件)。"
fi

# 3) 构建并拉起(--remove-orphans:清理模式切换后残留的旧容器,如 caddy)
say "构建并拉起全部服务(模式:$QUANLY_MODE)…"
compose up -d --build --remove-orphans

# 4) 等数据库就绪
say "等待数据库就绪…"
until compose exec -T postgres pg_isready -U quanly >/dev/null 2>&1; do
  sleep 2; echo "  等待 postgres…"
done

# 5) 迁移 + 静态资源
say "数据库迁移…"
compose exec -T backend python manage.py migrate --noinput

say "收集静态资源…"
compose exec -T backend python manage.py collectstatic --noinput || true

# collectstatic 会重写带哈希的静态清单,而 backend 的 WhiteNoise 在启动时已扫描过旧清单,
# 若不重启会因找不到旧哈希文件而 worker 崩溃(exit 3)。重启让其重新扫描最终产物。
say "重启后端以加载最新静态资源…"
compose restart backend

# 6) 完成提示
if [ "$QUANLY_MODE" = "server" ]; then
  server_domain="$(env_get DOMAIN)"
  say "完成!访问 https://$server_domain"
  say "提示:Caddy 首次申请证书需 1-2 分钟;确保域名已解析到本机且 80/443 开放。"
else
  say "完成!访问 http://localhost:8080"
fi
say "下一步:登录后到「API 密钥」页填写你的 OKX Key/Secret/Passphrase。"
