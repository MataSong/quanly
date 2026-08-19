"""Tests for M-T3: 策略商城 API.

Coverage:
  1. marketplace 过滤: 公开+approved, 自己(含私有), 内置出现; 他人私有不出现。
  2. create: owner=self/source=uploaded/status=draft; 无效 template_ref → 400。
  3. mine: 只返回自己的。
  4. update: 限 owner (他人 → 404); 改动后重置 status=draft。
  5. delete: 限 owner; 有 run 引用 → 400。
  6. submit: → pending + public。
  7. review: 需 strategy:audit (无 → 403); approve → approved; reject → rejected+reason。
  8. run guard: 他人私有策略 POST /runs → 403; 内置/自己/公开+approved → 通过。
  9. detail: 他人私有 → 404; 他人 public+approved → 200; params 脱敏。

OKX / Docker / Celery 全打桩。
"""
import pytest
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User

from core.accounts.models import Role, UserRole
from core.credentials.crypto import encrypt
from core.credentials.models import Credential
from core.strategy.models import Strategy, StrategyRun
from core.strategy.run_token import generate_token, hash_token


# ---------------------------------------------------------------------------
# Helpers (mirror test_strategy.py style)
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


def _builtin_strategy() -> Strategy:
    """Get or create the dual_ma builtin strategy (owner=None, approved, public)."""
    s, _ = Strategy.objects.get_or_create(
        code_ref="dual_ma",
        owner__isnull=True,
        defaults={
            "name": "Dual MA",
            "source_type": Strategy.SOURCE_BUILTIN,
            "is_builtin": True,
            "owner": None,
            "status": Strategy.STATUS_APPROVED,
            "visibility": Strategy.VISIBILITY_PUBLIC,
            "default_params": {"fast_period": 5, "slow_period": 20, "sz": "0.001"},
        },
    )
    return s


def _make_user_strategy(
    owner: User,
    name: str = "My Strat",
    template_ref: str = "dual_ma",
    visibility: str = Strategy.VISIBILITY_PRIVATE,
    status: str = Strategy.STATUS_DRAFT,
    params: dict | None = None,
) -> Strategy:
    return Strategy.objects.create(
        owner=owner,
        name=name,
        source_type=Strategy.SOURCE_UPLOADED,
        is_builtin=False,
        code_ref=template_ref,
        template_ref=template_ref,
        params=params or {"fast_period": 3, "slow_period": 10, "sz": "0.01"},
        default_params={},
        visibility=visibility,
        status=status,
    )


def _make_run(user: User, strategy: Strategy, status: str = StrategyRun.STATUS_PENDING) -> StrategyRun:
    plain_token = generate_token()
    return StrategyRun.objects.create(
        user=user,
        strategy=strategy,
        env=StrategyRun.ENV_SIM,
        symbol="BTC-USDT",
        params={},
        run_token_hash=hash_token(plain_token),
        status=status,
    )


# ---------------------------------------------------------------------------
# 1. Marketplace filtering
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_marketplace_shows_builtin(api_client):
    """GET /marketplace: builtin strategies visible."""
    builtin = _builtin_strategy()
    user = _make_user("mp_u1", ["strategy:view"])
    api_client.force_authenticate(user)
    resp = api_client.get("/api/strategy/marketplace")
    assert resp.status_code == 200
    ids = {s["id"] for s in resp.data}
    assert builtin.pk in ids


@pytest.mark.django_db
def test_marketplace_shows_own_private(api_client):
    """GET /marketplace: own private strategies are visible."""
    _builtin_strategy()
    user = _make_user("mp_u2", ["strategy:view"])
    own = _make_user_strategy(user, name="My Private", visibility=Strategy.VISIBILITY_PRIVATE)
    api_client.force_authenticate(user)
    resp = api_client.get("/api/strategy/marketplace")
    assert resp.status_code == 200
    ids = {s["id"] for s in resp.data}
    assert own.pk in ids


@pytest.mark.django_db
def test_marketplace_shows_public_approved(api_client):
    """GET /marketplace: other user's public+approved strategies visible."""
    _builtin_strategy()
    other = _make_user("mp_other")
    public_strat = _make_user_strategy(
        other, name="Public Strat",
        visibility=Strategy.VISIBILITY_PUBLIC,
        status=Strategy.STATUS_APPROVED,
    )
    user = _make_user("mp_u3", ["strategy:view"])
    api_client.force_authenticate(user)
    resp = api_client.get("/api/strategy/marketplace")
    assert resp.status_code == 200
    ids = {s["id"] for s in resp.data}
    assert public_strat.pk in ids


@pytest.mark.django_db
def test_marketplace_hides_other_private(api_client):
    """GET /marketplace: other user's private strategies NOT visible."""
    _builtin_strategy()
    other = _make_user("mp_other2")
    private_strat = _make_user_strategy(
        other, name="Other Private",
        visibility=Strategy.VISIBILITY_PRIVATE,
        status=Strategy.STATUS_DRAFT,
    )
    user = _make_user("mp_u4", ["strategy:view"])
    api_client.force_authenticate(user)
    resp = api_client.get("/api/strategy/marketplace")
    assert resp.status_code == 200
    ids = {s["id"] for s in resp.data}
    assert private_strat.pk not in ids


# ---------------------------------------------------------------------------
# 2. Create
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_create_strategy_success(api_client):
    """POST /strategies/create: creates own strategy with correct defaults."""
    _builtin_strategy()
    user = _make_user("create_u1", ["strategy:create"])
    api_client.force_authenticate(user)
    resp = api_client.post("/api/strategy/strategies/create", {
        "name": "My Test Strategy",
        "template_ref": "dual_ma",
        "params": {"fast_period": 3, "slow_period": 10, "sz": "0.01"},
        "description": "test desc",
    }, format="json")
    assert resp.status_code == 201
    data = resp.data
    assert data["name"] == "My Test Strategy"
    assert data["owner_username"] == user.username
    assert data["status"] == Strategy.STATUS_DRAFT
    assert data["source_type"] == Strategy.SOURCE_UPLOADED
    assert data["is_builtin"] is False
    assert data["template_ref"] == "dual_ma"
    assert data["is_owner"] is True


@pytest.mark.django_db
def test_create_strategy_invalid_template_ref_400(api_client):
    """POST /strategies/create: invalid template_ref → 400."""
    _builtin_strategy()
    user = _make_user("create_u2", ["strategy:create"])
    api_client.force_authenticate(user)
    resp = api_client.post("/api/strategy/strategies/create", {
        "name": "Bad Template",
        "template_ref": "nonexistent_template",
        "params": {},
    }, format="json")
    assert resp.status_code == 400
    assert "template_ref" in resp.data["detail"]


@pytest.mark.django_db
def test_create_strategy_missing_name_400(api_client):
    """POST /strategies/create: missing name → 400."""
    _builtin_strategy()
    user = _make_user("create_u3", ["strategy:create"])
    api_client.force_authenticate(user)
    resp = api_client.post("/api/strategy/strategies/create", {
        "template_ref": "dual_ma",
    }, format="json")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 3. Mine
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_mine_returns_only_own(api_client):
    """GET /mine: only returns strategies owned by the authenticated user."""
    _builtin_strategy()
    alice = _make_user("mine_alice", ["strategy:view"])
    bob = _make_user("mine_bob", ["strategy:view"])
    alice_strat = _make_user_strategy(alice, name="Alice Strat")
    bob_strat = _make_user_strategy(bob, name="Bob Strat")

    api_client.force_authenticate(alice)
    resp = api_client.get("/api/strategy/mine")
    assert resp.status_code == 200
    ids = {s["id"] for s in resp.data}
    assert alice_strat.pk in ids
    assert bob_strat.pk not in ids
    # builtin should NOT appear in mine (no owner)
    assert all(s["owner_username"] == alice.username for s in resp.data)


# ---------------------------------------------------------------------------
# 4. Update
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_update_own_strategy_resets_status(api_client):
    """PUT /strategies/<pk>: updates fields and resets status to draft."""
    _builtin_strategy()
    user = _make_user("update_u1", ["strategy:update", "strategy:view"])
    strat = _make_user_strategy(
        user, name="Original",
        status=Strategy.STATUS_APPROVED,
        visibility=Strategy.VISIBILITY_PUBLIC,
    )
    api_client.force_authenticate(user)
    resp = api_client.put(f"/api/strategy/strategies/{strat.pk}", {
        "name": "Updated",
        "params": {"fast_period": 7},
        "visibility": Strategy.VISIBILITY_PRIVATE,
    }, format="json")
    assert resp.status_code == 200
    data = resp.data
    assert data["name"] == "Updated"
    assert data["status"] == Strategy.STATUS_DRAFT
    assert data["visibility"] == Strategy.VISIBILITY_PRIVATE


@pytest.mark.django_db
def test_update_other_strategy_returns_404(api_client):
    """PUT /strategies/<pk>: updating another user's strategy → 404."""
    _builtin_strategy()
    owner = _make_user("update_owner")
    attacker = _make_user("update_attacker", ["strategy:update"])
    strat = _make_user_strategy(owner, name="Owner Strat")

    api_client.force_authenticate(attacker)
    resp = api_client.put(f"/api/strategy/strategies/{strat.pk}", {
        "name": "Hacked",
    }, format="json")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 5. Delete
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_delete_own_strategy_success(api_client):
    """DELETE /strategies/<pk>: own strategy without runs → 204."""
    _builtin_strategy()
    user = _make_user("delete_u1", ["strategy:delete"])
    strat = _make_user_strategy(user, name="To Delete")
    api_client.force_authenticate(user)
    resp = api_client.delete(f"/api/strategy/strategies/{strat.pk}")
    assert resp.status_code == 204
    assert not Strategy.objects.filter(pk=strat.pk).exists()


@pytest.mark.django_db
def test_delete_strategy_with_run_returns_400(api_client):
    """DELETE /strategies/<pk>: strategy with run references → 400."""
    _builtin_strategy()
    user = _make_user("delete_u2", ["strategy:delete"])
    strat = _make_user_strategy(user, name="Has Run")
    # Create a StrategyRun referencing the strategy (PROTECT constraint)
    _make_run(user, strat)

    api_client.force_authenticate(user)
    resp = api_client.delete(f"/api/strategy/strategies/{strat.pk}")
    assert resp.status_code == 400
    assert "运行记录" in resp.data["detail"]


@pytest.mark.django_db
def test_delete_other_strategy_returns_404(api_client):
    """DELETE /strategies/<pk>: another user's strategy → 404."""
    _builtin_strategy()
    owner = _make_user("delete_owner")
    attacker = _make_user("delete_attacker", ["strategy:delete"])
    strat = _make_user_strategy(owner)

    api_client.force_authenticate(attacker)
    resp = api_client.delete(f"/api/strategy/strategies/{strat.pk}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 6. Submit
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_submit_strategy_sets_pending_public(api_client):
    """POST /strategies/<pk>/submit: sets status=pending, visibility=public."""
    _builtin_strategy()
    user = _make_user("submit_u1", ["strategy:update"])
    strat = _make_user_strategy(user, name="To Submit", status=Strategy.STATUS_DRAFT)
    api_client.force_authenticate(user)
    resp = api_client.post(f"/api/strategy/strategies/{strat.pk}/submit")
    assert resp.status_code == 200
    assert resp.data["status"] == Strategy.STATUS_PENDING
    assert resp.data["visibility"] == Strategy.VISIBILITY_PUBLIC


@pytest.mark.django_db
def test_submit_other_strategy_returns_404(api_client):
    """POST /strategies/<pk>/submit for another user's strategy → 404."""
    _builtin_strategy()
    owner = _make_user("submit_owner")
    attacker = _make_user("submit_attacker", ["strategy:update"])
    strat = _make_user_strategy(owner)

    api_client.force_authenticate(attacker)
    resp = api_client.post(f"/api/strategy/strategies/{strat.pk}/submit")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 7. Admin review
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_admin_pending_requires_audit_perm(api_client):
    """GET /admin/pending without strategy:audit → 403."""
    _builtin_strategy()
    user = _make_user("audit_no_perm", ["strategy:view"])
    api_client.force_authenticate(user)
    resp = api_client.get("/api/strategy/admin/pending")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_admin_pending_returns_pending_strategies(api_client):
    """GET /admin/pending with strategy:audit → only pending strategies."""
    _builtin_strategy()
    owner = _make_user("audit_owner")
    admin = _make_user("audit_admin", ["strategy:audit"])
    pending = _make_user_strategy(owner, name="Pending Strat", status=Strategy.STATUS_PENDING)
    _make_user_strategy(owner, name="Draft Strat", status=Strategy.STATUS_DRAFT)

    api_client.force_authenticate(admin)
    resp = api_client.get("/api/strategy/admin/pending")
    assert resp.status_code == 200
    ids = {s["id"] for s in resp.data}
    assert pending.pk in ids
    # draft should not appear
    for s in resp.data:
        assert s["status"] == Strategy.STATUS_PENDING


@pytest.mark.django_db
def test_admin_review_approve(api_client):
    """POST /admin/strategies/<pk>/review action=approve → status=approved."""
    _builtin_strategy()
    owner = _make_user("review_owner1")
    admin = _make_user("review_admin1", ["strategy:audit"])
    strat = _make_user_strategy(owner, name="For Approval", status=Strategy.STATUS_PENDING,
                                visibility=Strategy.VISIBILITY_PUBLIC)
    api_client.force_authenticate(admin)
    resp = api_client.post(f"/api/strategy/admin/strategies/{strat.pk}/review", {
        "action": "approve",
    }, format="json")
    assert resp.status_code == 200
    assert resp.data["status"] == Strategy.STATUS_APPROVED


@pytest.mark.django_db
def test_admin_review_reject(api_client):
    """POST /admin/strategies/<pk>/review action=reject → status=rejected+reason."""
    _builtin_strategy()
    owner = _make_user("review_owner2")
    admin = _make_user("review_admin2", ["strategy:audit"])
    strat = _make_user_strategy(owner, name="For Rejection", status=Strategy.STATUS_PENDING,
                                visibility=Strategy.VISIBILITY_PUBLIC)
    api_client.force_authenticate(admin)
    resp = api_client.post(f"/api/strategy/admin/strategies/{strat.pk}/review", {
        "action": "reject",
        "reason": "Does not meet quality standards.",
    }, format="json")
    assert resp.status_code == 200
    assert resp.data["status"] == Strategy.STATUS_REJECTED
    assert resp.data["reject_reason"] == "Does not meet quality standards."


@pytest.mark.django_db
def test_admin_review_requires_audit_perm(api_client):
    """POST /admin/strategies/<pk>/review without strategy:audit → 403."""
    _builtin_strategy()
    owner = _make_user("review_owner3")
    non_admin = _make_user("review_non_admin", ["strategy:view"])
    strat = _make_user_strategy(owner, status=Strategy.STATUS_PENDING)

    api_client.force_authenticate(non_admin)
    resp = api_client.post(f"/api/strategy/admin/strategies/{strat.pk}/review", {
        "action": "approve",
    }, format="json")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 8. Run guard
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_run_guard_other_private_strategy_returns_403(api_client):
    """POST /runs using another user's private strategy → 403."""
    _builtin_strategy()
    owner = _make_user("guard_owner")
    attacker = _make_user("guard_attacker", ["strategy:run"])
    private_strat = _make_user_strategy(
        owner, name="Owner Private",
        visibility=Strategy.VISIBILITY_PRIVATE,
        status=Strategy.STATUS_DRAFT,
    )
    api_client.force_authenticate(attacker)
    resp = api_client.post("/api/strategy/runs", {
        "strategy_id": private_strat.pk,
        "symbol": "BTC-USDT",
    }, format="json")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_run_guard_builtin_strategy_passes(api_client):
    """POST /runs using builtin strategy → 201 (mock celery/docker)."""
    builtin = _builtin_strategy()
    user = _make_user("guard_builtin", ["strategy:run"])
    api_client.force_authenticate(user)
    resp = api_client.post("/api/strategy/runs", {
        "strategy_id": builtin.pk,
        "symbol": "BTC-USDT",
    }, format="json")
    assert resp.status_code == 201


@pytest.mark.django_db
def test_run_guard_own_strategy_passes(api_client):
    """POST /runs using own private strategy → 201."""
    _builtin_strategy()
    user = _make_user("guard_own", ["strategy:run"])
    own_strat = _make_user_strategy(
        user, name="Own Private",
        visibility=Strategy.VISIBILITY_PRIVATE,
        status=Strategy.STATUS_DRAFT,
    )
    api_client.force_authenticate(user)
    resp = api_client.post("/api/strategy/runs", {
        "strategy_id": own_strat.pk,
        "symbol": "BTC-USDT",
    }, format="json")
    assert resp.status_code == 201


@pytest.mark.django_db
def test_run_guard_public_approved_passes(api_client):
    """POST /runs using another user's public+approved strategy → 201."""
    _builtin_strategy()
    other = _make_user("guard_pub_owner")
    public_strat = _make_user_strategy(
        other, name="Public Approved",
        visibility=Strategy.VISIBILITY_PUBLIC,
        status=Strategy.STATUS_APPROVED,
    )
    user = _make_user("guard_pub_user", ["strategy:run"])
    api_client.force_authenticate(user)
    resp = api_client.post("/api/strategy/runs", {
        "strategy_id": public_strat.pk,
        "symbol": "BTC-USDT",
    }, format="json")
    assert resp.status_code == 201


@pytest.mark.django_db
def test_run_guard_other_pending_public_returns_403(api_client):
    """POST /runs using another user's public but pending strategy → 403."""
    _builtin_strategy()
    other = _make_user("guard_pending_owner")
    pending_strat = _make_user_strategy(
        other, name="Pending Public",
        visibility=Strategy.VISIBILITY_PUBLIC,
        status=Strategy.STATUS_PENDING,
    )
    user = _make_user("guard_pending_user", ["strategy:run"])
    api_client.force_authenticate(user)
    resp = api_client.post("/api/strategy/runs", {
        "strategy_id": pending_strat.pk,
        "symbol": "BTC-USDT",
    }, format="json")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 9. Detail view — access control and params masking
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_detail_other_private_returns_404(api_client):
    """GET /strategies/<pk> for another user's private strategy → 404."""
    _builtin_strategy()
    owner = _make_user("detail_owner1")
    viewer = _make_user("detail_viewer1", ["strategy:view"])
    private_strat = _make_user_strategy(owner, name="Other Private",
                                        visibility=Strategy.VISIBILITY_PRIVATE)
    api_client.force_authenticate(viewer)
    resp = api_client.get(f"/api/strategy/strategies/{private_strat.pk}")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_detail_other_public_approved_returns_200(api_client):
    """GET /strategies/<pk> for another user's public+approved strategy → 200."""
    _builtin_strategy()
    owner = _make_user("detail_owner2")
    viewer = _make_user("detail_viewer2", ["strategy:view"])
    pub_strat = _make_user_strategy(
        owner, name="Other Public",
        visibility=Strategy.VISIBILITY_PUBLIC,
        status=Strategy.STATUS_APPROVED,
        params={"fast_period": 5},
    )
    api_client.force_authenticate(viewer)
    resp = api_client.get(f"/api/strategy/strategies/{pub_strat.pk}")
    assert resp.status_code == 200
    # params should be visible for public+approved
    assert resp.data["params"] == {"fast_period": 5}
    assert "performance" in resp.data  # reserved field present


@pytest.mark.django_db
def test_detail_own_strategy_params_visible(api_client):
    """GET /strategies/<pk>: own strategy — params visible."""
    _builtin_strategy()
    user = _make_user("detail_own_u", ["strategy:view"])
    strat = _make_user_strategy(user, params={"fast_period": 9}, name="Own Strat")
    api_client.force_authenticate(user)
    resp = api_client.get(f"/api/strategy/strategies/{strat.pk}")
    assert resp.status_code == 200
    assert resp.data["params"] == {"fast_period": 9}
    assert resp.data["is_owner"] is True


@pytest.mark.django_db
def test_serializer_params_masked_for_other_pending(api_client):
    """Serializer: other user's pending/private strategy params → {} via list endpoint."""
    _builtin_strategy()
    owner = _make_user("mask_owner")
    viewer = _make_user("mask_viewer", ["strategy:view"])
    # Public but pending (not approved) — appears in marketplace? No (only approved+public show)
    # Let's use viewer's own context on a strategy they own vs not
    # Test via direct serializer: create a public+pending strat owned by owner,
    # it won't appear in marketplace for viewer, so test via admin view (audit perm needed).
    # Instead test params masking via the serializer context directly:
    from core.strategy.views import StrategySerializer
    from django.test import RequestFactory
    from rest_framework.request import Request as DRFRequest

    factory = RequestFactory()
    raw_request = factory.get("/")
    raw_request.user = viewer
    drf_request = DRFRequest(raw_request)

    pending_strat = _make_user_strategy(
        owner,
        name="Pending Strat",
        visibility=Strategy.VISIBILITY_PUBLIC,
        status=Strategy.STATUS_PENDING,
        params={"fast_period": 99},
    )
    data = StrategySerializer(pending_strat, context={"request": drf_request}).data
    # Other user's pending strategy: not public+approved → params masked
    assert data["params"] == {}


@pytest.mark.django_db
def test_detail_performance_aggregation(api_client):
    """策略详情 performance 聚合:run_count/user_count/order_count 真实统计,无数据返 0。"""
    owner = _make_user("perf_owner", ["strategy:view"])
    strat = _make_user_strategy(owner, visibility="public", status=Strategy.STATUS_APPROVED)
    # 无运行时全 0
    api_client.force_authenticate(owner)
    resp = api_client.get(f"/api/strategy/strategies/{strat.id}")
    assert resp.status_code == 200
    perf = resp.data["performance"]
    assert perf["run_count"] == 0
    assert perf["user_count"] == 0
    assert perf["order_count"] == 0
    assert perf["reference_backtest"] is None

    # 造 2 个 run(不同用户) → run_count=2, user_count=2
    other = _make_user("perf_other")
    _make_run(owner, strat)
    _make_run(other, strat)
    resp = api_client.get(f"/api/strategy/strategies/{strat.id}")
    perf = resp.data["performance"]
    assert perf["run_count"] == 2
    assert perf["user_count"] == 2


@pytest.mark.django_db
def test_run_uses_strategy_params(api_client):
    """用户参数化策略 run 时,run.params 落地为 strategy.params(容器会用它跑内置模板)。"""
    from core.strategy.models import StrategyRun

    _builtin_strategy()
    user = _make_user("param_flow", ["strategy:run"])
    strat = _make_user_strategy(
        user, name="Param Flow",
        params={"fast_period": 7, "slow_period": 21, "sz": "0.05"},
    )
    api_client.force_authenticate(user)
    resp = api_client.post("/api/strategy/runs", {
        "strategy_id": strat.pk,
        "symbol": "BTC-USDT",
    }, format="json")
    assert resp.status_code == 201
    run = StrategyRun.objects.get(pk=resp.data["id"])
    # 策略参数落地到 run,不被前端空 params 覆盖
    assert run.params == {"fast_period": 7, "slow_period": 21, "sz": "0.05"}
    # tasks 会用 template_ref 作 CODE_REF 跑内置代码
    assert run.strategy.template_ref == "dual_ma"


# ---------------------------------------------------------------------------
# UC-T4: code 类型 create / check / submit + code 脱敏
# ---------------------------------------------------------------------------

_PASSED = {"check_status": Strategy.CHECK_PASSED, "check_report": {"stage": "trial", "ok": True, "signal_count": 3}}
_FAILED = {"check_status": Strategy.CHECK_FAILED, "check_report": {"stage": "ast", "violations": [{"line": 1, "rule": "forbidden_import", "detail": "import os ..."}]}}

_VALIDATE = "core.strategy.validation.validate_strategy_code"

_SAMPLE_CODE = "def on_tick(ctx, params):\n    pass\n"


def _make_code_strategy(
    owner: User,
    name: str = "Code Strat",
    code: str = _SAMPLE_CODE,
    check_status: str = Strategy.CHECK_PASSED,
    check_report: dict | None = None,
    visibility: str = Strategy.VISIBILITY_PRIVATE,
    status: str = Strategy.STATUS_DRAFT,
) -> Strategy:
    return Strategy.objects.create(
        owner=owner,
        name=name,
        source_type=Strategy.SOURCE_CODE,
        is_builtin=False,
        code=code,
        code_ref="",
        template_ref="",
        params={},
        default_params={},
        visibility=visibility,
        status=status,
        check_status=check_status,
        check_report=check_report or {"stage": "trial", "ok": True},
    )


@pytest.mark.django_db
def test_create_code_strategy_passed(api_client):
    """POST create source_type=code, validate→passed → 201 + check_status=passed."""
    user = _make_user("code_c1", ["strategy:create"])
    api_client.force_authenticate(user)
    with patch(_VALIDATE, return_value=_PASSED) as m:
        resp = api_client.post("/api/strategy/strategies/create", {
            "name": "My Code Strat",
            "source_type": "code",
            "code": _SAMPLE_CODE,
        }, format="json")
    assert resp.status_code == 201
    m.assert_called_once()
    data = resp.data
    assert data["source_type"] == Strategy.SOURCE_CODE
    assert data["status"] == Strategy.STATUS_DRAFT
    assert data["check_status"] == Strategy.CHECK_PASSED
    assert data["is_owner"] is True
    # owner's own code is visible
    assert data["code"] == _SAMPLE_CODE


@pytest.mark.django_db
def test_create_code_strategy_failed(api_client):
    """POST create source_type=code, validate→failed → still 201 + check_status=failed."""
    user = _make_user("code_c2", ["strategy:create"])
    api_client.force_authenticate(user)
    with patch(_VALIDATE, return_value=_FAILED):
        resp = api_client.post("/api/strategy/strategies/create", {
            "name": "Bad Code Strat",
            "source_type": "code",
            "code": "import os\ndef on_tick(ctx, params):\n    pass\n",
        }, format="json")
    assert resp.status_code == 201
    assert resp.data["check_status"] == Strategy.CHECK_FAILED
    assert resp.data["check_report"]["stage"] == "ast"


@pytest.mark.django_db
def test_create_code_strategy_missing_code_400(api_client):
    """POST create source_type=code without code → 400 (validate not called)."""
    user = _make_user("code_c3", ["strategy:create"])
    api_client.force_authenticate(user)
    with patch(_VALIDATE, return_value=_PASSED) as m:
        resp = api_client.post("/api/strategy/strategies/create", {
            "name": "No Code",
            "source_type": "code",
        }, format="json")
    assert resp.status_code == 400
    m.assert_not_called()


@pytest.mark.django_db
def test_create_code_forces_owner_and_status(api_client):
    """create code: 不信前端传的 owner/status,强制 owner=self + draft."""
    _builtin_strategy()
    other = _make_user("code_other")
    user = _make_user("code_c4", ["strategy:create"])
    api_client.force_authenticate(user)
    with patch(_VALIDATE, return_value=_PASSED):
        resp = api_client.post("/api/strategy/strategies/create", {
            "name": "Sneaky",
            "source_type": "code",
            "code": _SAMPLE_CODE,
            "owner": other.pk,
            "status": Strategy.STATUS_APPROVED,
        }, format="json")
    assert resp.status_code == 201
    strat = Strategy.objects.get(pk=resp.data["id"])
    assert strat.owner_id == user.id
    assert strat.status == Strategy.STATUS_DRAFT


@pytest.mark.django_db
def test_create_template_unaffected(api_client):
    """create 默认(无 source_type)仍走 template 逻辑,不受 code 影响。"""
    _builtin_strategy()
    user = _make_user("code_c5", ["strategy:create"])
    api_client.force_authenticate(user)
    with patch(_VALIDATE, return_value=_PASSED) as m:
        resp = api_client.post("/api/strategy/strategies/create", {
            "name": "Template Strat",
            "template_ref": "dual_ma",
            "params": {"fast_period": 3},
        }, format="json")
    assert resp.status_code == 201
    assert resp.data["source_type"] == Strategy.SOURCE_UPLOADED
    m.assert_not_called()  # template create never runs validation


@pytest.mark.django_db
def test_check_endpoint_reruns_validation(api_client):
    """POST /strategies/<pk>/check reruns validate + updates check_status."""
    user = _make_user("code_chk1", ["strategy:update"])
    strat = _make_code_strategy(user, check_status=Strategy.CHECK_FAILED,
                                check_report={"stage": "ast"})
    api_client.force_authenticate(user)
    with patch(_VALIDATE, return_value=_PASSED) as m:
        resp = api_client.post(f"/api/strategy/strategies/{strat.pk}/check")
    assert resp.status_code == 200
    m.assert_called_once()
    assert resp.data["check_status"] == Strategy.CHECK_PASSED
    strat.refresh_from_db()
    assert strat.check_status == Strategy.CHECK_PASSED


@pytest.mark.django_db
def test_check_endpoint_template_400(api_client):
    """check on template strategy (no code) → 400."""
    _builtin_strategy()
    user = _make_user("code_chk2", ["strategy:update"])
    strat = _make_user_strategy(user, name="Tmpl")
    api_client.force_authenticate(user)
    resp = api_client.post(f"/api/strategy/strategies/{strat.pk}/check")
    assert resp.status_code == 400


@pytest.mark.django_db
def test_check_endpoint_other_owner_404(api_client):
    """check on another user's strategy → 404."""
    owner = _make_user("code_chk_owner")
    attacker = _make_user("code_chk_atk", ["strategy:update"])
    strat = _make_code_strategy(owner)
    api_client.force_authenticate(attacker)
    resp = api_client.post(f"/api/strategy/strategies/{strat.pk}/check")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_submit_code_requires_check_passed(api_client):
    """submit code strategy with check_status=failed → 400."""
    user = _make_user("code_sub1", ["strategy:update"])
    strat = _make_code_strategy(user, check_status=Strategy.CHECK_FAILED)
    api_client.force_authenticate(user)
    resp = api_client.post(f"/api/strategy/strategies/{strat.pk}/submit")
    assert resp.status_code == 400
    assert "检测未通过" in resp.data["detail"]
    strat.refresh_from_db()
    assert strat.status == Strategy.STATUS_DRAFT


@pytest.mark.django_db
def test_submit_code_passed_goes_pending(api_client):
    """submit code strategy with check_status=passed → pending + public."""
    user = _make_user("code_sub2", ["strategy:update"])
    strat = _make_code_strategy(user, check_status=Strategy.CHECK_PASSED)
    api_client.force_authenticate(user)
    resp = api_client.post(f"/api/strategy/strategies/{strat.pk}/submit")
    assert resp.status_code == 200
    assert resp.data["status"] == Strategy.STATUS_PENDING
    assert resp.data["visibility"] == Strategy.VISIBILITY_PUBLIC


@pytest.mark.django_db
def test_submit_template_not_blocked_by_check(api_client):
    """template strategy submit not affected by check_status guard."""
    _builtin_strategy()
    user = _make_user("code_sub3", ["strategy:update"])
    strat = _make_user_strategy(user, name="Tmpl Submit")
    api_client.force_authenticate(user)
    resp = api_client.post(f"/api/strategy/strategies/{strat.pk}/submit")
    assert resp.status_code == 200
    assert resp.data["status"] == Strategy.STATUS_PENDING


@pytest.mark.django_db
def test_code_masked_for_other_private():
    """Serializer: other user's private code strategy → code='' + report stage-only."""
    from core.strategy.views import StrategySerializer
    from django.test import RequestFactory
    from rest_framework.request import Request as DRFRequest

    owner = _make_user("code_mask_owner")
    viewer = _make_user("code_mask_viewer")
    strat = _make_code_strategy(
        owner, code=_SAMPLE_CODE,
        visibility=Strategy.VISIBILITY_PRIVATE, status=Strategy.STATUS_DRAFT,
        check_report={"stage": "ast", "violations": [{"detail": "secret code"}]},
    )
    factory = RequestFactory()
    raw = factory.get("/")
    drf_req = DRFRequest(raw)
    drf_req.user = viewer
    data = StrategySerializer(strat, context={"request": drf_req}).data
    assert data["code"] == ""
    # check_report masked to stage-only, no violations leaked
    assert data["check_report"] == {"stage": "ast"}
    assert "violations" not in data["check_report"]


@pytest.mark.django_db
def test_code_visible_for_owner_and_public_approved():
    """Serializer: owner sees own code; other sees public+approved code."""
    from core.strategy.views import StrategySerializer
    from django.test import RequestFactory
    from rest_framework.request import Request as DRFRequest

    owner = _make_user("code_vis_owner")
    viewer = _make_user("code_vis_viewer")
    factory = RequestFactory()

    # owner sees own private code
    own = _make_code_strategy(owner, code=_SAMPLE_CODE, visibility=Strategy.VISIBILITY_PRIVATE)
    raw = factory.get("/"); req_own = DRFRequest(raw); req_own.user = owner
    d_own = StrategySerializer(own, context={"request": req_own}).data
    assert d_own["code"] == _SAMPLE_CODE

    # other sees public+approved code
    pub = _make_code_strategy(
        owner, name="Pub Code", code=_SAMPLE_CODE,
        visibility=Strategy.VISIBILITY_PUBLIC, status=Strategy.STATUS_APPROVED,
    )
    raw2 = factory.get("/"); req_pub = DRFRequest(raw2); req_pub.user = viewer
    d_pub = StrategySerializer(pub, context={"request": req_pub}).data
    assert d_pub["code"] == _SAMPLE_CODE
