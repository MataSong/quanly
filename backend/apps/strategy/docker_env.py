"""从运行环境推导策略容器所需的 docker 项目名/卷名/网络名。

celery-worker 自身也是 compose 起的容器,带 label com.docker.compose.project,
据此拿到真实项目名,拼出正确的卷名/网络名——不再硬编码假设项目名为 quanly。
"""
import os
import socket

from django.conf import settings

_cache = {}


def reset_cache():
    _cache.clear()


def _get_client(client):
    if client is not None:
        return client
    import docker

    return docker.from_env()


def compose_project(client=None) -> str:
    if "project" in _cache:
        return _cache["project"]
    project = None
    try:
        c = _get_client(client)
        self_container = c.containers.get(socket.gethostname())
        project = self_container.labels.get("com.docker.compose.project")
    except Exception:
        project = None
    if not project:
        project = os.environ.get("COMPOSE_PROJECT_NAME") or "quanly"
    _cache["project"] = project
    return project


def scripts_volume_name(client=None) -> str:
    return f"{compose_project(client)}_strategy_scripts"


def strategy_network_name(client=None) -> str:
    # 若用户显式覆盖(非默认 quanly_default),尊重其配置;否则按项目名推导
    configured = getattr(settings, "STRATEGY_DOCKER_NETWORK", "")
    if configured and configured != "quanly_default":
        return configured
    return f"{compose_project(client)}_default"
