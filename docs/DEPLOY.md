# Quanly 生产部署清单

> 目标:把项目部署到线上、切换到真实 OKX。核心业务代码无需改动,主要是环境配置。

## 0. 前提(先验证,否则白忙)

- **服务器必须能访问 OKX**。上服务器后先跑:
  ```bash
  curl -m 10 https://www.okx.com/api/v5/public/time
  ```
  返回 JSON 才算通。国内服务器通常连不上(同 PyPI/DockerHub),需海外服务器或代理。
- 已装 Docker + Docker Compose。
- 有域名 + SSL 证书(Let's Encrypt 或购买)。

## 1. 拉代码 + 准备配置

```bash
git clone <repo> quanly && cd quanly
cp .env.prod.example .env.prod
```
编辑 `.env.prod`,逐项填真实值(模板里每项有注释)。**必须改**的:
- `DJANGO_SECRET_KEY`：`python -c "import secrets;print(secrets.token_urlsafe(50))"`
- `SECRET_ENCRYPTION_KEY`：`python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"`（设定后勿改,否则已存用户密钥无法解密）
- `DJANGO_DEBUG=0`、`ALLOWED_HOSTS=你的域名`
- 数据库/InfluxDB 密码与 token
- `MARKET_FEED=okx`、`EXCHANGE_MODE=okx`（切真实 OKX）

## 2. 放置 SSL 证书

```bash
mkdir -p nginx/certs
# 放入 fullchain.pem 和 privkey.pem
cp /path/fullchain.pem nginx/certs/
cp /path/privkey.pem   nginx/certs/
```
编辑 `nginx/nginx.prod.conf` 把 `your-domain.com` 换成你的域名。

## 3. 镜像准备（国内服务器同样可能要国内加速）

若无法直连 Docker Hub,先从国内源拉基础镜像再 tag（参考本机做法,如 daocloud）。
构建策略容器镜像（celery-worker 动态 run 它）:
```bash
docker build -t quanly-strategy-runner ./strategy-runner
```

## 4. 启动全栈（生产 compose 覆盖:HTTPS + 443）

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.prod up -d --build
```
backend 容器 entrypoint 会自动 `migrate`。确认全部容器健康:
```bash
docker compose --env-file .env.prod ps
```

## 5. 验证

- 浏览器开 `https://你的域名` → 注册 → 登录。
- 「API 密钥」页填**真实或 OKX demo** 的 Key/Secret/Passphrase（模拟盘填 demo key、实盘填 live key）。
- 行情页应显示真实 K 线;交易页下单打到 OKX（sim=官方模拟盘 flag1 / live=官方实盘 flag0）。

## 6. 数据说明

- 全新部署 = 空数据库,本地 mock 测试数据不会带过来,线上从零开始的真实数据。
- mock 代码保留无害:`EXCHANGE_MODE=okx` 时不调用。

## 7. 仍需额外工作的点（接上 OKX 也不会自动变真）

- **C2C 商家挂单**:OKX 无公开广告列表接口,仍是内置示例,需接商户/私有接口。
- **回测历史数据**:回测引擎用 mockfeed 生成的历史;真实回测应把数据源换成 InfluxDB 存储的真实 K 线或 OKX 历史（引擎逻辑已就绪,仅换数据源）。
- **强平 MMR 档位**:已实现从 OKX position-tiers 拉取,连通后自动用实时档位。

## 8. 运维提示

- 数据卷（pgdata/influxdata/redisdata/frontend_dist/strategy_scripts）挂在宿主机,`down` 不加 `-v` 不会丢数据。
- celery-worker 挂了宿主机 docker.sock 以动态起策略容器——确保服务器 Docker 权限正常。
- 定期备份 postgres 卷。
