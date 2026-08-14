"""Audit decorator for DRF view methods.

Usage:

    @audit("accounts.user.create")
    def create(self, request, *args, **kwargs):
        ...
        return Response(...)

Writes an AuditLog row after the view returns.
Never raises — audit failure must not break the request.
"""
import functools
import logging
from typing import Callable, Union

log = logging.getLogger("quanly.audit")


def _client_ip(request) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def _extract_target_id(response) -> str:
    body = getattr(response, "data", None)
    if not isinstance(body, dict):
        return ""
    if "id" in body:
        return str(body["id"])
    data = body.get("data")
    if isinstance(data, dict) and "id" in data:
        return str(data["id"])
    return ""


def audit(action: Union[str, Callable]):
    """Decorator that writes an AuditLog entry after the view method returns."""
    def deco(view_method):
        @functools.wraps(view_method)
        def wrapper(self, request, *args, **kwargs):
            response = view_method(self, request, *args, **kwargs)
            try:
                from .models import AuditLog
                actor = request.user if request.user.is_authenticated else None
                resolved_action = action(request, response) if callable(action) else action
                detail = {
                    "ip": _client_ip(request),
                    "ua": request.META.get("HTTP_USER_AGENT", "")[:200],
                    "status_code": getattr(response, "status_code", None),
                    "target_id": _extract_target_id(response),
                }
                # view 可通过 request._audit_extra 补充非敏感上下文(如 credential_id/inst_id);
                # 失败请求(502)也能借此在审计里留下溯源信息。
                extra = getattr(request, "_audit_extra", None)
                if isinstance(extra, dict):
                    detail.update(extra)
                AuditLog.objects.create(
                    user=actor,
                    action=resolved_action,
                    detail=detail,
                )
            except Exception as exc:  # never break the request
                log.warning("audit write failed: %s", exc)
            return response
        return wrapper
    return deco
