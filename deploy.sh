#!/usr/bin/env bash
# ================================================================
# quanly 傻瓜式部署脚本 deploy.sh
#
#   一行搞定:  chmod +x deploy.sh && ./deploy.sh
#
# 直接回车 = 自动模式:脚本自己判断该"首次安装 / 更新 / 重启"。
# 也可用菜单或参数:
#   ./deploy.sh              自动模式(推荐给小白)
#   ./deploy.sh menu         弹出菜单手动选
#   ./deploy.sh install      首次安装 / 全量重建
#   ./deploy.sh update       更新部署(自动判断变化,生产重建)
#   ./deploy.sh dev          开发热重载模式(改代码即生效)
#   ./deploy.sh restart      重启全部(不重建)
#   ./deploy.sh restart-backend   仅重启后端(dev 改 .py 后用)
#   ./deploy.sh restart-worker    仅重启 celery worker
#   ./deploy.sh status       查看容器状态
#   ./deploy.sh logs         跟踪日志
#   ./deploy.sh stop         停止全部
#   ./deploy.sh reset        停止并删除容器(保留数据)
# ================================================================
set -euo pipefail

# --- 定位到脚本所在目录,保证任意路径调用都对 ---
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- 颜色输出 ---
if [ -t 1 ]; then
  C_RESET='\033[0m'; C_RED='\033[31m'; C_GRN='\033[32m'; C_YLW='\033[33m'; C_CYN='\033[36m'; C_BLD='\033[1m'
else
  C_RESET=''; C_RED=''; C_GRN=''; C_YLW=''; C_CYN=''; C_BLD=''
fi
info()  { printf "${C_CYN}➤${C_RESET} %s\n" "$*"; }
ok()    { printf "${C_GRN}✅ %s${C_RESET}\n" "$*"; }
warn()  { printf "${C_YLW}⚠️  %s${C_RESET}\n" "$*"; }
err()   { printf "${C_RED}❌ %s${C_RESET}\n" "$*" >&2; }
title() { printf "\n${C_BLD}${C_CYN}== %s ==${C_RESET}\n" "$*"; }

ENV_FILE=".env"
STATE_FILE=".deploy_state"
COMPOSE_DEV="docker-compose.dev.yml"

# ================================================================
# A. 前置检查
# ================================================================
check_prereq() {
  if ! command -v docker >/dev/null 2>&1; then
    err "未检测到 docker。请先安装 Docker Desktop:https://www.docker.com/products/docker-desktop/"
    exit 1
  fi
  if ! docker compose version >/dev/null 2>&1; then
    err "未检测到 docker compose(v2)。请升级 Docker Desktop 或安装 compose 插件。"
    exit 1
  fi
  if ! docker info >/dev/null 2>&1; then
    err "Docker 守护进程未运行。请先启动 Docker Desktop 再重试。"
    exit 1
  fi
}

# ================================================================
# B. .env 自举
# ================================================================

# 随机字符串(URL 安全,不含易混淆字符)
gen_random() {
  local n="${1:-48}"
  openssl rand -base64 "$n" 2>/dev/null | tr -dc 'A-Za-z0-9' | head -c "$n"
}

# 生成 Fernet key:优先本机 python-cryptography,退化到临时容器
gen_fernet() {
  if python3 -c "from cryptography.fernet import Fernet" >/dev/null 2>&1; then
    python3 -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"
  else
    # 本机无 cryptography,用临时 python 容器生成
    docker run --rm python:3.12-slim sh -c \
      "pip install --quiet cryptography -i https://pypi.tuna.tsinghua.edu.cn/simple >/dev/null 2>&1 && python -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())'"
  fi
}

# 读取 .env 里某个 key 的值(去引号)
env_get() {
  local key="$1"
  [ -f "$ENV_FILE" ] || return 1
  grep -E "^${key}=" "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '\r'
}

# 设置/替换 .env 里某个 key(不存在则追加)
env_set() {
  local key="$1" val="$2"
  if grep -qE "^${key}=" "$ENV_FILE"; then
    # 用 | 作分隔符避免值里的 / 干扰;转义 & 和 |
    local esc
    esc=$(printf '%s' "$val" | sed -e 's/[&|\\]/\\&/g')
    sed -i.bak -E "s|^${key}=.*|${key}=${esc}|" "$ENV_FILE" && rm -f "${ENV_FILE}.bak"
  else
    printf '%s=%s\n' "$key" "$val" >> "$ENV_FILE"
  fi
}

# 值是否缺失或仍是占位符(change-me*)
is_placeholder() {
  local v="$1"
  [ -z "$v" ] && return 0
  case "$v" in change-me*|CHANGE-ME*) return 0 ;; esac
  return 1
}

# 首次安装:从模板创建 .env 并填充密钥 + 交互问管理员
bootstrap_env() {
  title "首次配置 .env"
  if [ ! -f ".env.example" ]; then
    err "缺少 .env.example 模板,无法自举。请确认在 quanly 项目根目录运行。"
    exit 1
  fi
  cp .env.example "$ENV_FILE"
  info "已从 .env.example 生成 .env,正在填充随机密钥..."

  env_set "QUANLY_SECRET_KEY" "$(gen_random 50)"
  env_set "POSTGRES_PASSWORD" "$(gen_random 24)"
  info "生成 OKX 密钥加密主密钥(Fernet)..."
  local fkey; fkey=$(gen_fernet)
  if [ -z "$fkey" ]; then err "Fernet key 生成失败。"; exit 1; fi
  env_set "QUANLY_CREDENTIALS_ENC_KEY" "$fkey"

  # --- 交互问管理员账号/密码/端口(非交互场景全默认) ---
  local admin_user admin_pw nginx_port
  if [ -t 0 ]; then
    printf "管理员用户名 [默认 admin]: "; read -r admin_user || true
    printf "管理员密码 [留空=随机生成]: "; read -rs admin_pw || true; echo
    printf "网站端口 [默认 80]: "; read -r nginx_port || true
  fi
  admin_user="${admin_user:-admin}"
  nginx_port="${nginx_port:-80}"
  local pw_generated=0
  if [ -z "${admin_pw:-}" ]; then
    admin_pw="$(gen_random 16)"; pw_generated=1
  fi
  env_set "QUANLY_ADMIN_USER" "$admin_user"
  env_set "QUANLY_ADMIN_PASSWORD" "$admin_pw"
  env_set "NGINX_PORT" "$nginx_port"
  # 放开所有 IP 访问(不限本机);外部设备用本机局域网 IP 访问
  env_set "QUANLY_ALLOWED_HOSTS" "*"

  chmod 600 "$ENV_FILE"
  ok ".env 已生成并加密保护(chmod 600)"
  echo
  local ip; ip="$(lan_ip)"
  printf "${C_BLD}${C_YLW}请务必保存以下登录信息(仅显示这一次):${C_RESET}\n"
  printf "  管理员账号: ${C_BLD}%s${C_RESET}\n" "$admin_user"
  if [ "$pw_generated" = "1" ]; then
    printf "  管理员密码: ${C_BLD}%s${C_RESET}  ${C_YLW}(自动生成)${C_RESET}\n" "$admin_pw"
  else
    printf "  管理员密码: ${C_BLD}(你设置的密码)${C_RESET}\n"
  fi
  printf "  本机访问:   ${C_BLD}http://127.0.0.1:%s${C_RESET}\n" "$nginx_port"
  printf "  外部访问:   ${C_BLD}http://%s:%s${C_RESET}  ${C_YLW}(同局域网设备用此地址)${C_RESET}\n" "$ip" "$nginx_port"
  echo
}

# 校验已存在的 .env 必需项
validate_env() {
  local missing=0 k v
  for k in QUANLY_SECRET_KEY QUANLY_CREDENTIALS_ENC_KEY POSTGRES_PASSWORD QUANLY_ADMIN_PASSWORD; do
    v="$(env_get "$k" || true)"
    if is_placeholder "$v"; then
      err ".env 中 ${k} 缺失或仍是占位值(change-me...)"
      missing=1
    fi
  done
  if [ "$missing" = "1" ]; then
    echo
    warn "关键配置不完整,直接启动会导致后端崩溃。"
    if [ -t 0 ]; then
      printf "是否让脚本自动补全缺失的密钥?[Y/n] "; read -r ans || true
      case "${ans:-Y}" in
        [Nn]*) err "请手动编辑 .env 补齐后重试。"; exit 1 ;;
      esac
      # 自动补全占位/缺失项
      is_placeholder "$(env_get QUANLY_SECRET_KEY || true)"          && env_set QUANLY_SECRET_KEY "$(gen_random 50)"
      is_placeholder "$(env_get POSTGRES_PASSWORD || true)"          && env_set POSTGRES_PASSWORD "$(gen_random 24)"
      is_placeholder "$(env_get QUANLY_ADMIN_PASSWORD || true)"      && { local p; p="$(gen_random 16)"; env_set QUANLY_ADMIN_PASSWORD "$p"; warn "已生成管理员密码: $p (请保存)"; }
      if is_placeholder "$(env_get QUANLY_CREDENTIALS_ENC_KEY || true)"; then
        info "生成 Fernet 加密主密钥..."; env_set QUANLY_CREDENTIALS_ENC_KEY "$(gen_fernet)"
      fi
      ok ".env 已补全"
    else
      exit 1
    fi
  fi
}

# 确保 .env 就绪(首次自举 or 校验)。返回 0=首次刚创建 1=已存在
ensure_env() {
  if [ ! -f "$ENV_FILE" ]; then
    bootstrap_env
    return 0
  else
    validate_env
    return 1
  fi
}

# ================================================================
# C. compose 封装
# ================================================================
NGINX_PORT_CACHE=""
port() {
  if [ -z "$NGINX_PORT_CACHE" ]; then
    NGINX_PORT_CACHE="$(env_get NGINX_PORT || true)"; NGINX_PORT_CACHE="${NGINX_PORT_CACHE:-80}"
  fi
  printf '%s' "$NGINX_PORT_CACHE"
}

# 本机局域网 IP(供外部设备访问);查不到则回退 0.0.0.0
lan_ip() {
  local ip=""
  if command -v ipconfig >/dev/null 2>&1; then
    ip="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)"
  fi
  if [ -z "$ip" ] && command -v hostname >/dev/null 2>&1; then
    ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  fi
  printf '%s' "${ip:-0.0.0.0}"
}

dc()     { docker compose --env-file "$ENV_FILE" "$@"; }
dc_dev() { docker compose -f docker-compose.yml -f "$COMPOSE_DEV" --env-file "$ENV_FILE" "$@"; }

# 等 backend 健康 + 探活首页
wait_healthy() {
  local p; p="$(port)"
  info "等待服务启动(最多 120 秒)..."
  local i
  for i in $(seq 1 60); do
    if curl -sf "http://127.0.0.1:${p}/" >/dev/null 2>&1; then
      ok "服务已就绪"
      return 0
    fi
    sleep 2
  done
  warn "超时未探测到首页响应。打印 backend 最近日志:"
  dc logs backend --tail 25 || true
  return 1
}

print_access() {
  local p; p="$(port)"
  local u; u="$(env_get QUANLY_ADMIN_USER || true)"; u="${u:-admin}"
  local ip; ip="$(lan_ip)"
  echo
  ok "部署完成!"
  printf "  本机访问:   ${C_BLD}http://127.0.0.1:%s${C_RESET}\n" "$p"
  printf "  外部访问:   ${C_BLD}http://%s:%s${C_RESET}  ${C_YLW}(同局域网设备用此地址)${C_RESET}\n" "$ip" "$p"
  printf "  管理员账号: ${C_BLD}%s${C_RESET}\n" "$u"
  printf "  (密码见首次安装时的提示或你的 .env)\n\n"
}

save_state() {
  if git rev-parse HEAD >/dev/null 2>&1; then
    git rev-parse HEAD > "$STATE_FILE"
  fi
}

# ================================================================
# D. 部署动作
# ================================================================
BACKEND_SERVICES="backend celery-worker market-collector"

do_install() {
  title "全量部署(构建所有镜像)"
  ensure_env || true
  dc up -d --build
  wait_healthy || true
  save_state
  print_access
}

do_update() {
  title "更新部署"
  ensure_env || true

  local state="" rebuild_backend=0 rebuild_frontend=0
  [ -f "$STATE_FILE" ] && state="$(cat "$STATE_FILE" 2>/dev/null || true)"

  if [ -z "$state" ] || ! git rev-parse HEAD >/dev/null 2>&1 || ! git cat-file -e "$state" 2>/dev/null; then
    warn "无有效部署记录,执行全量重建。"
    rebuild_backend=1; rebuild_frontend=1
  else
    local head; head="$(git rev-parse HEAD)"
    if [ "$state" = "$head" ]; then
      info "代码无新提交(HEAD 未变)。将仅重启以应用配置改动。"
      dc up -d
      ok "已重启。"
      print_access
      return 0
    fi
    git diff --quiet "$state" "$head" -- backend/  || rebuild_backend=1
    git diff --quiet "$state" "$head" -- frontend/ || rebuild_frontend=1
    # docker-compose / nginx 配置变化也触发对应重建
    git diff --quiet "$state" "$head" -- docker-compose.yml backend/Dockerfile backend/docker-entrypoint.sh && : || rebuild_backend=1
    git diff --quiet "$state" "$head" -- frontend/Dockerfile nginx/ && : || rebuild_frontend=1
  fi

  local svcs=""
  [ "$rebuild_backend" = "1" ]  && svcs="$svcs $BACKEND_SERVICES"
  [ "$rebuild_frontend" = "1" ] && svcs="$svcs nginx"

  if [ -z "$(printf '%s' "$svcs" | tr -d ' ')" ]; then
    info "后端/前端代码均无变化,仅重启。"
    dc up -d
  else
    info "检测到变化,重建服务:${svcs}"
    # shellcheck disable=SC2086
    dc up -d --build $svcs
    # 未重建的其余服务也确保在运行
    dc up -d
  fi
  wait_healthy || true
  save_state
  print_access
}

do_dev() {
  title "开发热重载模式"
  ensure_env || true
  info "启动 dev 栈(挂载源码 + vite HMR)..."
  dc_dev up -d --build
  echo
  ok "开发模式已启动"
  printf "  前端(HMR):  ${C_BLD}http://127.0.0.1:5173${C_RESET}  改 .vue/.ts 秒级生效\n"
  printf "  后端 API:   http://127.0.0.1:8000\n"
  printf "  ${C_YLW}改后端 .py 后:${C_RESET} ./deploy.sh restart-backend\n"
  printf "  ${C_YLW}改策略/任务后:${C_RESET} ./deploy.sh restart-worker\n"
  warn "此模式仅供本地开发,勿用于正式对外部署。"
  echo
}

do_restart()         { title "重启全部"; dc restart; ok "已重启"; }
do_restart_backend() { title "重启后端"; dc restart backend; ok "backend 已重启(dev 下源码改动已生效)"; }
do_restart_worker()  { title "重启 Worker"; dc restart celery-worker; ok "celery-worker 已重启"; }
do_status()          { title "容器状态"; dc ps; }
do_logs()            { title "日志(Ctrl-C 退出)"; dc logs -f --tail 50; }
do_stop()            { title "停止全部"; dc stop; ok "已停止(数据保留)"; }

do_reset() {
  title "重置(删除容器,保留数据卷)"
  warn "这会停止并删除所有 quanly 容器。数据库/Redis 数据卷会保留。"
  if [ -t 0 ]; then
    printf "确认继续?输入 yes 回车: "; read -r ans || true
    [ "${ans:-}" = "yes" ] || { info "已取消。"; return 0; }
  fi
  dc down
  ok "容器已删除,数据卷保留(postgres_data/redis_data)。下次 install 会自动重建。"
}

# ================================================================
# 自动模式:判断该 install / update / restart
# ================================================================
auto_mode() {
  # 是否已经装过(有 state 或有容器)
  local has_containers=0
  if [ -n "$(dc ps -q 2>/dev/null || true)" ]; then has_containers=1; fi

  if [ ! -f "$ENV_FILE" ]; then
    info "未检测到配置,进入首次安装。"
    do_install
  elif [ ! -f "$STATE_FILE" ] && [ "$has_containers" = "0" ]; then
    info "未检测到部署记录且无运行容器,执行全量部署。"
    do_install
  else
    info "检测到已部署,执行更新(自动判断变化)。"
    do_update
  fi
}

# ================================================================
# 菜单
# ================================================================
menu() {
  title "quanly 部署助手"
  cat <<'EOF'
  1) 首次安装 / 全量重建
  2) 更新部署(自动判断变化,生产重建)
  3) 开发热重载模式(改代码即生效)
  4) 重启全部(不重建)
  5) 查看容器状态
  6) 查看日志
  7) 停止全部
  8) 重置(删容器,保留数据)
  0) 退出
EOF
  printf "请选择 [默认 2]: "; read -r choice || true
  case "${choice:-2}" in
    1) do_install ;;
    2) do_update ;;
    3) do_dev ;;
    4) do_restart ;;
    5) do_status ;;
    6) do_logs ;;
    7) do_stop ;;
    8) do_reset ;;
    0) exit 0 ;;
    *) err "无效选择"; exit 1 ;;
  esac
}

# ================================================================
# 入口
# ================================================================
main() {
  check_prereq
  local cmd="${1:-auto}"
  case "$cmd" in
    auto)            auto_mode ;;
    menu|m)          menu ;;
    install)         do_install ;;
    update)          do_update ;;
    dev)             do_dev ;;
    restart)         do_restart ;;
    restart-backend) do_restart_backend ;;
    restart-worker)  do_restart_worker ;;
    status)          do_status ;;
    logs)            do_logs ;;
    stop)            do_stop ;;
    reset)           do_reset ;;
    -h|--help|help)
      sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//' ;;
    *) err "未知命令: $cmd"; echo "运行 ./deploy.sh --help 查看用法"; exit 1 ;;
  esac
}

main "$@"
