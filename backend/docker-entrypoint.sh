#!/bin/sh
set -e

echo "[entrypoint] Running migrate..."
python manage.py migrate --noinput

echo "[entrypoint] Seeding admin..."
python manage.py seed_admin

echo "[entrypoint] Starting gunicorn..."
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-2}" \
    --timeout 120 \
    --log-level info \
    --access-logfile - \
    --error-logfile -
