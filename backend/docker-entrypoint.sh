#!/bin/sh
set -e

echo "[entrypoint] Running migrate..."
python manage.py migrate --noinput

echo "[entrypoint] Seeding admin..."
python manage.py seed_admin

echo "[entrypoint] Starting daphne (ASGI)..."
exec daphne -b 0.0.0.0 -p 8000 config.asgi:application
