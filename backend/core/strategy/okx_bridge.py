"""OKX bridge for strategy runner containers.

These functions are called by the strategy runner API endpoints when a
container needs market data or wants to place an order.  All secrets stay
on the backend — the container only knows its RUN_TOKEN.
"""
import logging

from core.strategy.models import StrategyRun

logger = logging.getLogger("quanly.strategy")


def runner_candles(run: StrategyRun, bar: str = "1m", limit: int = 100) -> list[dict]:
    """Fetch candlestick data for the run's symbol.

    Delegates to the public market API — no credential needed.
    Returns oldest-first list of {ts, o, h, l, c, vol, volCcy} dicts.
    """
    from core.market.okx_client import get_candles

    return get_candles(run.symbol, bar=bar, limit=limit)


def runner_place_order(
    run: StrategyRun,
    side: str,
    sz: str,
    ord_type: str,
    px: str | None = None,
) -> str:
    """Place an order on behalf of a strategy run.

    Uses run.credential for authentication — the credential's encrypted
    keys are decrypted inside okx_ext.place_order; they are never exposed
    to the runner container.

    Creates a StrategyOrder record linking the order to the run.

    Returns the OKX ordId string.
    Raises RuntimeError if OKX rejects the order.
    """
    from core.trading.okx_ext import place_order
    from core.strategy.models import StrategyOrder

    cred = run.credential
    if cred is None:
        raise RuntimeError("StrategyRun has no credential attached.")

    logger.info(
        "runner_place_order run=%s symbol=%s side=%s sz=%s ord_type=%s",
        run.pk,
        run.symbol,
        side,
        sz,
        ord_type,
    )

    okx_data = place_order(
        cred,
        inst_type="SPOT",
        inst_id=run.symbol,
        side=side,
        ord_type=ord_type,
        sz=sz,
        px=px,
    )

    ord_id = okx_data.get("ordId", "")
    cl_ord_id = okx_data.get("clOrdId", "")

    # Persist the order linked to the strategy run.
    StrategyOrder.objects.create(
        run=run,
        user=run.user,
        credential=cred,
        env=cred.env,
        inst_type="SPOT",
        inst_id=run.symbol,
        side=side,
        ord_type=ord_type,
        sz=sz,
        px=px or "",
        td_mode="cash",  # SPOT always uses cash
        okx_ord_id=ord_id,
        cl_ord_id=cl_ord_id,
    )

    logger.info("runner_place_order succeeded ordId=%s run=%s", ord_id, run.pk)
    return ord_id
