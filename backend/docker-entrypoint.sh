#!/bin/sh
set -e

# 如果 compose 传了自定义 command(如 celery worker),执行它,不跑 web 启动流程。
# 这样 backend/market-collector/celery-worker 复用同一镜像但各起各的进程。
if [ "$#" -gt 0 ]; then
    echo "[entrypoint] Running custom command: $*"
    exec "$@"
fi

echo "[entrypoint] Running migrate..."
python manage.py migrate --noinput

echo "[entrypoint] Seeding admin..."
python manage.py seed_admin

echo "[entrypoint] Seeding built-in strategies..."
python manage.py seed_builtin_strategies

echo "[entrypoint] Starting daphne (ASGI)..."
exec daphne -b 0.0.0.0 -p 8000 config.asgi:application
