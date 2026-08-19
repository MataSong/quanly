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
# UC-T7 安全边界:策略容器只接入一个 internal(不通外网)网络,该网络里只有 backend
# 可达(backend 双网络:default 连 postgres/redis,isolated 供策略容器回调 runner API)。
# 用户代码因此:不通外网(internal)、不通 postgres/redis/market-collector(它们只在 default)。
# compose 网络实际名带项目前缀,故用 STRATEGY_DOCKER_NETWORK 让部署时传入实际名(见 docker-compose.yml
# 的 celery-worker environment)。默认值是 compose 项目名 quanly 前缀下的合理猜测。
_STRATEGY_NETWORK = os.environ.get(
    "STRATEGY_DOCKER_NETWORK", "quanly_strategy_isolated"
)


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
    from core.strategy.models import StrategyRun

    try:
        run = StrategyRun.objects.select_related("strategy", "credential").get(pk=run_id)
    except StrategyRun.DoesNotExist:
        logger.error("run_strategy: StrategyRun %s not found", run_id)
        return

    # M5: 提前 guard —— 无 credential 无法下单,直接标 error 早失败,不起容器。
    if run.credential is None:
        logger.error("run_strategy: run=%s has no credential, aborting", run_id)
        run.status = StrategyRun.STATUS_ERROR
        run.save(update_fields=["status"])
        return

    # Generate a fresh token and atomically update the hash.
    # M1: status 先不置 RUNNING —— 等容器真正起来后再置,避免 docker.run 失败前的窗口里
    #     token 已能通过 resolve_run(status=running)。
    plain_token = generate_token()
    run.run_token_hash = hash_token(plain_token)
    run.save(update_fields=["run_token_hash"])

    # Build the environment dict injected into the container.
    # CRITICAL: only RUN_TOKEN + config — NO credential keys.
    container_env = {
        "RUN_TOKEN": plain_token,          # only safe token, not a key
        "BACKEND_URL": _BACKEND_URL,
        # 用户参数化实例跑 template_ref 指向的内置模板代码;内置策略用自身 code_ref。
        "CODE_REF": run.strategy.template_ref or run.strategy.code_ref,
        "SYMBOL": run.symbol,
        "PARAMS": json.dumps(run.params),
    }

    # UC-T7: source_type=code(用户自写脚本)→ 注入 USER_CODE,runner(T6)以受控 exec 执行。
    # runner 有 USER_CODE 时优先,CODE_REF 无意义;builtin/template 不注入,走 CODE_REF(现状)。
    if run.strategy.source_type == run.strategy.SOURCE_CODE:
        container_env["USER_CODE"] = run.strategy.code

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
            security_opt=["no-new-privileges:true"],  # 安全加固:禁止提权
            pids_limit=128,        # UC-T7: 防 fork 炸弹
            network=_STRATEGY_NETWORK,
            # Temporary writable tmpfs so the runner can write temp files.
            tmpfs={"/tmp": "size=64m,mode=1777"},
        )
        # M1: 容器成功启动后才置 RUNNING(token 此时才生效)。
        run.container_id = container.id
        run.status = StrategyRun.STATUS_RUNNING
        run.save(update_fields=["container_id", "status"])
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
