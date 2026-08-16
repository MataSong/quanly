"""DRF Authentication class for strategy runner containers.

RunTokenAuthentication reads the X-Run-Token header, resolves the
StrategyRun, and attaches it to request.strategy_run.

This auth class is intentionally narrow — it is ONLY used on the
strategy runner API endpoints, not on the main JWT-protected APIs.
"""
import logging

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from core.strategy.run_token import resolve_run

logger = logging.getLogger("quanly.strategy")


class RunTokenAuthentication(BaseAuthentication):
    """Authenticate strategy runner containers via X-Run-Token header.

    On success:  returns (run.user, run)  — DRF sets request.user = run.user
                 and request.auth = run.  Callers can also access run via
                 request.auth (which is the StrategyRun instance).
    On failure:  returns None → DRF will try the next authenticator,
                 eventually returning 401 if none succeed.
    """

    HEADER = "HTTP_X_RUN_TOKEN"

    def authenticate(self, request):
        token = request.META.get(self.HEADER, "").strip()
        if not token:
            return None  # Let other authenticators handle it

        run = resolve_run(token)
        if run is None:
            logger.warning("RunTokenAuthentication: invalid or expired token")
            raise AuthenticationFailed("Invalid or expired run token.")

        # Attach run to request so views can access it directly.
        request.strategy_run = run
        return (run.user, run)

    def authenticate_header(self, request):
        return "X-Run-Token"
