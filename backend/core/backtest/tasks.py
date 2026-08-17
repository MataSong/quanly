"""Celery tasks for the backtest app."""
import logging

from config import celery_app

# Import data/engine at module level so they are patchable in tests.
# These modules have no Django model imports so they are safe to import early.
from core.backtest.data import fetch_range
from core.backtest.engine import run as engine_run

logger = logging.getLogger("quanly.backtest")


@celery_app.task(bind=True, name="core.backtest.run_backtest", max_retries=0)
def run_backtest(self, backtest_id: int) -> None:
    """Fetch historical candles from OKX, run the backtest engine, persist results.

    Steps:
      1. Load Backtest record.
      2. Set status = running.
      3. Fetch candles via fetch_range (real OKX call).
      4. Run engine.run() — pure simulation, no OKX calls inside.
      5. Persist metrics, equity_curve, and BacktestTrade rows.
      6. Set status = done.

    On any exception: set status = error, record error_msg.
    """
    # Model imports stay lazy to avoid Django app-registry issues at import time.
    from core.backtest.models import Backtest, BacktestTrade

    try:
        bt = Backtest.objects.select_related("strategy").get(pk=backtest_id)
    except Backtest.DoesNotExist:
        logger.error("run_backtest: Backtest %s not found", backtest_id)
        return

    bt.status = Backtest.STATUS_RUNNING
    bt.save(update_fields=["status"])
    logger.info("run_backtest: starting backtest=%s strategy=%s", bt.pk, bt.strategy.code_ref)

    try:
        candles = fetch_range(
            symbol=bt.symbol,
            bar=bt.bar,
            start_ts=bt.start_ts,
            end_ts=bt.end_ts,
        )

        # 拉不到历史数据 → 报错(区分"OKX无数据/连不上"与"真的无信号"),不静默成 done。
        if not candles:
            raise RuntimeError(
                f"No historical candles for {bt.symbol} {bt.bar} in the given range "
                "(OKX unreachable or no data)."
            )

        result = engine_run(
            code_ref=bt.strategy.code_ref,
            params=bt.params,
            candles=candles,
            init_cash=float(bt.init_cash),
            fee_rate=float(bt.fee_rate),
            bar=bt.bar,
        )

        bt.equity_curve = result["equity_curve"]
        bt.metrics = result["metrics"]
        bt.status = Backtest.STATUS_DONE
        bt.save(update_fields=["equity_curve", "metrics", "status"])

        # Bulk-create trade rows.
        trades_to_create = [
            BacktestTrade(
                backtest=bt,
                side=t["side"],
                ts=t["ts"],
                price=t["price"],
                sz=t["sz"],
                fee=t["fee"],
                pnl=t.get("pnl", 0.0),
            )
            for t in result["trades"]
        ]
        if trades_to_create:
            BacktestTrade.objects.bulk_create(trades_to_create)

        logger.info(
            "run_backtest: done backtest=%s trades=%d equity_points=%d metrics=%s",
            bt.pk,
            len(trades_to_create),
            len(result["equity_curve"]),
            result["metrics"],
        )

    except Exception as exc:
        logger.exception("run_backtest: error backtest=%s: %s", bt.pk, exc)
        bt.status = Backtest.STATUS_ERROR
        bt.error_msg = str(exc)
        bt.save(update_fields=["status", "error_msg"])
        raise
