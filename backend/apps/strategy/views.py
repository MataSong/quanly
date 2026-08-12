from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response

import secrets

from apps.credentials.models import ExchangeCredential

from .builtins import BUILTINS
from .models import Strategy, StrategyLog, StrategyRun
from .pnl import run_pnl
from .serializers import StrategyRunSerializer, StrategySerializer
from .tasks import run_strategy_task, stop_strategy_task
from .visual.generate import generate_source
from .visual.schemas import SCHEMAS


def _seed_builtins(user):
    # 按名字补齐缺失的内置策略(老用户也能拿到新增的内置策略)
    existing = set(
        Strategy.objects.filter(user=user, kind=Strategy.Kind.BUILTIN).values_list(
            "name", flat=True
        )
    )
    for b in BUILTINS:
        if b["name"] not in existing:
            Strategy.objects.create(
                user=user, name=b["name"], source=b["source"], kind=Strategy.Kind.BUILTIN
            )


class StrategyViewSet(viewsets.ModelViewSet):
    serializer_class = StrategySerializer

    def get_queryset(self):
        _seed_builtins(self.request.user)
        return Strategy.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        mode = serializer.validated_data.get("mode", "code")
        vc = serializer.validated_data.get("visual_config")
        if mode == "visual" and vc and vc.get("kind"):
            src = generate_source(vc["kind"], vc.get("config") or {})
            serializer.save(user=self.request.user, kind=Strategy.Kind.UPLOADED, source=src)
        else:
            serializer.save(user=self.request.user, kind=Strategy.Kind.UPLOADED)

    def perform_update(self, serializer):
        mode = serializer.validated_data.get("mode", getattr(serializer.instance, "mode", "code"))
        vc = serializer.validated_data.get("visual_config")
        if mode == "visual" and vc and vc.get("kind"):
            src = generate_source(vc["kind"], vc.get("config") or {})
            serializer.save(source=src)
        else:
            serializer.save()


@api_view(["POST"])
def run_strategy(request, pk):
    strategy = get_object_or_404(Strategy, pk=pk, user=request.user)
    env = request.data.get("env", "sim")
    cred_id = request.data.get("credential_id")
    credential = None
    if cred_id:
        credential = get_object_or_404(ExchangeCredential, pk=cred_id, user=request.user)
    symbol = request.data.get("symbol", "BTC-USDT")
    if not symbol or not str(symbol).strip():
        return Response({"detail_key": "strategy.launch.err.symbol_required"}, status=400)
    try:
        interval = int(request.data.get("interval_sec", 5))
    except (TypeError, ValueError):
        return Response({"detail_key": "strategy.launch.err.interval_invalid"}, status=400)
    if not (1 <= interval <= 3600):
        return Response({"detail_key": "strategy.launch.err.interval_invalid"}, status=400)
    run = StrategyRun.objects.create(
        user=request.user,
        strategy=strategy,
        env=env,
        credential=credential,
        symbol=str(symbol).strip(),
        interval_sec=interval,
    )
    # 派发 celery 任务启动容器(P4-3);celery 不可用时置 error 并提示
    try:
        from .tasks import run_strategy_task

        run_strategy_task.delay(run.id)
    except Exception as e:  # noqa
        run.status = StrategyRun.Status.ERROR
        run.save()
        return Response({"detail": f"调度失败: {e}", "run": StrategyRunSerializer(run).data}, status=500)
    return Response(StrategyRunSerializer(run).data, status=201)


@api_view(["POST"])
def stop_strategy(request, pk):
    run = get_object_or_404(StrategyRun, pk=pk, user=request.user)
    try:
        from .tasks import stop_strategy_task

        stop_strategy_task.delay(run.id)
    except Exception:
        pass
    run.status = StrategyRun.Status.STOPPED
    run.stopped_at = timezone.now()
    run.save()
    return Response(StrategyRunSerializer(run).data)


@api_view(["GET"])
def list_runs(request):
    qs = StrategyRun.objects.filter(user=request.user)
    strategy_id = request.query_params.get("strategy")
    if strategy_id:
        qs = qs.filter(strategy_id=strategy_id)
    return Response(StrategyRunSerializer(qs[:100], many=True).data)


@api_view(["GET"])
def run_logs(request, pk):
    run = get_object_or_404(StrategyRun, pk=pk, user=request.user)
    logs = StrategyLog.objects.filter(run=run)[:500]
    return Response(
        [{"level": l.level, "message": l.message, "ts": l.ts.isoformat()} for l in logs]
    )


@api_view(["POST"])
def batch_run(request):
    template_id = request.data.get("template_id")
    strategy = get_object_or_404(Strategy, pk=template_id, user=request.user)
    symbols = request.data.get("symbols") or []
    if not isinstance(symbols, list) or not symbols:
        return Response({"detail_key": "strategy.launch.err.symbol_required"}, status=400)
    env = request.data.get("env", "sim")
    cred_id = request.data.get("credential_id")
    credential = None
    if cred_id:
        credential = get_object_or_404(ExchangeCredential, pk=cred_id, user=request.user)
    try:
        interval = int(request.data.get("interval_sec", 5))
    except (TypeError, ValueError):
        return Response({"detail_key": "strategy.launch.err.interval_invalid"}, status=400)
    if not (1 <= interval <= 3600):
        return Response({"detail_key": "strategy.launch.err.interval_invalid"}, status=400)

    batch_id = secrets.token_hex(8)
    created = []
    for sym in symbols:
        if not str(sym).strip():
            continue
        run = StrategyRun.objects.create(
            user=request.user, strategy=strategy, env=env, credential=credential,
            symbol=str(sym).strip(), interval_sec=interval, batch_id=batch_id,
        )
        try:
            run_strategy_task.delay(run.id)
        except Exception:  # noqa
            run.status = StrategyRun.Status.ERROR
            run.save()
        created.append(run)
    return Response(
        {"batch_id": batch_id, "runs": StrategyRunSerializer(created, many=True).data},
        status=201,
    )


@api_view(["GET"])
def tasks_overview(request):
    qs = StrategyRun.objects.filter(user=request.user).select_related("strategy")
    groups = {}
    for run in qs[:300]:
        key = run.batch_id or f"single-{run.id}"
        g = groups.setdefault(key, {
            "batch_id": run.batch_id, "template_name": run.strategy.name,
            "env": run.env, "runs": [],
        })
        row = StrategyRunSerializer(run).data
        row["pnl"] = run_pnl(run)
        g["runs"].append(row)
    return Response(list(groups.values()))


@api_view(["POST"])
def batch_stop(request):
    batch_id = request.data.get("batch_id")
    if not batch_id:
        return Response({"detail": "batch_id required"}, status=400)
    runs = StrategyRun.objects.filter(user=request.user, batch_id=batch_id)
    for run in runs:
        try:
            stop_strategy_task.delay(run.id)
        except Exception:
            pass
        run.status = StrategyRun.Status.STOPPED
        run.stopped_at = timezone.now()
        run.save()
    return Response({"stopped": runs.count()})


@api_view(["GET"])
def visual_schemas(request):
    return Response(SCHEMAS)


@api_view(["POST"])
def visual_preview(request):
    kind = request.data.get("kind")
    config = request.data.get("config") or {}
    try:
        source = generate_source(kind, config)
    except Exception as e:  # noqa
        return Response({"detail": str(e)}, status=400)
    return Response({"source": source})


@api_view(["POST"])
def code_validate(request):
    source = request.data.get("source", "")
    try:
        compile(source, "strategy.py", "exec")
        return Response({"ok": True})
    except SyntaxError as e:
        return Response({"ok": False, "error": str(e), "lineno": e.lineno}, status=400)


@api_view(["POST"])
def code_dryrun(request):
    source = request.data.get("source", "")
    symbol = request.data.get("symbol", "BTC-USDT")
    bar = request.data.get("bar", "1m")
    try:
        bars = int(request.data.get("bars", 120))
    except (TypeError, ValueError):
        bars = 120
    from apps.backtest.engine import run_backtest

    try:
        result = run_backtest(source, symbol=symbol, bar=bar, bars=bars)
        logs = result.get("logs", [])[:50]
        return Response({"logs": logs})
    except Exception as e:  # noqa
        return Response({"logs": [], "error": str(e)}, status=200)
