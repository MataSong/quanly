import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


# ---------------------------------------------------------------------------
# Debug / infra-verification tasks (no business logic — P3-A only)
# ---------------------------------------------------------------------------

@app.task(bind=True, name="config.ping")
def ping(self):
    """Heartbeat task: returns 'pong'. Used to verify Celery worker is alive."""
    return "pong"


@app.task(bind=True, name="config.docker_hello")
def docker_hello(self):
    """
    Verify Docker-out-of-Docker (DooD) works inside celery-worker container.
    Requires /var/run/docker.sock to be mounted (see docker-compose.yml).
    Will fail gracefully with an error string if docker.sock is unavailable.
    """
    try:
        import docker  # noqa: PLC0415
        client = docker.from_env()
        output = client.containers.run("hello-world", remove=True)
        return output.decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: {exc}"
