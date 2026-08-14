"""Trading API views — OKX spot + perpetual swap order management.

All credential lookups are scoped to request.user (multi-tenant).
Flag follows credential.env: sim→"1", live→"0".
Zero mock in product paths — only test suites use unittest.mock.
"""
import logging

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.accounts.drf import HasRequiredPermissions, require_perm
from core.audit.decorators import audit
from core.credentials.models import Credential

from . import okx_ext
from .models import Order
from .serializers import CancelOrderSerializer, OrderSerializer, PlaceOrderSerializer

logger = logging.getLogger("quanly.trading")


def _get_credential(request, credential_id: int) -> Credential:
    """Return credential owned by request.user, or raise 404."""
    return get_object_or_404(Credential, id=credential_id, user=request.user)


class PlaceOrderView(APIView):
    """POST /api/trading/order — place a spot or swap order on OKX."""

    permission_classes = [IsAuthenticated]

    @audit("trading.place_order")
    def post(self, request):
        require_perm(request, "trading:place_order")

        ser = PlaceOrderSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data

        cred = _get_credential(request, d["credential_id"])

        try:
            okx_data = okx_ext.place_order(
                cred,
                inst_type=d["inst_type"],
                inst_id=d["inst_id"],
                side=d["side"],
                ord_type=d["ord_type"],
                sz=d["sz"],
                px=d["px"] or None,
                pos_side=d["pos_side"],
                td_mode=d["td_mode"] or None,
                reduce_only=d["reduce_only"] or False,
            )
        except RuntimeError as exc:
            logger.error("OKX place_order failed: %s", exc)
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        # Determine resolved td_mode (mirrors okx_ext logic)
        if d["td_mode"]:
            resolved_td_mode = d["td_mode"]
        else:
            resolved_td_mode = "cash" if d["inst_type"].upper() == "SPOT" else "cross"

        order = Order.objects.create(
            user=request.user,
            credential=cred,
            env=cred.env,
            inst_type=d["inst_type"].upper(),
            inst_id=d["inst_id"],
            side=d["side"],
            ord_type=d["ord_type"],
            pos_side=d["pos_side"] or "",
            sz=d["sz"],
            px=d["px"] or "",
            td_mode=resolved_td_mode,
            reduce_only=bool(d["reduce_only"]),
            okx_ord_id=okx_data.get("ordId", ""),
            cl_ord_id=okx_data.get("clOrdId", ""),
            state=okx_data.get("sCode", "live"),
        )

        return Response(
            {
                "order": OrderSerializer(order).data,
                "okx": okx_data,
            },
            status=status.HTTP_201_CREATED,
        )


class CancelOrderView(APIView):
    """POST /api/trading/cancel — cancel an open order on OKX."""

    permission_classes = [IsAuthenticated]

    @audit("trading.cancel_order")
    def post(self, request):
        require_perm(request, "trading:cancel")

        ser = CancelOrderSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data

        cred = _get_credential(request, d["credential_id"])

        try:
            okx_data = okx_ext.cancel_order(cred, d["inst_id"], d["ord_id"])
        except RuntimeError as exc:
            logger.error("OKX cancel_order failed: %s", exc)
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        return Response({"okx": okx_data}, status=status.HTTP_200_OK)


class OrdersView(APIView):
    """GET /api/trading/orders?credential_id=&inst_type= — list open orders from OKX."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        require_perm(request, "trading:view")

        credential_id = request.query_params.get("credential_id")
        if not credential_id:
            return Response(
                {"detail": "credential_id is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        cred = _get_credential(request, int(credential_id))
        inst_type = request.query_params.get("inst_type")

        try:
            orders = okx_ext.get_orders(cred, inst_type=inst_type)
        except RuntimeError as exc:
            logger.error("OKX get_orders failed: %s", exc)
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        return Response({"data": orders})


class PositionsView(APIView):
    """GET /api/trading/positions?credential_id=&inst_type= — get positions from OKX."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        require_perm(request, "trading:view")

        credential_id = request.query_params.get("credential_id")
        if not credential_id:
            return Response(
                {"detail": "credential_id is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        cred = _get_credential(request, int(credential_id))
        inst_type = request.query_params.get("inst_type")

        try:
            positions = okx_ext.get_positions(cred, inst_type=inst_type)
        except RuntimeError as exc:
            logger.error("OKX get_positions failed: %s", exc)
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        return Response({"data": positions})


class BalanceView(APIView):
    """GET /api/trading/balance?credential_id= — get account balance from OKX."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        require_perm(request, "trading:view")

        credential_id = request.query_params.get("credential_id")
        if not credential_id:
            return Response(
                {"detail": "credential_id is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        cred = _get_credential(request, int(credential_id))

        try:
            balance = okx_ext.get_balance(cred)
        except RuntimeError as exc:
            logger.error("OKX get_balance failed: %s", exc)
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        return Response({"data": balance})
