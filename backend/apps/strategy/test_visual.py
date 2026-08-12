import pytest


def test_generate_ma_cross_compiles():
    from apps.strategy.visual.generate import generate_source
    src = generate_source("ma_cross", {"short": 3, "long": 10, "size": 0.001})
    assert "def on_tick(ctx):" in src
    compile(src, "gen.py", "exec")


def test_generate_all_kinds_compile():
    from apps.strategy.visual.generate import generate_source
    from apps.strategy.visual.schemas import SCHEMAS
    defaults = {
        "ma_cross": {"short": 3, "long": 10, "size": 0.001},
        "grid": {"lower": 100, "upper": 200, "grids": 5, "size": 0.001},
        "dca": {"period": 12, "amount": 10},
        "tp_sl": {"tp_pct": 0.04, "sl_pct": 0.02, "size": 0.001},
    }
    for kind in SCHEMAS:
        src = generate_source(kind, defaults[kind])
        compile(src, f"{kind}.py", "exec")
        assert "on_tick" in src


def test_generate_rejects_unknown_kind():
    from apps.strategy.visual.generate import generate_source
    with pytest.raises(ValueError):
        generate_source("nope", {})


def test_visual_schemas_endpoint(db):
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient
    user = get_user_model().objects.create_user("d1", password="pass12345")
    c = APIClient(); c.force_authenticate(user)
    r = c.get("/api/strategy/visual/schemas")
    assert r.status_code == 200
    assert "ma_cross" in r.data


def test_visual_preview_endpoint(db):
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient
    user = get_user_model().objects.create_user("d2", password="pass12345")
    c = APIClient(); c.force_authenticate(user)
    r = c.post("/api/strategy/visual/preview",
               {"kind": "ma_cross", "config": {"short": 3, "long": 10, "size": 0.001}}, format="json")
    assert r.status_code == 200
    assert "def on_tick" in r.data["source"]


def test_code_validate_detects_syntax_error(db):
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient
    user = get_user_model().objects.create_user("d3", password="pass12345")
    c = APIClient(); c.force_authenticate(user)
    ok = c.post("/api/strategy/code/validate", {"source": "def on_tick(ctx):\n    pass"}, format="json")
    assert ok.status_code == 200 and ok.data["ok"] is True
    bad = c.post("/api/strategy/code/validate", {"source": "def on_tick(ctx:"}, format="json")
    assert bad.status_code == 400 and bad.data["ok"] is False


def test_create_visual_strategy_regenerates_source(db):
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient
    from apps.strategy.models import Strategy
    user = get_user_model().objects.create_user("d4", password="pass12345")
    c = APIClient(); c.force_authenticate(user)
    r = c.post("/api/strategies/", {
        "name": "vis", "source": "", "mode": "visual",
        "visual_config": {"kind": "ma_cross", "config": {"short": 3, "long": 10, "size": 0.001}},
    }, format="json")
    assert r.status_code == 201
    s = Strategy.objects.get(name="vis", user=user)
    assert s.mode == "visual"
    assert "def on_tick" in s.source
