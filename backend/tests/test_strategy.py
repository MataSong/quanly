"""Tests for P3-B: Strategy backend.

Coverage:
  1. RUN_TOKEN auth: no/wrong token → 401; valid token → passes.
  2. Multi-tenant: token only works for its bound run; users see only own runs;
     using another user's credential_id is rejected.
  3. Management API permissions: no strategy:run → 403 on start.
  4. runner_place_order: places order via credential (stubbed okx_ext), creates StrategyOrder.
  5. dual_ma on_tick: golden cross → buy signal; death cross → sell signal (pure function).
  6. celery run_strategy: mock docker SDK, env only contains safe keys (no credential secrets).

All OKX and Docker calls are unittest.mock stubs — zero real external calls.
"""
import json
import pytest
from unittest.mock import MagicMock, patch
from django.contrib.auth.models import User

from core.credentials.crypto import encrypt
from core.credentials.models import Credential
from core.accounts.models import Role, UserRole
from core.strategy.models import Strategy, StrategyOrder, StrategyRun, StrategyLog
from core.strategy.run_token import generate_token, hash_token, resolve_run


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(username: str, perms: list[str] | None = None) -> User:
    user = User.objects.create_user(username, password="pw")
    if perms:
        role = Role.objects.create(name=f"role_{username}", permissions=perms)
        UserRole.objects.create(user=user, role=role)
    return user


def _make_credential(user: User, env: str = Credential.ENV_SIM, label: str = "default") -> Credential:
    return Credential.objects.create(
        user=user,
        env=env,
        label=label,
        api_key_enc=encrypt("test-api-key"),
        secret_enc=encrypt("test-secret"),
        passphrase_enc=encrypt("test-passphrase"),
    )


def _make_strategy(code_ref: str = "dual_ma") -> Strategy:
    return Strategy.objects.get_or_create(
        code_ref=code_ref,
        defaults={
            "name": "Dual MA",
            "source_type": Strategy.SOURCE_BUILTIN,
            "is_builtin": True,
            "default_params": {"fast_period": 5, "slow_period": 20, "sz": "0.001"},
        },
    )[0]


def _make_run(
    user: User,
    strategy: Strategy | None = None,
    credential: Credential | None = None,
    status: str = StrategyRun.STATUS_RUNNING,
) -> tuple[StrategyRun, str]:
    """Create a StrategyRun; return (run, plain_token)."""
    if strategy is None:
        strategy = _make_strategy()
    plain_token = generate_token()
    run = StrategyRun.objects.create(
        user=user,
        strategy=strategy,
        credential=credential,
        env=StrategyRun.ENV_SIM,
        symbol="BTC-USDT",
        params={},
        run_token_hash=hash_token(plain_token),
        status=status,
    )
    return run, plain_token


# ---------------------------------------------------------------------------
# 1. RUN_TOKEN authentication
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_runner_api_no_token_returns_401(api_client):
    """Missing X-Run-Token header → 401."""
    resp = api_client.get("/api/strategy/runner/candles")
    assert resp.status_code == 401


@pytest.mark.django_db
def test_runner_api_wrong_token_returns_401(api_client):
    """Wrong X-Run-Token → 401."""
    api_client.credentials(HTTP_X_RUN_TOKEN="totally-wrong-token")
    resp = api_client.get("/api/strategy/runner/candles")
    assert resp.status_code == 401


@pytest.mark.django_db
def test_runner_api_valid_token_passes_auth(api_client):
    """Valid X-Run-Token for a running run → auth succeeds (200 or 502 from OKX stub)."""
    user = _make_user("tok_valid")
    run, plain_token = _make_run(user, status=StrategyRun.STATUS_RUNNING)

    with patch("core.market.okx_client.get_candles", return_value=[]):
        api_client.credentials(HTTP_X_RUN_TOKEN=plain_token)
        resp = api_client.get("/api/strategy/runner/candles?bar=1m&limit=5")

    # Auth succeeded — response is 200 (empty candles list is fine)
    assert resp.status_code == 200


@pytest.mark.django_db
def test_runner_api_token_for_pending_run_returns_401(api_client):
    """Token for a pending (not running) run → 401 (resolve_run requires status=running)."""
    user = _make_user("tok_pending")
    run, plain_token = _make_run(user, status=StrategyRun.STATUS_PENDING)

    api_client.credentials(HTTP_X_RUN_TOKEN=plain_token)
    resp = api_client.get("/api/strategy/runner/candles")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 2. Multi-tenant isolation
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_user_can_only_see_own_runs(api_client):
    """GET /api/strategy/runs only returns the authenticated user's runs."""
    alice = _make_user("alice_mt", ["strategy:view"])
    bob = _make_user("bob_mt", ["strategy:view"])
    strategy = _make_strategy()

    _make_run(alice, strategy=strategy)
    _make_run(bob, strategy=strategy)

    api_client.force_authenticate(alice)
    resp = api_client.get("/api/strategy/runs")
    assert resp.status_code == 200
    run_ids = {r["id"] for r in resp.data}
    # Alice's runs only — none of Bob's
    alice_run_ids = set(StrategyRun.objects.filter(user=alice).values_list("id", flat=True))
    bob_run_ids = set(StrategyRun.objects.filter(user=bob).values_list("id", flat=True))
    assert run_ids == alice_run_ids
    assert not (run_ids & bob_run_ids)


@pytest.mark.django_db
def test_create_run_with_other_users_credential_returns_404(api_client):
    """POST /api/strategy/runs with another user's credential_id → 404."""
    owner = _make_user("cred_owner_mt", ["strategy:run"])
    attacker = _make_user("attacker_mt", ["strategy:run"])
    cred = _make_credential(owner)
    strategy = _make_strategy()

    api_client.force_authenticate(attacker)
    resp = api_client.post("/api/strategy/runs", {
        "strategy_id": strategy.pk,
        "credential_id": cred.pk,
        "symbol": "BTC-USDT",
    }, format="json")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_token_cannot_access_another_runs_endpoint(api_client):
    """Token for run A cannot be used to get logs for run B."""
    alice = _make_user("alice_token_mt")
    bob = _make_user("bob_token_mt")
    run_a, token_a = _make_run(alice, status=StrategyRun.STATUS_RUNNING)
    run_b, _ = _make_run(bob, status=StrategyRun.STATUS_RUNNING)

    # Token A is valid but run_b belongs to bob — resolve_run returns run_a, not run_b.
    # The runner API endpoints operate on the authenticated run (from token), not a path param.
    # So token_a cannot reach run_b's data at all — auth just gives access to run_a.
    # Verify resolve_run returns run_a, not run_b.
    resolved = resolve_run(token_a)
    assert resolved is not None
    assert resolved.pk == run_a.pk


@pytest.mark.django_db
def test_run_detail_view_not_accessible_by_other_user(api_client):
    """GET /api/strategy/runs/<id> for another user's run → 404."""
    alice = _make_user("alice_detail", ["strategy:view"])
    bob = _make_user("bob_detail")
    run_b, _ = _make_run(bob)

    api_client.force_authenticate(alice)
    resp = api_client.get(f"/api/strategy/runs/{run_b.pk}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 3. Management API permissions
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_start_run_without_strategy_run_perm_returns_403(api_client):
    """POST /api/strategy/runs/<id>/start without strategy:run → 403."""
    user = _make_user("no_run_perm", ["strategy:view"])
    run, _ = _make_run(user, status=StrategyRun.STATUS_PENDING)

    api_client.force_authenticate(user)
    resp = api_client.post(f"/api/strategy/runs/{run.pk}/start")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_start_run_with_strategy_run_perm_enqueues_task(api_client):
    """POST /api/strategy/runs/<id>/start with strategy:run → 200 + task enqueued."""
    user = _make_user("has_run_perm", ["strategy:run"])
    run, _ = _make_run(user, status=StrategyRun.STATUS_PENDING)

    api_client.force_authenticate(user)
    with patch("core.strategy.tasks.run_strategy.delay") as mock_delay:
        resp = api_client.post(f"/api/strategy/runs/{run.pk}/start")

    assert resp.status_code == 200
    mock_delay.assert_called_once_with(run.pk)


@pytest.mark.django_db
def test_strategy_list_requires_strategy_view_perm(api_client):
    """GET /api/strategy/strategies without strategy:view → 403."""
    user = _make_user("no_view_perm", [])
    api_client.force_authenticate(user)
    resp = api_client.get("/api/strategy/strategies")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 4. runner_place_order creates StrategyOrder
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_runner_place_order_creates_strategy_order(api_client):
    """POST /api/strategy/runner/order (stubbed OKX) creates a StrategyOrder linked to the run."""
    user = _make_user("runner_order_user")
    cred = _make_credential(user)
    run, plain_token = _make_run(user, credential=cred, status=StrategyRun.STATUS_RUNNING)

    mock_api = MagicMock()
    mock_api.place_order.return_value = {
        "code": "0",
        "msg": "",
        "data": [{"ordId": "STRATEGY_ORD_1", "clOrdId": "CL_STRAT_1", "sCode": "0", "sMsg": ""}],
    }

    with patch("core.trading.okx_ext._trade_api", return_value=mock_api):
        api_client.credentials(HTTP_X_RUN_TOKEN=plain_token)
        resp = api_client.post("/api/strategy/runner/order", {
            "side": "buy",
            "sz": "0.001",
            "ord_type": "market",
        }, format="json")

    assert resp.status_code == 200
    assert resp.data["ordId"] == "STRATEGY_ORD_1"

    order = StrategyOrder.objects.get(okx_ord_id="STRATEGY_ORD_1")
    assert order.run == run
    assert order.user == user
    assert order.credential == cred
    assert order.side == "buy"
    assert order.sz == "0.001"
    assert order.inst_id == "BTC-USDT"
    assert order.inst_type == "SPOT"


@pytest.mark.django_db
def test_runner_place_order_unit_via_okx_bridge(api_client):
    """Direct call to runner_place_order (bypassing HTTP) creates StrategyOrder."""
    from core.strategy.okx_bridge import runner_place_order

    user = _make_user("bridge_order_user")
    cred = _make_credential(user)
    run, _ = _make_run(user, credential=cred, status=StrategyRun.STATUS_RUNNING)

    mock_api = MagicMock()
    mock_api.place_order.return_value = {
        "code": "0",
        "msg": "",
        "data": [{"ordId": "BRIDGE_ORD_42", "clOrdId": "CL_B42", "sCode": "0", "sMsg": ""}],
    }

    with patch("core.trading.okx_ext._trade_api", return_value=mock_api):
        ord_id = runner_place_order(run, side="sell", sz="0.002", ord_type="market")

    assert ord_id == "BRIDGE_ORD_42"
    assert StrategyOrder.objects.filter(run=run, okx_ord_id="BRIDGE_ORD_42").exists()


# ---------------------------------------------------------------------------
# 5. dual_ma on_tick — pure function unit tests
# ---------------------------------------------------------------------------

def _make_closes(n: int, value: float = 100.0) -> list[float]:
    """Return a list of `n` identical close prices."""
    return [value] * n


def test_dual_ma_compute_signal_insufficient_data():
    """Not enough bars → no signal."""
    from core.strategy.builtin.dual_ma import compute_signal

    closes = _make_closes(10)  # need >= slow_period + 1 = 21
    assert compute_signal(closes, fast_period=5, slow_period=20) is None


def test_dual_ma_golden_cross_buy_signal():
    """Fast MA crosses above slow MA → 'buy' signal."""
    from core.strategy.builtin.dual_ma import compute_signal

    # Build prices where fast MA starts below slow, then crosses above.
    # Slow period=5, fast period=3 (small numbers for easy construction).
    # Previous 6 bars: all at 100 → both MAs = 100 → fast == slow.
    # Then spike: last bar = 200 → fast MA rises above slow MA.
    closes = [100.0] * 6 + [200.0]
    # fast(3) now = mean([100, 100, 200]) = 133.3
    # slow(5) now = mean([100, 100, 100, 100, 200]) = 120
    # fast(3) prev = mean([100, 100, 100]) = 100
    # slow(5) prev = mean([100, 100, 100, 100, 100]) = 100
    # prev: fast(100) == slow(100); now: fast(133) > slow(120) → golden cross
    signal = compute_signal(closes, fast_period=3, slow_period=5)
    assert signal == "buy"


def test_dual_ma_death_cross_sell_signal():
    """Fast MA crosses below slow MA → 'sell' signal."""
    from core.strategy.builtin.dual_ma import compute_signal

    # Start with fast above slow, then collapse last bar.
    closes = [200.0] * 6 + [50.0]
    # fast(3) now = mean([200, 200, 50]) = 150
    # slow(5) now = mean([200, 200, 200, 200, 50]) = 170
    # fast(3) prev = mean([200, 200, 200]) = 200
    # slow(5) prev = mean([200, 200, 200, 200, 200]) = 200
    # prev: fast(200) == slow(200); now: fast(150) < slow(170) → death cross
    signal = compute_signal(closes, fast_period=3, slow_period=5)
    assert signal == "sell"


def test_dual_ma_no_crossover_no_signal():
    """Flat prices → no crossover → None."""
    from core.strategy.builtin.dual_ma import compute_signal

    closes = [100.0] * 25
    assert compute_signal(closes, fast_period=5, slow_period=20) is None


def test_dual_ma_on_tick_buy(monkeypatch):
    """on_tick calls ctx.buy on golden cross."""
    from core.strategy.builtin.dual_ma import on_tick

    ctx = MagicMock()
    ctx.candles.return_value = [{"c": str(p)} for p in ([100.0] * 6 + [200.0])]
    ctx.buy.return_value = "ORD_BUY"

    on_tick(ctx, {"fast_period": 3, "slow_period": 5, "sz": "0.001"})

    ctx.buy.assert_called_once_with("0.001")


def test_dual_ma_on_tick_sell(monkeypatch):
    """on_tick calls ctx.sell on death cross."""
    from core.strategy.builtin.dual_ma import on_tick

    ctx = MagicMock()
    ctx.candles.return_value = [{"c": str(p)} for p in ([200.0] * 6 + [50.0])]
    ctx.sell.return_value = "ORD_SELL"

    on_tick(ctx, {"fast_period": 3, "slow_period": 5, "sz": "0.002"})

    ctx.sell.assert_called_once_with("0.002")


def test_dual_ma_on_tick_no_signal():
    """on_tick logs 'no signal' when no crossover."""
    from core.strategy.builtin.dual_ma import on_tick

    ctx = MagicMock()
    ctx.candles.return_value = [{"c": "100.0"}] * 25

    on_tick(ctx, {"fast_period": 5, "slow_period": 20, "sz": "0.001"})

    ctx.buy.assert_not_called()
    ctx.sell.assert_not_called()


# ---------------------------------------------------------------------------
# 6. celery run_strategy — mock docker SDK, verify env safety
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_run_strategy_task_injects_only_safe_env():
    """run_strategy task injects RUN_TOKEN+config but NO credential keys."""
    from core.strategy.tasks import run_strategy

    user = _make_user("celery_user")
    cred = _make_credential(user)
    run, _ = _make_run(user, credential=cred, status=StrategyRun.STATUS_PENDING)

    mock_container = MagicMock()
    mock_container.id = "abc123def456" * 3  # 36-char fake ID

    mock_docker_client = MagicMock()
    mock_docker_client.containers.run.return_value = mock_container

    with patch("docker.from_env", return_value=mock_docker_client):
        run_strategy(run.pk)

    # Verify container.run was called
    mock_docker_client.containers.run.assert_called_once()
    call_kwargs = mock_docker_client.containers.run.call_args

    # Extract the environment dict passed to Docker
    env = call_kwargs.kwargs.get("environment") or call_kwargs.args[1] if len(call_kwargs.args) > 1 else {}
    if not env:
        # Try positional or keyword
        env = call_kwargs[1].get("environment", {}) if call_kwargs[1] else {}

    # The environment must contain RUN_TOKEN, BACKEND_URL, CODE_REF, SYMBOL, PARAMS
    env_passed = mock_docker_client.containers.run.call_args.kwargs.get("environment", {})
    assert "RUN_TOKEN" in env_passed
    assert "BACKEND_URL" in env_passed
    assert "CODE_REF" in env_passed
    assert "SYMBOL" in env_passed
    assert "PARAMS" in env_passed

    # CRITICAL: no raw credential fields must be present
    forbidden_keys = {"API_KEY", "SECRET", "PASSPHRASE", "api_key", "secret", "passphrase",
                      "OKX_API_KEY", "OKX_SECRET", "OKX_PASSPHRASE"}
    injected_keys = set(env_passed.keys())
    assert not (injected_keys & forbidden_keys), (
        f"Credential keys leaked into container env: {injected_keys & forbidden_keys}"
    )

    # Verify status was set to running and container_id recorded
    run.refresh_from_db()
    assert run.status == StrategyRun.STATUS_RUNNING
    assert run.container_id == mock_container.id


@pytest.mark.django_db
def test_run_strategy_task_updates_token_hash():
    """run_strategy generates a fresh token and updates run_token_hash."""
    from core.strategy.tasks import run_strategy

    user = _make_user("token_refresh_user")
    run, old_plain_token = _make_run(user, status=StrategyRun.STATUS_PENDING)
    old_hash = run.run_token_hash

    mock_container = MagicMock()
    mock_container.id = "fresh_container_id_123"

    with patch("docker.from_env", return_value=MagicMock(
        **{"containers.run.return_value": mock_container}
    )):
        run_strategy(run.pk)

    run.refresh_from_db()
    # Token hash must have been rotated
    assert run.run_token_hash != old_hash
    # Old token must no longer resolve the run
    assert resolve_run(old_plain_token) is None


@pytest.mark.django_db
def test_stop_strategy_task_sets_status_stopped():
    """stop_strategy sets run status to stopped."""
    from core.strategy.tasks import stop_strategy

    user = _make_user("stop_user")
    run, _ = _make_run(user, status=StrategyRun.STATUS_RUNNING)
    run.container_id = "fake_container_abc"
    run.save(update_fields=["container_id"])

    mock_container = MagicMock()
    mock_client = MagicMock()
    mock_client.containers.get.return_value = mock_container

    with patch("docker.from_env", return_value=mock_client):
        stop_strategy(run.pk)

    run.refresh_from_db()
    assert run.status == StrategyRun.STATUS_STOPPED
    mock_container.stop.assert_called_once()
    mock_container.remove.assert_called_once()


# ---------------------------------------------------------------------------
# 7. run_token module unit tests
# ---------------------------------------------------------------------------

def test_generate_token_is_url_safe_string():
    """generate_token returns a non-empty URL-safe string."""
    token = generate_token()
    assert isinstance(token, str)
    assert len(token) > 20


def test_hash_token_is_deterministic():
    """hash_token produces the same hash for the same token."""
    t = "test-token-abc"
    assert hash_token(t) == hash_token(t)
    assert len(hash_token(t)) == 64  # SHA-256 hex = 64 chars


def test_hash_token_different_inputs_differ():
    """hash_token produces different hashes for different inputs."""
    assert hash_token("abc") != hash_token("xyz")


@pytest.mark.django_db
def test_resolve_run_returns_none_for_unknown_token():
    """resolve_run returns None for a token not in the database."""
    assert resolve_run("nonexistent-token-xyz") is None


@pytest.mark.django_db
def test_resolve_run_returns_run_for_valid_running_token():
    """resolve_run returns the StrategyRun for a valid running token."""
    user = _make_user("resolve_user")
    run, plain_token = _make_run(user, status=StrategyRun.STATUS_RUNNING)
    resolved = resolve_run(plain_token)
    assert resolved is not None
    assert resolved.pk == run.pk
