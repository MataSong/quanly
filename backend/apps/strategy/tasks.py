"""Celery 任务:用 Docker-out-of-Docker 启动/停止策略容器,并采集日志。

celery-worker 容器挂载宿主机 docker.sock;为每个 StrategyRun 动态 run 一个
strategy-runner 容器。用户脚本经共享卷 strategy_scripts 传入。
容器只拿到 RUN_TOKEN(拿不到真实密钥),网络限定 compose 网络,资源限额。
"""
import json
import os

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from . import docker_env
from .models import StrategyLog, StrategyRun

SCRIPTS_DIR = getattr(settings, "STRATEGY_SCRIPTS_DIR", "/scripts")  # 共享卷,worker 与 runner 都挂


def _classify_launch_error(exc) -> str:
    name = exc.__class__.__name__
    msg = str(exc).lower()
    if "imagenotfound" in name.lower() or "no such image" in msg or "pull access" in msg:
        return "image_not_found"
    if "volume" in msg:
        return "volume_error"
    if "network" in msg:
        return "network_error"
    return "unknown"


def _publish_log(run_id, message, level="info"):
    StrategyLog.objects.create(run_id=run_id, level=level, message=message)
    try:
        import redis

        r = redis.from_url(settings.REDIS_URL)
        r.publish(f"strategy:{run_id}", json.dumps({"level": level, "message": message}))
    except Exception:
        pass


def _launch_container(run):
    """起一个策略隔离容器并返回 container 对象。启动与恢复共用。"""
    import docker

    run_id = run.id
    os.makedirs(SCRIPTS_DIR, exist_ok=True)
    script_path = os.path.join(SCRIPTS_DIR, f"run_{run_id}.py")
    with open(script_path, "w") as f:
        f.write(run.strategy.source)

    client = docker.from_env()
    return client.containers.run(
        settings.STRATEGY_RUNNER_IMAGE,
        detach=True,
        name=f"quanly-strategy-{run_id}",
        environment={
            "RUN_ID": str(run_id),
            "RUN_TOKEN": run.run_token,
            "BACKEND_URL": settings.BACKEND_INTERNAL_URL,
            "SYMBOL": run.symbol,
            "INTERVAL": str(run.interval_sec),
            "SCRIPT_PATH": f"/scripts/run_{run_id}.py",
        },
        volumes={docker_env.scripts_volume_name(client): {"bind": "/scripts", "mode": "ro"}},
        network=docker_env.strategy_network_name(client),
        mem_limit="256m",
        nano_cpus=500_000_000,  # 0.5 CPU
        cap_drop=["ALL"],
        read_only=True,
        tmpfs={"/tmp": ""},
        restart_policy={"Name": "unless-stopped"},  # 容器自治:worker 重建/宿主重启后续跑
    )


@shared_task
def run_strategy_task(run_id):
    run = StrategyRun.objects.select_related("strategy").get(id=run_id)
    try:
        container = _launch_container(run)
    except Exception as e:  # noqa
        run.status = StrategyRun.Status.ERROR
        run.save()
        _publish_log(run_id, f"启动容器失败[{_classify_launch_error(e)}]: {e}", "error")
        return

    run.container_id = container.id
    run.status = StrategyRun.Status.RUNNING
    run.save()
    _publish_log(run_id, "策略容器已启动", "info")
    # 不再阻塞 attach 日志:日志由 runner 容器主动经 /api/strategy-api/log 上报。
    # worker 起容器后立即返回,释放并发槽,可并发启动多策略(支撑批量并行)。


@shared_task
def stop_strategy_task(run_id):
    import docker

    run = StrategyRun.objects.get(id=run_id)
    client = docker.from_env()
    try:
        c = client.containers.get(f"quanly-strategy-{run_id}")
        c.stop(timeout=3)
        c.remove(force=True)
    except Exception:
        pass
    run.status = StrategyRun.Status.STOPPED
    run.stopped_at = timezone.now()
    run.save()
    _publish_log(run_id, "策略已停止", "info")
