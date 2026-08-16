"""Celery tasks for strategy lifecycle management.

RUN_TOKEN design:
  - At start time, a fresh token is generated and the StrategyRun's
    run_token_hash is updated atomically.
  - The plaintext token is passed ONLY as a Docker environment variable.
  - It is NEVER stored in the database or logged.
  - No credential keys are injected — the container authenticates with
    RUN_TOKEN and calls back to the backend to trade/get market data.
"""
import json
import logging
import os

from config import celery_app
from core.strategy.run_token import generate_token, hash_token

logger = logging.getLogger("quanly.strategy")

# Backend URL injected into containers so they know where to call back.
_BACKEND_URL = os.environ.get("STRATEGY_BACKEND_URL", "http://backend:8000")
# Docker network the strategy container joins so it can reach the backend.
_STRATEGY_NETWORK = os.environ.get("STRATEGY_DOCKER_NETWORK", "quanly_default")


@celery_app.task(bind=True, name="core.strategy.run_strategy")
def run_strategy(self, run_id: int):
    """Start a strategy runner Docker container for the given StrategyRun.

    Steps:
      1. Load the StrategyRun (must be pending/stopped/error).
      2. Generate a fresh plaintext token + update hash in DB (atomic).
      3. Launch quanly-strategy-runner container with ONLY safe env vars.
      4. Record container_id and set status=running.

    The plaintext token is used ONCE here and then discarded — it exists
    only in memory during this function and in the container's env.
    """
    import django
    django.setup()  # noqa: ensure Django is ready in worker context

    from core.strategy.models import StrategyRun

    try:
        run = StrategyRun.objects.select_related("strategy", "credential").get(pk=run_id)
    except StrategyRun.DoesNotExist:
        logger.error("run_strategy: StrategyRun %s not found", run_id)
        return

    # Generate a fresh token and atomically update the hash.
    plain_token = generate_token()
    run.run_token_hash = hash_token(plain_token)
    run.status = StrategyRun.STATUS_RUNNING
    run.save(update_fields=["run_token_hash", "status"])

    # Build the environment dict injected into the container.
    # CRITICAL: only RUN_TOKEN + config — NO credential keys.
    container_env = {
        "RUN_TOKEN": plain_token,          # only safe token, not a key
        "BACKEND_URL": _BACKEND_URL,
        "CODE_REF": run.strategy.code_ref,
        "SYMBOL": run.symbol,
        "PARAMS": json.dumps(run.params),
    }

    logger.info(
        "run_strategy: starting container for run=%s strategy=%s symbol=%s env_keys=%s",
        run_id,
        run.strategy.code_ref,
        run.symbol,
        list(container_env.keys()),
    )

    try:
        import docker  # type: ignore[import]

        client = docker.from_env()
        container = client.containers.run(
            "quanly-strategy-runner",
            detach=True,
            environment=container_env,
            mem_limit="256m",
            cpu_quota=50000,       # 50% of one CPU
            cap_drop=["ALL"],
            read_only=True,
            network=_STRATEGY_NETWORK,
            # Temporary writable tmpfs so the runner can write temp files.
            tmpfs={"/tmp": "size=64m,mode=1777"},
        )
        run.container_id = container.id
        run.save(update_fields=["container_id"])
        logger.info(
            "run_strategy: container started id=%s run=%s", container.id[:12], run_id
        )
    except Exception as exc:
        logger.error("run_strategy: failed to start container run=%s: %s", run_id, exc)
        run.status = StrategyRun.STATUS_ERROR
        run.save(update_fields=["status"])
        raise


@celery_app.task(bind=True, name="core.strategy.stop_strategy")
def stop_strategy(self, run_id: int):
    """Stop and remove the Docker container for the given StrategyRun."""
    import django
    django.setup()  # noqa

    from core.strategy.models import StrategyRun

    try:
        run = StrategyRun.objects.get(pk=run_id)
    except StrategyRun.DoesNotExist:
        logger.error("stop_strategy: StrategyRun %s not found", run_id)
        return

    if run.container_id:
        try:
            import docker  # type: ignore[import]

            client = docker.from_env()
            try:
                container = client.containers.get(run.container_id)
                container.stop(timeout=10)
                container.remove(force=True)
                logger.info(
                    "stop_strategy: container stopped+removed id=%s run=%s",
                    run.container_id[:12],
                    run_id,
                )
            except docker.errors.NotFound:
                logger.warning(
                    "stop_strategy: container %s not found (already gone?)",
                    run.container_id[:12],
                )
        except Exception as exc:
            logger.error(
                "stop_strategy: error stopping container run=%s: %s", run_id, exc
            )

    run.status = StrategyRun.STATUS_STOPPED
    run.save(update_fields=["status"])
    logger.info("stop_strategy: run=%s status=stopped", run_id)
