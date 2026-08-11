import pytest
from decimal import Decimal

from apps.trading import sync
from apps.trading.models import Balance


@pytest.mark.django_db
def test_upsert_balances_writes_rows(django_user_model):
    user = django_user_model.objects.create(username="u1")
    rows = [
        type("B", (), {"ccy": "USDT", "total": 1000.0, "available": 900.0, "frozen": 100.0})(),
        type("B", (), {"ccy": "BTC", "total": 0.5, "available": 0.5, "frozen": 0.0})(),
    ]
    sync.upsert_balances(user, "sim", rows)
    usdt = Balance.objects.get(user=user, env="sim", ccy="USDT")
    assert usdt.total == Decimal("1000.0")
    assert usdt.frozen == Decimal("100.0")
    assert Balance.objects.filter(user=user, env="sim").count() == 2
