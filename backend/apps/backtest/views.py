import json

from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.strategy.models import Strategy

from .engine import BacktestError, run_backtest
from .metrics import compute_metrics
from .models import Backtest


@api_view(["POST"])
def run(request):
    d = request.data
    source = d.get("source")
    strategy = None
    if d.get("strategy_id"):
        strategy = get_object_or_404(Strategy, pk=d["strategy_id"], user=request.user)
        source = strategy.source
    if not source:
        return Response({"detail": "需要 strategy_id 或 source"}, status=400)

    symbol = d.get("symbol", "BTC-USDT")
    bar = d.get("bar", "1m")
    bars = int(d.get("bars", 500))
    initial_capital = float(d.get("initial_capital", 10000))
    fee_rate = float(d.get("fee_rate", 0.0005))

    try:
        result = run_backtest(source, symbol, bar, bars, initial_capital, fee_rate)
        metrics = compute_metrics(result, bar)
    except BacktestError as e:
        return Response({"detail": str(e)}, status=400)
    except Exception as e:  # noqa: BLE001
        return Response({"detail": f"回测执行失败:{e}"}, status=500)
    payload = {"result": result, "metrics": metrics}

    bt = Backtest.objects.create(
        user=request.user,
        strategy=strategy,
        name=strategy.name if strategy else "自定义脚本",
        symbol=symbol,
        bar=bar,
        bars=bars,
        initial_capital=initial_capital,
        fee_rate=fee_rate,
        result_json=json.dumps(payload),
    )
    return Response({"id": bt.id, "name": bt.name, **payload}, status=201)


@api_view(["GET"])
def list_backtests(request):
    qs = Backtest.objects.filter(user=request.user)[:50]
    return Response(
        [
            {
                "id": b.id,
                "name": b.name,
                "symbol": b.symbol,
                "bar": b.bar,
                "bars": b.bars,
                "created_at": b.created_at.isoformat(),
            }
            for b in qs
        ]
    )


@api_view(["GET"])
def detail(request, pk):
    b = get_object_or_404(Backtest, pk=pk, user=request.user)
    payload = json.loads(b.result_json) if b.result_json else {}
    return Response({"id": b.id, "name": b.name, "symbol": b.symbol, **payload})
