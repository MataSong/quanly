# Quanly 傻瓜化一键部署 + 热更新 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 提供单入口 `quanly` 命令,让小白一键完成本地/服务器部署与热更新。

**Architecture:** 极薄分发器 `quanly.sh`(Linux/Mac),底层复用并强化现有 `deploy/*.sh`。新增 `deploy/lib.sh`(公共函数)、`deploy/preflight.sh`(环境自检)、`docker-compose.local.yml`(本地模式补齐常驻进程)。热更新按 git diff 路径只重建变更镜像。

**Tech Stack:** Bash 脚本、Docker Compose、现有 Django/Vue 容器栈。

**约束:**
- 项目**非 git 仓库** → 所有 Commit 步骤跳过,改为 `bash -n` 静态检查。
- **无 shell 测试框架** → 用 `bash -n` + 手动运行清单验证。
- **数据安全铁律**:`.env.prod` 存在即保留绝不覆盖(`SECRET_ENCRYPTION_KEY` 变更会导致已存用户 OKX 密钥无法解密)。脚本不打印任何密钥值。

**参考文件(实现前先读):**
- `docker-compose.yml`(base:含 `x-backend-env: &backend-env` 锚点、nginx `8080:80`)
- `docker-compose.prod.yml`(prod:Caddy 80/443、celery-beat、private-ws、`x-backend-env: &prod-backend-env`)
- `.env.prod.example`(env 键名清单)
- 现有 `deploy/init.sh`、`deploy/update.sh`、`deploy/backup.sh`、`deploy/restore.sh`(将被强化/复用)

---

## File Structure

| 文件 | 职责 |
|------|------|
| `deploy/lib.sh`(新增) | 公共函数库,仅被 `source`。compose 命令选择、密钥生成、彩色输出、项目名 |
| `deploy/preflight.sh`(新增) | 环境自检:Docker/compose/端口/OKX 连通 |
| `docker-compose.local.yml`(新增) | 本地模式补齐 `celery-beat` + `private-ws`(不含 Caddy) |
| `deploy/init.sh`(重写) | 双模式初始化,调 preflight,保留已有 `.env.prod` |
| `deploy/update.sh`(重写) | git diff 路径判断,只重建变更镜像 |
| `deploy/backup.sh`(改) | 复用 lib.sh 的 compose/project_name |
| `deploy/restore.sh`(改) | 复用 lib.sh |
| `quanly.sh`(新增) | 唯一入口分发器 + status/logs/help 内联实现 |

**依赖顺序:** lib.sh → preflight.sh → docker-compose.local.yml → init.sh / update.sh / backup.sh / restore.sh → quanly.sh

---

## Task 1: 公共函数库 lib.sh

**Files:**
- Create: `deploy/lib.sh`

- [ ] **Step 1: 写 lib.sh 完整内容**

`deploy/lib.sh`:

```bash
#!/usr/bin/env bash
# 公共函数库:被 quanly.sh 与 deploy/*.sh 通过 `source` 引入,不单独执行。
# 提供:彩色输出、密钥生成、compose 命令选择(按 QUANLY_MODE)、项目名。

# --- 彩色输出 ---
_c_red='\033[0;31m'; _c_yel='\033[0;33m'; _c_grn='\033[0;32m'; _c_rst='\033[0m'
say()  { printf "${_c_grn}==>${_c_rst} %s\n" "$*"; }
warn() { printf "${_c_yel}[!]${_c_rst} %s\n" "$*" >&2; }
die()  { printf "${_c_red}[x]${_c_rst} %s\n" "$*" >&2; exit 1; }

# --- 项目名(compose 卷前缀,取当前目录名规整为小写字母数字) ---
project_name() { basename "$PWD" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9'; }

# --- 密钥生成 ---
gen_secret() { openssl rand -base64 48 | tr -d '\n/+=' | cut -c1-50; }
gen_hex()    { openssl rand -hex 16; }
gen_fernet() {
  python3 -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())' 2>/dev/null \
    || docker run --rm python:3.13-slim sh -c \
       'pip -q install cryptography >/dev/null 2>&1 && python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"'
}

# --- compose 命令(按 QUANLY_MODE 选择;默认 local) ---
# 用法:compose ps  /  compose up -d --build
ENV_FILE="${ENV_FILE:-.env.prod}"
compose() {
  local mode="${QUANLY_MODE:-local}"
  if [ "$mode" = "server" ]; then
    docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file "$ENV_FILE" "$@"
  else
    docker compose -f docker-compose.yml -f docker-compose.local.yml --env-file "$ENV_FILE" "$@"
  fi
}

# --- 从 .env.prod 读取某个键的值(不存在返回空) ---
env_get() {
  local key="$1"
  [ -f "$ENV_FILE" ] || return 0
  grep "^${key}=" "$ENV_FILE" | head -1 | cut -d= -f2-
}

# --- 从 .env.prod 载入 QUANLY_MODE 到环境(供 update/status/logs 用) ---
load_mode() {
  local m; m="$(env_get QUANLY_MODE)"
  export QUANLY_MODE="${m:-local}"
}
```

- [ ] **Step 2: 静态检查**

Run: `bash -n deploy/lib.sh`
Expected: 无输出(语法正确)

- [ ] **Step 3: 冒烟测试函数可用**

Run: `bash -c 'source deploy/lib.sh; say hello; echo "proj=$(project_name)"; echo "hex=$(gen_hex)"'`
Expected: 打印绿色 `==> hello`、`proj=quanly`、`hex=` 后跟 32 位十六进制串

---

## Task 2: 环境自检 preflight.sh

**Files:**
- Create: `deploy/preflight.sh`

- [ ] **Step 1: 写 preflight.sh 完整内容**

`deploy/preflight.sh`:

```bash
#!/usr/bin/env bash
# 环境自检:Docker 安装/运行、compose 可用、端口占用、OKX 连通。
# 硬性失败(Docker 相关)中止;软性(端口/OKX)仅警告。
# 可独立运行,也被 init/update 通过 `source` 调用。
set -euo pipefail
cd "$(dirname "$0")/.."
source deploy/lib.sh

preflight() {
  say "环境自检…"

  command -v docker >/dev/null 2>&1 \
    || die "未检测到 Docker。请先安装 Docker Desktop:https://www.docker.com/products/docker-desktop/"

  docker info >/dev/null 2>&1 \
    || die "Docker 未运行。请启动 Docker Desktop 后重试。"

  docker compose version >/dev/null 2>&1 \
    || die "docker compose 不可用。请升级到较新版 Docker Desktop。"

  # 端口占用(软性):本地查 8080;服务器查 80/443
  local mode="${QUANLY_MODE:-local}"
  local ports
  if [ "$mode" = "server" ]; then ports="80 443"; else ports="8080"; fi
  for p in $ports; do
    if command -v lsof >/dev/null 2>&1 && lsof -iTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1; then
      warn "端口 $p 已被占用(若是本项目自身在跑可忽略)。"
    fi
  done

  # OKX 连通(软性)
  if command -v curl >/dev/null 2>&1; then
    if ! curl -s --max-time 8 https://www.okx.com/api/v5/public/time >/dev/null 2>&1; then
      warn "无法连接 OKX(www.okx.com)。行情与交易将不可用,可能需要代理或检查网络。"
    fi
  fi

  say "自检完成。"
}

# 独立运行时执行 preflight;被 source 时仅定义函数
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
  preflight
fi
```

- [ ] **Step 2: 静态检查**

Run: `bash -n deploy/preflight.sh`
Expected: 无输出

- [ ] **Step 3: 独立运行(Docker 在跑时)**

Run: `bash deploy/preflight.sh`
Expected: 打印 `==> 环境自检…` 与 `==> 自检完成。`;若网络不通 OKX 会有黄色 `[!]` 警告但不中止

---

## Task 3: 本地模式 compose override

**Files:**
- Create: `docker-compose.local.yml`

- [ ] **Step 1: 写 docker-compose.local.yml 完整内容**

补齐本地模式缺失的两个常驻进程,复用 base 的 `&backend-env` 锚点。**不含 Caddy**。

`docker-compose.local.yml`:

```yaml
# 本地模式覆盖:补齐 base 缺少的 celery-beat + private-ws,保证本地也能实时回填/校正数据。
# 用法:docker compose -f docker-compose.yml -f docker-compose.local.yml --env-file .env.prod up -d
# 不含 Caddy(本地免域名/证书,入口走 base 的 nginx 8080)。
services:
  celery-beat:
    build: ./backend
    command: celery -A config beat -l info
    environment: *backend-env
    restart: unless-stopped
    depends_on:
      - redis
      - backend

  private-ws:
    build: ./backend
    command: python manage.py run_private_ws --env sim
    environment: *backend-env
    restart: unless-stopped
    depends_on:
      - redis
      - backend
```

- [ ] **Step 2: 校验 YAML + 锚点可解析**

Run: `docker compose -f docker-compose.yml -f docker-compose.local.yml --env-file .env.prod config >/dev/null && echo OK`
Expected: `OK`(锚点 `*backend-env` 成功解析,无 YAML 错误)

- [ ] **Step 3: 确认 celery-beat 与 private-ws 出现在合并配置里**

Run: `docker compose -f docker-compose.yml -f docker-compose.local.yml --env-file .env.prod config --services | sort`
Expected: 服务列表含 `celery-beat` 与 `private-ws`(且**不含** `caddy`)

---

## Task 4: 重写 init.sh(双模式 + 保留已有配置)

**Files:**
- Modify(整体重写): `deploy/init.sh`

- [ ] **Step 1: 写 init.sh 完整内容**

`deploy/init.sh`:

```bash
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

# 3) 构建并拉起
say "构建并拉起全部服务(模式:$QUANLY_MODE)…"
compose up -d --build

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

# 6) 完成提示
if [ "$QUANLY_MODE" = "server" ]; then
  local_domain="$(env_get DOMAIN)"
  say "完成!访问 https://$local_domain"
  say "提示:Caddy 首次申请证书需 1-2 分钟;确保域名已解析到本机且 80/443 开放。"
else
  say "完成!访问 http://localhost:8080"
fi
say "下一步:登录后到「API 密钥」页填写你的 OKX Key/Secret/Passphrase。"
```

- [ ] **Step 2: 静态检查**

Run: `bash -n deploy/init.sh`
Expected: 无输出

- [ ] **Step 3: 保留性快速验证(不真正跑容器)**

前置:确保当前目录已有真实 `.env.prod`。计算其 md5:
Run: `md5sum .env.prod`
记下哈希值。此步仅验证脚本逻辑分支——在 Task 10 的手动清单里再做完整运行验证。此处只确认 `bash -n` 通过即可。

---

## Task 5: 重写 update.sh(git diff 只重建变更镜像)

**Files:**
- Modify(整体重写): `deploy/update.sh`

- [ ] **Step 1: 写 update.sh 完整内容**

`deploy/update.sh`:

```bash
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
fi

# 7) 边缘代理重载
if [ "$RESTART_EDGE" = "1" ]; then
  say "重载边缘代理…"
  if [ "$QUANLY_MODE" = "server" ]; then
    compose up -d --no-deps caddy nginx
  else
    compose up -d --no-deps nginx
  fi
fi

# 8) 清理
docker image prune -f >/dev/null 2>&1 || true
say "热更新完成。"
```

> **说明:** `compose up -d --no-deps --build $BACKEND_SERVICES` 中 `celery-beat`/`private-ws` 在 local 与 server 两种 compose 组合里均有定义(local override / prod override),故服务名列表两模式通用,无需分支。

- [ ] **Step 2: 静态检查**

Run: `bash -n deploy/update.sh`
Expected: 无输出

---

## Task 6: 强化 backup.sh 复用 lib.sh

**Files:**
- Modify(整体重写): `deploy/backup.sh`

- [ ] **Step 1: 写 backup.sh 完整内容**

`deploy/backup.sh`:

```bash
#!/usr/bin/env bash
# 备份:PostgreSQL 逻辑导出 + InfluxDB 数据卷打包,保留最近 14 份。
set -euo pipefail
cd "$(dirname "$0")/.."
source deploy/lib.sh

ENV_FILE=".env.prod"
[ -f "$ENV_FILE" ] || die "缺少 $ENV_FILE,请先运行:./quanly init"
load_mode

TS="$(date +%Y%m%d-%H%M%S)"
OUT="backups"; mkdir -p "$OUT"
PROJECT="$(project_name)"

say "备份 PostgreSQL → $OUT/db-$TS.sql.gz"
compose exec -T postgres pg_dump -U quanly quanly | gzip > "$OUT/db-$TS.sql.gz"

say "备份 InfluxDB 数据卷 → $OUT/influx-$TS.tar.gz"
docker run --rm -v "${PROJECT}_influxdata":/data -v "$PWD/$OUT":/backup alpine \
  tar czf "/backup/influx-$TS.tar.gz" -C /data . \
  || warn "InfluxDB 卷备份跳过(卷名 ${PROJECT}_influxdata 不匹配可忽略)"

# 仅保留最近 14 份
ls -1t "$OUT"/db-*.sql.gz 2>/dev/null | tail -n +15 | xargs -r rm -f
ls -1t "$OUT"/influx-*.tar.gz 2>/dev/null | tail -n +15 | xargs -r rm -f
say "备份完成: $TS"
```

- [ ] **Step 2: 静态检查**

Run: `bash -n deploy/backup.sh`
Expected: 无输出

---

## Task 7: 强化 restore.sh 复用 lib.sh

**Files:**
- Modify(整体重写): `deploy/restore.sh`

- [ ] **Step 1: 写 restore.sh 完整内容**

`deploy/restore.sh`:

```bash
#!/usr/bin/env bash
# 恢复:从指定 db 备份还原 PostgreSQL(会覆盖当前库,需二次确认)。
set -euo pipefail
cd "$(dirname "$0")/.."
source deploy/lib.sh

ENV_FILE=".env.prod"
[ -f "$ENV_FILE" ] || die "缺少 $ENV_FILE,请先运行:./quanly init"
load_mode

DB_DUMP="${1:-}"
[ -z "$DB_DUMP" ] && die "用法: ./quanly restore backups/db-YYYYmmdd-HHMMSS.sql.gz"
[ -f "$DB_DUMP" ] || die "找不到备份文件: $DB_DUMP"

read -rp "将覆盖当前数据库,确认?(输入 yes 继续) " ok
[ "$ok" = "yes" ] || { say "已取消"; exit 0; }

say "恢复数据库 from $DB_DUMP"
gunzip -c "$DB_DUMP" | compose exec -T postgres psql -U quanly quanly
say "恢复完成。建议随后重启后端:./quanly logs backend 查看状态。"
compose restart backend ws || true
```

- [ ] **Step 2: 静态检查**

Run: `bash -n deploy/restore.sh`
Expected: 无输出

---

## Task 8: 单入口分发器 quanly.sh

**Files:**
- Create: `quanly.sh`

- [ ] **Step 1: 写 quanly.sh 完整内容**

`quanly.sh`:

```bash
#!/usr/bin/env bash
# Quanly 统一入口。用法:./quanly <子命令>
#   init      初始化部署(首次或重新拉起)
#   update    热更新(拉代码 + 只重建变更镜像)
#   backup    备份数据库与时序数据
#   restore   从备份恢复数据库:./quanly restore <file>
#   status    查看各服务运行状态
#   logs      跟踪日志:./quanly logs [服务名]
#   help      显示本帮助
set -euo pipefail
cd "$(dirname "$0")"
source deploy/lib.sh

usage() {
  cat <<'EOF'
Quanly 部署工具。用法: ./quanly <子命令>

  init            初始化部署(首次生成配置并拉起;已部署则重新拉起)
  update          热更新(git pull + 只重建变更的镜像 + 按需迁移)
  backup          备份 PostgreSQL 与 InfluxDB
  restore <file>  从指定备份恢复数据库
  status          查看各服务运行状态
  logs [服务名]   跟踪日志(省略服务名则全部)
  help            显示本帮助
EOF
}

cmd="${1:-help}"
[ $# -gt 0 ] && shift || true

case "$cmd" in
  init)    bash deploy/init.sh "$@" ;;
  update)  bash deploy/update.sh "$@" ;;
  backup)  bash deploy/backup.sh "$@" ;;
  restore) bash deploy/restore.sh "$@" ;;
  status)
    load_mode
    compose ps
    ;;
  logs)
    load_mode
    compose logs -f --tail=100 "$@"
    ;;
  help|--help|-h) usage ;;
  *) warn "未知子命令: $cmd"; usage; exit 1 ;;
esac
```

- [ ] **Step 2: 赋可执行权限**

Run: `chmod +x quanly.sh deploy/*.sh`
Expected: 无输出

- [ ] **Step 3: 静态检查**

Run: `bash -n quanly.sh`
Expected: 无输出

- [ ] **Step 4: help 与未知命令验证**

Run: `./quanly.sh help && echo "---" && ./quanly.sh bogus; echo "exit=$?"`
Expected: 打印帮助文本;然后对 bogus 打印黄色 `[!] 未知子命令: bogus` + 帮助 + `exit=1`

---

## Task 10: 手动集成验证清单

**Files:** 无(仅运行验证)

> 前置:Docker Desktop 已启动。当前目录已有真实 `.env.prod`(含用户 OKX 密钥,**不可覆盖**)。

- [ ] **Step 1: 全部脚本静态检查**

Run: `for f in quanly.sh deploy/lib.sh deploy/preflight.sh deploy/init.sh deploy/update.sh deploy/backup.sh deploy/restore.sh; do bash -n "$f" && echo "OK $f"; done`
Expected: 每个文件都打印 `OK <文件名>`

- [ ] **Step 2: compose 配置合并校验(本地模式)**

Run: `docker compose -f docker-compose.yml -f docker-compose.local.yml --env-file .env.prod config --services | sort`
Expected: 含 `backend celery-beat celery-worker frontend influxdb market-collector nginx postgres private-ws redis ws`;**不含** `caddy`

- [ ] **Step 3: 配置保留性(核心安全)**

Run: `md5sum .env.prod > /tmp/env_before.md5 && bash deploy/init.sh </dev/null 2>&1 | grep -i "保留不覆盖" && md5sum -c /tmp/env_before.md5`
Expected: 打印 `检测到已有 .env.prod,保留不覆盖`;`md5sum -c` 输出 `.env.prod: OK`(内容未变)

- [ ] **Step 4: status 与 logs**

Run: `./quanly.sh status`
Expected: 打印 `docker compose ps` 表格,backend/nginx 等为 Up

Run: `timeout 5 ./quanly.sh logs backend || true`
Expected: 5 秒内跟踪打印 backend 日志后被 timeout 终止(无脚本报错)

- [ ] **Step 5: update 无变更路径(非 git 仓库)**

> 本项目非 git 仓库,`update` 会走“非 git → 全量重建”分支。

Run: `./quanly.sh update 2>&1 | tail -20`
Expected: 打印“非 git 仓库,无法检测变更,将执行全量重建。”→ 备份 → 迁移 → 重建 → `热更新完成。`;结束后 `./quanly.sh status` 各服务仍 Up

- [ ] **Step 6: preflight 硬性失败提示(可选,需手动停 Docker)**

若愿意验证:退出 Docker Desktop → `bash deploy/preflight.sh`
Expected: 红色 `[x] Docker 未运行。请启动 Docker Desktop 后重试。` 并以非零退出。验证后重新启动 Docker。

- [ ] **Step 7: 交付核验报告**

对照 spec“交付后核验”,逐条汇总 Step 1-6 结果,向用户报告本地一键部署 + 热更新是否全部达标。

---

## Self-Review

**1. Spec coverage:**
- 单入口 quanly 子命令 → Task 8 ✅
- lib.sh 公共函数 → Task 1 ✅
- preflight 环境自检 → Task 2 ✅
- 本地模式补 celery-beat/private-ws(local override)→ Task 3 ✅
- init 双模式 + 保留已有配置 + 免域名本地 → Task 4 ✅
- update git diff 只重建变更 + 非 git 回退全量 → Task 5 ✅
- backup/restore 复用 lib.sh → Task 6/7 ✅
- 敏感项首次生成、之后保留 → Task 4 Step 1 + Task 10 Step 3 ✅
- 数据安全(备份先行、不打印密钥)→ Task 5/6 ✅
- 测试策略(bash -n + 手动清单)→ 各 Task Step + Task 10 ✅

**2. Placeholder scan:** 无 TBD/TODO;每个改文件的 Step 均含完整脚本内容;命令均给出预期输出。

**3. Type/名称一致性:**
- `compose()`、`load_mode`、`env_get`、`project_name`、`say/warn/die`、`gen_*` 在 lib.sh 定义,后续 Task 调用名一致。
- `QUANLY_MODE`(local/server)、`ENV_FILE`(.env.prod)全程一致。
- `BACKEND_SERVICES` 列表(backend ws market-collector celery-worker celery-beat private-ver…)—— 核对:update.sh 用 `celery-beat private-ws`,与 local/prod override 服务名一致 ✅。
- init.sh 中 `local local_domain` 在非函数顶层使用 `local` 会报错 → **已修正**:见下。

**修正:** Task 4 init.sh 第 6 步完成提示里 `local local_domain="$(env_get DOMAIN)"` 处于脚本顶层(非函数内),`local` 关键字非法。改为普通变量:

```bash
if [ "$QUANLY_MODE" = "server" ]; then
  server_domain="$(env_get DOMAIN)"
  say "完成!访问 https://$server_domain"
  say "提示:Caddy 首次申请证书需 1-2 分钟;确保域名已解析到本机且 80/443 开放。"
else
  say "完成!访问 http://localhost:8080"
fi
```

实现 Task 4 时使用上述修正版顶层变量写法(勿用 `local`)。
