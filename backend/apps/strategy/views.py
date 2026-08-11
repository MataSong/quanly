from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.credentials.models import ExchangeCredential

from .builtins import BUILTINS
from .models import Strategy, StrategyLog, StrategyRun
from .serializers import StrategyRunSerializer, StrategySerializer


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
        serializer.save(user=self.request.user, kind=Strategy.Kind.UPLOADED)


@api_view(["POST"])
def run_strategy(request, pk):
    strategy = get_object_or_404(Strategy, pk=pk, user=request.user)
    env = request.data.get("env", "sim")
    cred_id = request.data.get("credential_id")
    credential = None
    if cred_id:
        credential = get_object_or_404(ExchangeCredential, pk=cred_id, user=request.user)
    run = StrategyRun.objects.create(
        user=request.user,
        strategy=strategy,
        env=env,
        credential=credential,
        symbol=request.data.get("symbol", "BTC-USDT"),
        interval_sec=int(request.data.get("interval_sec", 5)),
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
