"""Asset dashboard views — aggregates OKX balance, positions, and bills.

All credential lookups are scoped to request.user (multi-tenant).
Flag follows credential.env via okx_ext._flag(cred).
Zero mock in product paths — only test suites use unittest.mock.
Patch point in tests: core.assets.views.okx_ext.get_balance / get_positions / get_bills
"""
import logging

from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.accounts.drf import HasRequiredPermissions
from core.credentials.models import Credential
from core.trading import okx_ext

logger = logging.getLogger("quanly.assets")


def _get_credential(request) -> Credential:
    """Return credential owned by request.user from credential_id query param.

    Caller must have already checked that credential_id is present (returns 400).
    Raises:
        NotFound (404): if credential_id is not a valid int or doesn't belong to user.
    """
    cid_str = request.query_params.get("credential_id", "")
    try:
        cid = int(cid_str)
    except (TypeError, ValueError):
        raise NotFound("credential not found")
    try:
        return Credential.objects.get(id=cid, user=request.user)
    except Credential.DoesNotExist:
        raise NotFound("credential not found")


class AssetsSummaryView(APIView):
    """GET /api/assets/summary?credential_id= — aggregate OKX net value, positions, bills."""

    permission_classes = [IsAuthenticated, HasRequiredPermissions]
    required_permissions = ["assets:view"]

    def get(self, request):
        # credential_id presence check (400) — must be outside OKX try/except
        cid_str = request.query_params.get("credential_id")
        if not cid_str:
            return Response(
                {"detail": "credential_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Ownership check (404) — must be outside OKX try/except
        cred = _get_credential(request)

        # OKX calls — any failure → 502
        try:
            balance = okx_ext.get_balance(cred)
            positions = okx_ext.get_positions(cred)
            bills = okx_ext.get_bills(cred)
        except Exception as exc:
            logger.error("OKX assets summary failed: %s", exc)
            return Response(
                {"detail": f"OKX error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # Assemble net_value
        net_value: float = float(balance[0].get("totalEq") or 0) if balance else 0.0

        # Assemble currencies — only those with eqUsd > 0, sorted descending
        raw_details: list[dict] = balance[0].get("details", []) if balance else []
        currencies = sorted(
            [
                {
                    "ccy": d.get("ccy"),
                    "eq": d.get("eq"),
                    "eqUsd": d.get("eqUsd"),
                    "availBal": d.get("availBal"),
                    "frozenBal": d.get("frozenBal"),
                }
                for d in raw_details
                if float(d.get("eqUsd") or 0) > 0
            ],
            key=lambda d: float(d.get("eqUsd") or 0),
            reverse=True,
        )

        return Response(
            {
                "net_value": net_value,
                "currencies": currencies,
                "positions": positions,
                "bills": bills,
            }
        )
