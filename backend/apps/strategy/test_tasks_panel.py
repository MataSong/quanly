import pytest


def test_new_model_fields(db):
    from django.contrib.auth import get_user_model
    from apps.strategy.models import Strategy, StrategyRun

    user = get_user_model().objects.create_user("c1", password="pass12345")
    strat = Strategy.objects.create(user=user, name="s", source="x")
    assert strat.mode == "code"
    assert strat.visual_config is None
    assert strat.description == ""
    run = StrategyRun.objects.create(
        user=user, strategy=strat, env="sim", symbol="BTC-USDT"
    )
    assert run.batch_id == ""


def test_strategy_serializer_has_mode(db):
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient
    from apps.strategy.models import Strategy

    user = get_user_model().objects.create_user("c2", password="pass12345")
    Strategy.objects.create(user=user, name="s", source="x", mode="visual",
                            visual_config={"kind": "ma"}, description="d")
    c = APIClient(); c.force_authenticate(user)
    r = c.get("/api/strategies/")
    row = [s for s in r.data if s["name"] == "s"][0]
    assert row["mode"] == "visual"
    assert row["visual_config"] == {"kind": "ma"}
    assert row["description"] == "d"


def test_run_pnl_sums_close_bills(db):
    from django.contrib.auth import get_user_model
    from apps.strategy.models import Strategy, StrategyRun
    from apps.strategy.pnl import run_pnl

    user = get_user_model().objects.create_user("c3", password="pass12345")
    strat = Strategy.objects.create(user=user, name="s", source="x")
    run = StrategyRun.objects.create(user=user, strategy=strat, env="sim", symbol="BTC-USDT")
    assert run_pnl(run) == 0.0


def test_batch_run_creates_runs_with_shared_batch(db, monkeypatch):
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient
    from apps.strategy.models import Strategy, StrategyRun
    from apps.strategy import views

    monkeypatch.setattr(views, "run_strategy_task",
                        type("T", (), {"delay": staticmethod(lambda rid: None)}))

    user = get_user_model().objects.create_user("c4", password="pass12345")
    strat = Strategy.objects.create(user=user, name="s", source="x")
    c = APIClient(); c.force_authenticate(user)
    r = c.post("/api/strategy/tasks/batch-run",
               {"template_id": strat.id, "symbols": ["BTC-USDT", "ETH-USDT"], "env": "sim", "interval_sec": 5},
               format="json")
    assert r.status_code == 201
    batch_id = r.data["batch_id"]
    assert batch_id
    runs = StrategyRun.objects.filter(batch_id=batch_id)
    assert runs.count() == 2
    assert set(runs.values_list("symbol", flat=True)) == {"BTC-USDT", "ETH-USDT"}


def test_tasks_overview_groups_by_batch(db):
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient
    from apps.strategy.models import Strategy, StrategyRun

    user = get_user_model().objects.create_user("c5", password="pass12345")
    strat = Strategy.objects.create(user=user, name="s", source="x")
    StrategyRun.objects.create(user=user, strategy=strat, env="sim", symbol="BTC-USDT", batch_id="b1")
    StrategyRun.objects.create(user=user, strategy=strat, env="sim", symbol="ETH-USDT", batch_id="b1")
    c = APIClient(); c.force_authenticate(user)
    r = c.get("/api/strategy/tasks")
    assert r.status_code == 200
    grp = [g for g in r.data if g["batch_id"] == "b1"][0]
    assert len(grp["runs"]) == 2
    assert "pnl" in grp["runs"][0]


def test_batch_stop_stops_all(db, monkeypatch):
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient
    from apps.strategy.models import Strategy, StrategyRun
    from apps.strategy import views

    monkeypatch.setattr(views, "stop_strategy_task",
                        type("T", (), {"delay": staticmethod(lambda rid: None)}))
    user = get_user_model().objects.create_user("c6", password="pass12345")
    strat = Strategy.objects.create(user=user, name="s", source="x")
    for sym in ("BTC-USDT", "ETH-USDT"):
        StrategyRun.objects.create(user=user, strategy=strat, env="sim", symbol=sym,
                                   batch_id="b2", status=StrategyRun.Status.RUNNING)
    c = APIClient(); c.force_authenticate(user)
    r = c.post("/api/strategy/tasks/batch-stop", {"batch_id": "b2"}, format="json")
    assert r.status_code == 200
    assert r.data["stopped"] == 2
    assert StrategyRun.objects.filter(batch_id="b2", status="stopped").count() == 2
