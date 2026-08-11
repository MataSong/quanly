# Quanly 傻瓜化一键部署 + 热更新 设计

**日期**: 2026-08-11
**范围**: 用户原始需求点 5 —— 让小白也能一键初始化部署、代码更新时热更新。

---

## 目标

小白只需记住一个命令 `./quanly <子命令>`,即可完成：

- **初始化部署**：自动生成配置（随机密钥）、拉起全部容器、迁移数据库、收集静态资源。
- **热更新**：拉最新代码后，按变更路径只重建受影响的镜像并重启，数据不丢。
- 支持**本地**（localhost，免域名/证书）与**服务器**（域名 + Caddy 自动 HTTPS）两种模式。

## 非目标（YAGNI）

- 不做真·免重启热加载（gunicorn --reload / 源码挂载）—— 用户已选“重建变更镜像即可”。
- 不做多机/集群编排、CI/CD 集成。
- 不做 Windows 纯 CMD 原生支持 —— `quanly.bat` 依赖 git-bash 或 WSL 提供 bash（Windows 上运行 bash 脚本的唯一现实路径）。
- 不改动已验证可用的备份/恢复核心逻辑，只做复用重构。

## 已确认的设计决策

| 决策点 | 选择 |
|--------|------|
| 统一入口 | 单入口 `quanly` 子命令，现有 deploy/*.sh 作为底层被调用 |
| 部署场景 | 本地 + 服务器 双模式 |
| 热更新检测 | 按 git diff 路径判断，只重建变更镜像 |
| 敏感项 | 首次自动生成随机值，之后原样保留（绝不覆盖 `.env.prod`） |

---

## 架构

### 文件结构

```
quanly.sh          ← 唯一入口(Linux/Mac/服务器)。解析子命令并分发到 deploy/*.sh
quanly.bat         ← Windows 入口。定位 git-bash/WSL 的 bash,转调 quanly.sh
docker-compose.local.yml  ← 新增。本地模式补齐 celery-beat + private-ws(不含 Caddy)
deploy/
  lib.sh           ← 新增。公共函数库,被其余脚本 source
  preflight.sh     ← 新增。环境自检(Docker/端口/OKX 连通)
  init.sh          ← 强化。双模式 + 免域名本地模式 + 调 preflight
  update.sh        ← 强化。git diff 路径判断 → 只重建变更镜像
  backup.sh        ← 保留。改为复用 lib.sh 的 compose/项目名函数
  restore.sh       ← 保留。改为复用 lib.sh
```

### 单元职责

- **quanly.sh**：极薄分发器。`case "$1"` 分发到子命令函数，每个子命令函数调用对应 `deploy/*.sh`。提供 `help`/`status`/`logs` 内联实现（简单，无需独立脚本）。
- **quanly.bat**：探测 `bash`（优先 git-bash 常见路径 `C:\Program Files\Git\bin\bash.exe`，回退 `wsl bash`），把参数原样透传给 `quanly.sh`。若都找不到，打印安装 git-bash 的指引并退出。
- **deploy/lib.sh**：不可执行，仅被 `source`。导出：
  - `COMPOSE_LOCAL` / `COMPOSE_PROD`：两种模式的 compose 命令字符串。
  - `compose()`：按 `$QUANLY_MODE`（local/server）选择正确的 compose 命令。
  - `gen_secret` / `gen_hex` / `gen_fernet`：密钥生成（fernet 优先本机 python3，回退 docker one-shot）。
  - `project_name`：compose 卷前缀（当前目录名规整）。
  - `say` / `warn` / `die`：带颜色的统一输出。
- **deploy/preflight.sh**：环境自检，见下节。可独立运行，也被 init/update source 调用。

### 两种模式的 compose 组合

- **本地模式**（`QUANLY_MODE=local`）：base compose + 新增 `docker-compose.local.yml`。入口是 nginx `8080:80`。**不启动 Caddy**（避免小白无域名时卡在证书申请）。仍读 `.env.prod` 作为环境变量来源。
  - compose 命令：`docker compose -f docker-compose.yml -f docker-compose.local.yml --env-file .env.prod`
  - **为什么需要 local override**：base compose 缺 `celery-beat`（定时全量校正余额/持仓）和 `private-ws`（实时回填余额/持仓/订单）——这两个常驻进程只定义在 prod override 里。若本地只跑 base，会重现“看不到实时数据”的问题。因此新增 `docker-compose.local.yml`，仅补齐这两个进程（复用 base 的 `*backend-env`），**不含 Caddy**。
  - **新增文件 `docker-compose.local.yml`** 内容：`celery-beat` 服务（`command: celery -A config beat -l info`）+ `private-ws` 服务（`command: python manage.py run_private_ws --env sim`），二者 `build: ./backend`、`environment: *backend-env`、`depends_on: [redis, backend]`、`restart: unless-stopped`。
- **服务器模式**（`QUANLY_MODE=server`）：base + prod override。入口是 Caddy `80/443` 自动 HTTPS，nginx 8080 作为备用 HTTP 入口。
  - compose 命令：`docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.prod`

模式在 `.env.prod` 中以 `QUANLY_MODE=local|server` 持久化，`init` 首次询问并写入，`update`/`status`/`logs` 读取它以选择正确的 compose 组合。

---

## 子命令行为

### `quanly init`

1. 运行 `preflight.sh`（Docker 检查为硬性，OKX 连通为警告）。
2. 若 `.env.prod` **已存在** → 打印“检测到已有配置，保留不覆盖”，跳到步骤 5（直接拉起）。此时 `QUANLY_MODE` 从文件读取。
3. 若 `.env.prod` **不存在** → 询问模式：
   - “本地还是服务器？[1] 本地(localhost) [2] 服务器(带域名 HTTPS)”
   - 本地：不问域名。`ALLOWED_HOSTS=localhost,127.0.0.1`，`QUANLY_MODE=local`。
   - 服务器：问域名、证书邮箱。`ALLOWED_HOSTS=<域名>`，`DOMAIN`/`ACME_EMAIL` 写入，`QUANLY_MODE=server`。
4. 生成随机 `DJANGO_SECRET_KEY`、`SECRET_ENCRYPTION_KEY`、`DB_PASSWORD`、`INFLUX_PASSWORD`、`INFLUX_ADMIN_TOKEN`，连同固定项写入 `.env.prod`，`chmod 600`。
5. `compose up -d --build`（按模式选组合）。
6. 等 postgres healthy → `migrate --noinput` → `collectstatic --noinput`。
7. 打印访问地址：本地 `http://localhost:8080`；服务器 `https://<域名>`（附证书申请 1-2 分钟提示）。

### `quanly update`

1. 运行 `preflight.sh`。
2. `git pull --ff-only`（非 git 仓库或 pull 失败 → 警告并用当前代码继续）。为拿到 diff，pull **前**记录 `git rev-parse HEAD` 为 `OLD_SHA`，pull 后取 `NEW_SHA`。
3. `bash deploy/backup.sh`（失败仅警告，不中断）。
4. **变更检测**：`CHANGED=$(git diff --name-only "$OLD_SHA" "$NEW_SHA")`（无 git 时视为“全部变更”以求稳妥）。
   - `frontend/` 命中 → 标记重建 `frontend`。
   - `backend/` 或 `backend/requirements.txt` 命中 → 标记重建 backend 系列。服务列表按模式：base 的 `backend ws market-collector celery-worker`，local 模式追加 `celery-beat private-ws`（来自 local override），server 模式追加 `celery-beat private-ws`（来自 prod override）。
   - `docker-compose*.yml` / `Caddyfile` / `nginx/` 命中 → 标记重启对应边缘服务。
   - 无任何命中 → 打印“无代码变更，无需重建”，跳到步骤 8。
5. 若需重建 backend：先 `up -d postgres redis influxdb`，等 postgres healthy，`run --rm backend python manage.py migrate --noinput`。
6. 按标记 `up -d --no-deps --build <服务>` 逐组重建（前端、后端系列、边缘）。
7. 若重建了 backend：`collectstatic --noinput`。
8. `docker image prune -f` 清悬空镜像。打印“热更新完成”。

### `quanly backup` / `quanly restore <file>`

透传到现有 `deploy/backup.sh` / `deploy/restore.sh`（内部改用 lib.sh 的 compose/project_name）。

### `quanly status`

`compose ps`，并高亮 backend/nginx/caddy 的健康状态。

### `quanly logs [服务名]`

`compose logs -f --tail=100 [服务名]`（无参数则全部）。

### `quanly help`

列出所有子命令及一行说明。无参数或未知子命令时也打印 help。

---

## 环境自检 preflight.sh

按顺序检查，用人话提示：

1. **Docker 已安装**：`command -v docker` 失败 → `die` 并提示去 docker.com 装 Docker Desktop。
2. **Docker daemon 在跑**：`docker info` 失败 → `die` 并提示启动 Docker Desktop。
3. **compose 可用**：`docker compose version` 失败 → `die` 并提示升级 Docker。
4. **端口占用**：本地模式查 8080；服务器模式查 80/443。占用 → `warn`（不中断，因可能是本项目自己在跑）。
5. **OKX 连通**：`curl -s --max-time 8 https://www.okx.com/api/v5/public/time` 失败 → `warn`（明确告知：连不上 OKX 则行情/交易不可用，可能需代理）。

硬性失败（1-3）中止；软性（4-5）仅警告。

---

## 错误处理

- 所有脚本 `set -euo pipefail`。
- `.env.prod` 缺失时 `update`/`status`/`logs` → `die` 提示先跑 `quanly init`。
- `restore` 覆盖数据库前需输入 `yes` 二次确认（保留现有行为）。
- migrate 失败 → 脚本非零退出（不吞错误），提示查看 `quanly logs backend`。
- git diff 在 shallow clone 或首次无 OLD_SHA 时 → 回退为“全部重建”。

## 数据安全（不可回退约束）

- `.env.prod` 存在即保留，**绝不覆盖**（`SECRET_ENCRYPTION_KEY` 一旦变更会导致已存用户 OKX 密钥无法解密）。
- `update` 在重建前强制 `backup.sh`，失败仅警告但会显式提示用户。
- 脚本不打印任何密钥值到终端。

---

## 测试策略（无自动化测试框架，靠手动 + 脚本自检）

因项目无 shell 测试框架，采用可复核的手动验证清单（实现计划中每步附命令与预期）：

1. **本地全新部署**：删除测试用 `.env.prod` 副本 → `quanly init` 选本地 → 断言 `.env.prod` 生成且含随机密钥、`http://localhost:8080` 可访问、`compose ps` 全 Up。
2. **保留性**：再次 `quanly init` → 断言打印“保留不覆盖”，`.env.prod` 内容 md5 不变。
3. **无变更更新**：`quanly update`（无代码改动）→ 断言打印“无代码变更”，未触发 build。
4. **前端变更更新**：改一个前端文件并 commit → `quanly update` → 断言仅 frontend 重建，backend 未动。
5. **后端变更更新**：改一个后端文件并 commit → `quanly update` → 断言 backend 系列重建 + migrate 执行。
6. **preflight**：停掉 Docker daemon → `quanly init` → 断言明确报错并中止。
7. **bash 语法**：所有脚本 `bash -n` 静态检查通过。

## 交付后核验

实现完成后，逐项跑上述 1-7 验证清单，并向用户报告结果。
