# @forgeplan-node: auth-module
"""
Auth module startup validation and middleware utilities.

Provides:
  - validate_jwt_secret(): startup guard that rejects known weak/placeholder
    JWT secrets before the server accepts any requests.

validate_jwt_secret() is called automatically at module import time (which
occurs when the auth router is registered in main.py). It is a no-op when
the TESTING or TEST environment variable is set to a truthy value, allowing
test suites to use short or predictable secrets.

To call it explicitly from a FastAPI lifespan handler instead:

    from placementops.modules.auth.middleware import validate_jwt_secret

    @asynccontextmanager
    async def lifespan(app):
        validate_jwt_secret()
        yield
"""
# F7 fix: reject known placeholder/weak JWT secrets at startup so that
# misconfigured production deployments fail fast rather than silently accepting
# forged tokens.

import os

# ── Constants ─────────────────────────────────────────────────────────────────

# Known placeholder values that developers sometimes leave in .env files.
# Any of these in production is a critical misconfiguration.
_WEAK_SECRETS: frozenset[str] = frozenset([
    "your-secret-key",
    "secret",
    "changeme",
    "change-me",
    "changethis",
    "test-secret",
])

# Minimum acceptable secret length for HS256 signatures.
# NIST SP 800-107 recommends at least 256 bits (32 bytes) for HMAC-SHA256.
_MIN_SECRET_LENGTH: int = 32


# ── Public API ────────────────────────────────────────────────────────────────

def validate_jwt_secret() -> None:
    """
    Validate that SUPABASE_JWT_SECRET is not a known weak placeholder and
    meets the minimum length requirement for production use.

    Behaviour
    ---------
    - Skipped entirely when the TESTING or TEST environment variable is set
      to any non-empty value (e.g. "1", "true"). This allows test suites to
      use short or predictable secrets without triggering the guard.
    - Raises RuntimeError if the secret matches a known placeholder value.
    - Raises RuntimeError if the secret is shorter than _MIN_SECRET_LENGTH.

    When to call
    ------------
    This function is invoked automatically at the bottom of this module
    (i.e. at import time, which happens when the auth router is registered
    in main.py). It can also be called explicitly from a FastAPI lifespan
    handler for belt-and-suspenders assurance.
    """
    # Allow any secret in test/CI mode — suites use short, predictable values
    if os.environ.get("TESTING") or os.environ.get("TEST"):
        return

    secret: str = os.environ.get("SUPABASE_JWT_SECRET", "")

    if secret.lower() in _WEAK_SECRETS:
        raise RuntimeError(
            f"SUPABASE_JWT_SECRET is set to a known placeholder value "
            f"({secret!r}). Replace it with a strong, randomly-generated "
            "secret before starting the server in a non-test environment."
        )

    if len(secret) < _MIN_SECRET_LENGTH:
        raise RuntimeError(
            f"SUPABASE_JWT_SECRET is too short ({len(secret)} characters). "
            f"A minimum of {_MIN_SECRET_LENGTH} characters is required. "
            "Use a randomly-generated secret of at least 32 characters."
        )


# ── Module-init guard ─────────────────────────────────────────────────────────
# Run the check at import time so that any misconfiguration is caught as soon
# as the auth module is loaded (i.e. at server startup), not on the first
# request. The TESTING/TEST gate above ensures test suites are unaffected.
validate_jwt_secret()
