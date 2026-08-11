#!/usr/bin/env bash
set -e

python manage.py migrate --noinput
python manage.py collectstatic --noinput
gunicorn config.wsgi:application -b 0.0.0.0:8000 --workers 3
