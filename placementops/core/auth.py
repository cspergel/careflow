# @forgeplan-node: core-infrastructure
"""
Supabase JWT middleware for FastAPI.

Supports:
  - HS256 tokens validated against SUPABASE_JWT_SECRET
  - ES256 tokens validated via JWKS endpoint at SUPABASE_JWKS_URL

AuthContext is extracted from the validated token and attached to request.state.
organization_id is ALWAYS read from app_metadata — NEVER from user_metadata (AC12).
"""
# @forgeplan-decision: D-core-2-jwt-alg-detection -- Determine algorithm from JWT header alg field. Why: Supabase project may use either HS256 (pre-Oct-2025) or ES256 (post-Oct-2025); checking the header allows a single middleware to support both without config changes
# @forgeplan-spec: AC3
# @forgeplan-spec: AC12

import os
from dataclasses import dataclass
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# SUPABASE_JWKS_URL is read at import time to initialize the PyJWKClient early.
# SUPABASE_JWT_SECRET is read lazily (inside _decode_token) to support test environments
# where the env var is set after module imports but before the first request.
_SUPABASE_JWKS_URL: str | None = os.environ.get("SUPABASE_JWKS_URL")

# PyJWKClient caches JWKS keys with a 5-minute lifespan to avoid thundering-herd on key rotation
_jwks_client: "jwt.PyJWKClient | None" = None

if _SUPABASE_JWKS_URL:
    _jwks_client = jwt.PyJWKClient(_SUPABASE_JWKS_URL, lifespan=300)

_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class AuthContext:
    """
    Validated identity extracted from Supabase JWT.

    organization_id is sourced exclusively from app_metadata (not user_metadata)
    to prevent tenant spoofing via user-controlled metadata.
    """

    user_id: UUID
    organization_id: UUID
    role_key: str


def _decode_token(token: str) -> dict:
    """
    Decode and validate a Supabase JWT.

    Algorithm is determined from the unverified token header:
      - alg=HS256 → validate with SUPABASE_JWT_SECRET
      - alg=ES256 → validate with JWKS endpoint (PyJWKClient)

    Raises HTTPException 401 on any validation failure.
    """
    # Peek at the unverified header to determine algorithm
    try:
        unverified_header = jwt.get_unverified_header(token)
    except jwt.DecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token format",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    alg = unverified_header.get("alg", "HS256")
    if alg not in ("HS256", "ES256"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unsupported token algorithm",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if alg == "ES256":
        # @forgeplan-spec: AC3 — ES256 path
        if _jwks_client is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="ES256 token received but SUPABASE_JWKS_URL is not configured",
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            signing_key = _jwks_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["ES256"],
                audience="authenticated",
                options={"verify_exp": True},
            )
            return payload
        except jwt.ExpiredSignatureError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        except (jwt.InvalidTokenError, Exception) as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
    else:
        # @forgeplan-spec: AC3 — HS256 path (default)
        # Read lazily to support test environments where env var is set after module import
        _secret = os.environ.get("SUPABASE_JWT_SECRET", "")
        if not _secret:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="JWT secret not configured",
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            payload = jwt.decode(
                token,
                _secret,
                algorithms=["HS256"],
                audience="authenticated",
                options={"verify_exp": True},
            )
            return payload
        except jwt.ExpiredSignatureError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        except jwt.InvalidTokenError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc


def _extract_auth_context(payload: dict) -> AuthContext:
    """
    Extract AuthContext from validated JWT payload.

    CRITICAL: organization_id is read ONLY from app_metadata.
    Reading from user_metadata would allow tenant spoofing (AC12).
    """
    user_id_str = payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing sub claim",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # @forgeplan-spec: AC12 — org_id from app_metadata ONLY
    app_metadata = payload.get("app_metadata") or {}
    org_id_str = app_metadata.get("organization_id")
    role_key = app_metadata.get("role_key")
    if not role_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing required role claim",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not org_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing organization_id in app_metadata",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = UUID(user_id_str)
        organization_id = UUID(org_id_str)
    except (ValueError, AttributeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid UUID in token claims",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return AuthContext(
        user_id=user_id,
        organization_id=organization_id,
        role_key=role_key,
    )


async def get_auth_context(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> AuthContext:
    """
    FastAPI dependency that validates the JWT and returns AuthContext.

    Attaches AuthContext to request.state for downstream middleware access.
    Raises 401 if no bearer token present or token invalid.
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = _decode_token(credentials.credentials)
    auth_ctx = _extract_auth_context(payload)

    # Attach to request.state for middleware-layer access
    request.state.auth = auth_ctx

    return auth_ctx


def require_org_match(resource_org_id: str | UUID, auth: AuthContext) -> None:
    """
    Enforce tenant isolation at the application layer.

    Raises HTTP 403 if the authenticated user's org does not match the resource's org.
    This is defense-in-depth alongside RLS policies (AC4).
    """
    # @forgeplan-spec: AC4
    resource_org = UUID(str(resource_org_id))
    if auth.organization_id != resource_org:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: organization mismatch",
        )


async def get_db_role(user_id: UUID, organization_id: UUID, db: AsyncSession) -> str:
    """
    Fetch the authoritative role_key for a user from the database.

    Use this helper in sensitive operations (e.g. case status transitions) where
    the JWT-embedded role_key in AuthContext may be stale — a demoted user retains
    their old role in the JWT until it expires, but the DB always holds the current
    authoritative value.

    Raises HTTP 403 if the user is not found or does not belong to the expected org.
    """
    # Import here to avoid a circular import: auth <- database <- models <- auth
    from placementops.core.models.user import User  # noqa: PLC0415

    result = await db.execute(
        select(User.role_key).where(
            User.id == str(user_id),
            User.organization_id == str(organization_id),
            User.status == "active",
        )
    )
    role_key: str | None = result.scalar_one_or_none()
    if role_key is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User not found or inactive in this organization",
        )
    return role_key
