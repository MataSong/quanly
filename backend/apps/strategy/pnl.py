"""策略运行的近似盈亏聚合。

近似口径:该 run 的 user+env+symbol 在 run 启动后的平仓盈亏(CLOSE_PNL)账单合计。
注:同一 symbol 若有手动单会混入,这是任务面板的近似展示,非精确 run 级隔离。
"""
from apps.trading.models import Bill


def run_pnl(run) -> float:
    qs = Bill.objects.filter(
        user=run.user,
        env=run.env,
        symbol=run.symbol,
        bill_type=Bill.BillType.CLOSE_PNL,
        ts__gte=run.started_at,
    )
    total = sum(float(b.amount) for b in qs)
    return round(total, 8)
