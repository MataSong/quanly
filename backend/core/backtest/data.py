"""Historical candle data fetcher — real OKX only, no mock/fallback.

Uses get_history_candles() with backward pagination to cover an arbitrary
time range.  Raises if OKX is unreachable; callers should handle the error.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("quanly.backtest.data")

# Safety cap: never paginate more than this many pages to avoid runaway loops.
# 100 candles/page × 500 pages = 50 000 bars max per fetch.
_MAX_PAGES = 500


def fetch_range(
    symbol: str,
    bar: str,
    start_ts: int,
    end_ts: int,
) -> list[dict[str, Any]]:
    """Fetch all candles in [start_ts, end_ts] from OKX (inclusive, milliseconds).

    Strategy:
      1. Call get_history_candles without ``after`` to get the most-recent page
         that ends at or before end_ts.  Actually OKX history endpoint always
         returns the newest available bars, so we walk backward using ``after``.
      2. Each page returns up to 100 candles newest-first; we keep going until
         the oldest candle on the page is older than start_ts or the page is empty.
      3. Deduplicate by ts, sort ascending, and filter to [start_ts, end_ts].

    Raises RuntimeError if OKX returns an error (real connectivity issue).
    """
    # Lazy import so the module can be imported without Django being configured
    # (e.g. for pure-function unit tests that mock this module).
    from core.market.okx_client import get_history_candles

    all_candles: dict[int, dict[str, Any]] = {}
    # Start walking backward from just after end_ts so the first page covers
    # the end of the requested window.
    after: str | None = str(end_ts + 1)
    pages_fetched = 0

    while pages_fetched < _MAX_PAGES:
        page = get_history_candles(symbol=symbol, bar=bar, after=after, limit=100)
        pages_fetched += 1

        if not page:
            # OKX returned empty page — no more historical data available.
            break

        for candle in page:
            ts = int(candle["ts"])
            all_candles[ts] = candle

        # page is oldest-first after get_history_candles reverses it.
        oldest_ts = int(page[0]["ts"])

        if oldest_ts <= start_ts:
            # We've reached (or passed) the start of our window — done.
            break

        # Advance cursor: ask for data strictly before the oldest candle we have.
        after = str(oldest_ts)

    if not all_candles:
        logger.warning(
            "fetch_range: no candles returned from OKX for %s %s [%d, %d]",
            symbol, bar, start_ts, end_ts,
        )
        return []

    # Sort by timestamp ascending, then filter to the requested window.
    sorted_candles = sorted(all_candles.values(), key=lambda c: int(c["ts"]))
    result = [c for c in sorted_candles if start_ts <= int(c["ts"]) <= end_ts]

    logger.info(
        "fetch_range: fetched %d candles (%d pages) for %s %s [%d, %d]",
        len(result), pages_fetched, symbol, bar, start_ts, end_ts,
    )
    return result
