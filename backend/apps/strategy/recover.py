"""worker/backend 重启后恢复运行中的策略。

扫 DB 中 status=RUNNING 的 StrategyRun:容器还活着则对齐(不动),
容器已死(NotFound/exited)则自动重拉同参数容器。幂等,可重复执行。
"""
from .models import StrategyRun


def _get_client(client):
    if client is not None:
        return client
    import docker

    return docker.from_env()


def recover_running_runs(client=None) -> dict:
    from . import tasks

    c = _get_client(client)
    result = {"alive": 0, "relaunched": 0, "failed": 0}
    runs = StrategyRun.objects.filter(status=StrategyRun.Status.RUNNING)
    for run in runs:
        name = f"quanly-strategy-{run.id}"
        alive = False
        try:
            container = c.containers.get(name)
            alive = getattr(container, "status", "") == "running"
        except Exception:
            alive = False
        if alive:
            result["alive"] += 1
            continue
        try:
            container = tasks._launch_container(run)
            if container is not None and getattr(container, "id", None):
                run.container_id = container.id
                run.save(update_fields=["container_id"])
            result["relaunched"] += 1
            tasks._publish_log(run.id, "worker 重启,策略已自动恢复", "info")
        except Exception as e:  # noqa
            run.status = StrategyRun.Status.ERROR
            run.save(update_fields=["status"])
            result["failed"] += 1
            tasks._publish_log(run.id, f"恢复失败: {e}", "error")
    return result
