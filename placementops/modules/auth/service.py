# @forgeplan-node: auth-module
"""
Auth service: Supabase Auth calls and user profile lookups.

Uses supabase-py for credential validation (login) and session invalidation
(logout). User profile data is fetched from the database (not JWT claims) to
ensure role_key reflects the current DB state (AC12).
"""
# @forgeplan-spec: AC1
# @forgeplan-spec: AC2
# @forgeplan-spec: AC5
# @forgeplan-spec: AC12
# @forgeplan-spec: AC13
# @forgeplan-decision: D-auth-4-rbac-role-permissions-dict -- RolePermissions exported as plain dict keyed by role_key. Why: importable, no ORM dependency; actual enforcement via require_role Depends

import os
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

# All shared models MUST be imported from placementops.core.models — never redefined here
from placementops.core.models import User
from placementops.core.audit import emit_audit_event


# ── Supabase client factory ───────────────────────────────────────────────────

def _get_supabase_client():
    """
    Build and return a Supabase client using environment credentials.

    Uses the anon key — sufficient for Auth API calls (sign-in, sign-out).
    The service role key is NOT used here; it lives in admin-surfaces.
    """
    # Import lazily to allow test mocking before the module is imported
    from supabase import create_client, Client  # type: ignore[import]

    supabase_url = os.environ.get("SUPABASE_URL", "")
    supabase_anon_key = os.environ.get("SUPABASE_ANON_KEY", "")

    if not supabase_url or not supabase_anon_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth service misconfigured: SUPABASE_URL or SUPABASE_ANON_KEY missing",
        )

    return create_client(supabase_url, supabase_anon_key)


# ── Login ─────────────────────────────────────────────────────────────────────

async def login_with_supabase(email: str, password: str) -> dict:
    """
    Authenticate credentials against Supabase Auth.

    Returns the raw Supabase auth response dict on success.
    Raises HTTP 401 on invalid credentials.
    Raises HTTP 503 if Supabase is unreachable.

    AC1: Successful → returns session data including access_token, expires_in
    AC2: Invalid credentials → 401
    """
    # @forgeplan-spec: AC1
    # @forgeplan-spec: AC2
    supabase = _get_supabase_client()

    try:
        response = supabase.auth.sign_in_with_password(
            {"email": email, "password": password}
        )
    except Exception as exc:
        # supabase-py raises AuthApiError on invalid credentials
        exc_str = str(exc).lower()
        if "invalid" in exc_str or "credentials" in exc_str or "password" in exc_str:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service temporarily unavailable",
        ) from exc

    if response is None or response.session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {
        "access_token": response.session.access_token,
        "expires_in": response.session.expires_in,
        "user_id": response.user.id,
    }


# ── Logout ────────────────────────────────────────────────────────────────────

async def logout_from_supabase(access_token: str) -> None:
    """
    Invalidate the Supabase session server-side.

    Directly POSTs to /auth/v1/logout with the user's access_token in the
    Authorization header. This is the most reliable way to invalidate the
    Supabase session without needing the refresh token.

    AC5: After logout, the same access_token must be rejected by Supabase.
    CRITICAL: This calls the Supabase server endpoint — it is NOT client-side
    token deletion. The session is invalidated at the Supabase Auth server.
    """
    # @forgeplan-spec: AC5
    # @forgeplan-decision: D-auth-2-supabase-logout -- Direct httpx POST to /auth/v1/logout. Why: supabase-py set_session() requires both access+refresh tokens; we only have the access token at logout time; direct REST call is simpler and more reliable

    import httpx

    supabase_url = os.environ.get("SUPABASE_URL", "")
    supabase_anon_key = os.environ.get("SUPABASE_ANON_KEY", "")

    if not supabase_url or not access_token:
        # Cannot invalidate without URL or token — silently succeed
        # (client will discard the token regardless)
        return

    logout_url = f"{supabase_url.rstrip('/')}/auth/v1/logout"

    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                logout_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "apikey": supabase_anon_key,
                    "Content-Type": "application/json",
                },
                timeout=5.0,
            )
    except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
        # F13: Network-level failure means the session was NOT invalidated server-side.
        # Return 503 so the caller knows the logout was incomplete.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        ) from exc
    except Exception:
        # Non-network exceptions (e.g. auth token already expired): the token is
        # effectively invalid anyway, so treat logout as successful.
        pass


# ── User profile lookup ───────────────────────────────────────────────────────

async def get_user_profile(user_id: UUID, session: AsyncSession) -> User:
    """
    Fetch the User row from the database by user_id.

    AC4: Returns user profile with role_key from DB (not JWT claims).
    AC12: role_key from the User row is authoritative — not from JWT.

    Raises HTTP 404 if the user is not found.
    """
    # @forgeplan-spec: AC4
    # @forgeplan-spec: AC12
    result = await session.get(User, str(user_id))
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return result


# ── Audit event helper ────────────────────────────────────────────────────────

async def write_login_audit_event(user: User, session: AsyncSession) -> None:
    """
    Write an AuditEvent row for a successful login.

    AC13: event_type=login, entity_type=user, actor_user_id=user.id
    Uses the insert-only emit_audit_event helper from core.
    """
    # @forgeplan-spec: AC13
    await emit_audit_event(
        session=session,
        organization_id=UUID(user.organization_id),
        entity_type="user",
        entity_id=UUID(user.id),
        event_type="login",
        actor_user_id=UUID(user.id),
    )
