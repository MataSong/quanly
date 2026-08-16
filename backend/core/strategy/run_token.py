"""RUN_TOKEN helpers: generate, hash, and resolve strategy run tokens.

Design decision on plaintext token lifecycle:
  - Token is generated at create-run time and returned ONCE to the caller.
  - Only its SHA-256 hash is persisted in StrategyRun.run_token_hash.
  - At start time, a NEW token is generated and the hash is updated; the new
    plaintext is passed to the Docker container via environment variable.
  - The plaintext NEVER touches the database.
"""
import hashlib
import secrets

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.strategy.models import StrategyRun


def generate_token() -> str:
    """Generate a cryptographically secure URL-safe random token (32 bytes → ~43 chars)."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Return the SHA-256 hex digest of the token string."""
    return hashlib.sha256(token.encode()).hexdigest()


def resolve_run(token: str) -> "StrategyRun | None":
    """Look up a StrategyRun by token hash.

    Returns the StrategyRun only if:
      - The hash matches a stored run_token_hash.
      - The run status is 'running'.

    Returns None if no match (caller should return 401).
    """
    from core.strategy.models import StrategyRun

    token_hash = hash_token(token)
    try:
        return StrategyRun.objects.select_related(
            "user", "strategy", "credential"
        ).get(run_token_hash=token_hash, status=StrategyRun.STATUS_RUNNING)
    except StrategyRun.DoesNotExist:
        return None
