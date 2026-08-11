from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.trading.models import Bill

from .service import summarize


@api_view(["GET"])
def summary(request):
    env = request.query_params.get("env", "sim")
    return Response(summarize(request.user, env))


@api_view(["GET"])
def bills(request):
    env = request.query_params.get("env", "sim")
    limit = int(request.query_params.get("limit", 100))
    qs = Bill.objects.filter(user=request.user, env=env)[:limit]
    data = [
        {
            "id": b.id,
            "bill_type": b.bill_type,
            "ccy": b.ccy,
            "amount": float(b.amount),
            "symbol": b.symbol,
            "balance_after": float(b.balance_after),
            "ts": b.ts.isoformat(),
        }
        for b in qs
    ]
    return Response(data)
