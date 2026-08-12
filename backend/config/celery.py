import os

from celery import Celery
from celery.signals import worker_ready

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("quanly")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@worker_ready.connect
def _recover_on_worker_ready(**kwargs):
    try:
        from apps.strategy.recover import recover_running_runs

        recover_running_runs()
    except Exception:
        pass
