FROM python:3.12-slim

# 设置工作目录
WORKDIR /app

# 系统依赖（psycopg 需要 libpq）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 先拷贝 requirements，利用 Docker layer 缓存
COPY requirements.txt .

# 用清华镜像安装 Python 依赖（PyPI 官方源可能挂起）
RUN pip install --no-cache-dir \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    -r requirements.txt \
    gunicorn

# 拷贝应用代码
COPY . .

# 收集静态文件（QUANLY_ENV=prod 会校验 SECRET_KEY，用 dev 跑 collectstatic 足够）
RUN QUANLY_ENV=dev QUANLY_SECRET_KEY=build-placeholder DJANGO_SETTINGS_MODULE=config.settings.dev \
    python manage.py collectstatic --noinput

EXPOSE 8000

# 启动脚本（迁移 + seed + gunicorn）
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]
