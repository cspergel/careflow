# @forgeplan-node: auth-module
"""
Auth router: login, me, logout endpoints.

All endpoints registered under /api/v1/auth (prefix applied at app level).

POST /auth/login  → LoginResponse  (AC1, AC2, AC3, AC13)
GET  /auth/me     → UserProfileResponse  (AC4)
POST /auth/logout → HTTP 204  (AC5)
"""
# @forgeplan-spec: AC1
# @forgeplan-spec: AC2
# @forgeplan-spec: AC3
# @forgeplan-spec: AC4
# @forgeplan-spec: AC5
# @forgeplan-spec: AC13

from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from placementops.core.auth import AuthContext, get_auth_context
from placementops.core.database import get_db

from placementops.modules.auth.rate_limiter import check_rate_limit, get_client_ip
from placementops.modules.auth.schemas import LoginRequest, LoginResponse, UserProfileResponse
from placementops.modules.auth.service import (
    get_user_profile,
    login_with_supabase,
    logout_from_supabase,
    write_login_audit_event,
)

router = APIRouter(prefix="/auth", tags=["auth"])


# ── POST /auth/login ──────────────────────────────────────────────────────────

@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate with email and password",
)
async def login(
    request: Request,
    body: LoginRequest,
    session: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """
    POST /api/v1/auth/login

    Validates credentials against Supabase Auth.
    Returns a JWT access token and user metadata on success.

    AC1: 200 LoginResponse with access_token, token_type=bearer, expires_in,
         user_id, organization_id, role_key
    AC2: 401 on invalid credentials
    AC3: 429 on 11th request within 60 seconds from the same IP
    AC13: Writes AuditEvent(entity_type=user, event_type=login, actor_user_id=user.id)
    """
    # @forgeplan-spec: AC3
    ip = get_client_ip(request)
    check_rate_limit(ip)

    # @forgeplan-spec: AC1
    # @forgeplan-spec: AC2
    supabase_result = await login_with_supabase(body.email, body.password)

    # @forgeplan-spec: AC12 — fetch role_key and org from DB row, not JWT
    user = await get_user_profile(UUID(supabase_result["user_id"]), session)

    # @forgeplan-spec: AC13 — write audit event before committing
    await write_login_audit_event(user, session)
    await session.commit()

    return LoginResponse(
        access_token=supabase_result["access_token"],
        token_type="bearer",
        expires_in=supabase_result["expires_in"],
        user_id=UUID(user.id),
        organization_id=UUID(user.organization_id),
        role_key=user.role_key,
    )


# ── GET /auth/me ──────────────────────────────────────────────────────────────

@router.get(
    "/me",
    response_model=UserProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Get the authenticated user's profile",
)
async def me(
    auth_ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> UserProfileResponse:
    """
    GET /api/v1/auth/me

    Returns the authenticated user's profile. Requires a valid JWT in the
    Authorization: Bearer header. Returns 401 if token is absent or expired.

    AC4: 200 with user_id, organization_id, role_key, email, full_name
    AC5: After logout, same token returns 401 (enforced by Supabase middleware)
    """
    # @forgeplan-spec: AC4
    user = await get_user_profile(auth_ctx.user_id, session)

    return UserProfileResponse(
        user_id=UUID(user.id),
        organization_id=UUID(user.organization_id),
        role_key=user.role_key,
        email=user.email,
        full_name=user.full_name,
    )


# ── POST /auth/logout ─────────────────────────────────────────────────────────

@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Invalidate the current session",
)
async def logout(
    request: Request,
    auth_ctx: AuthContext = Depends(get_auth_context),
) -> Response:
    """
    POST /api/v1/auth/logout

    Calls Supabase Auth signOut to server-side invalidate the session.
    Returns HTTP 204 No Content on success.

    AC5: Session is invalidated at Supabase; subsequent /me requests with
         the same token return 401.

    CRITICAL: Logout must call Supabase server-side signOut — client-side
    token deletion alone is insufficient (spec constraint and failure mode).
    """
    # @forgeplan-spec: AC5
    # Extract the raw Bearer token from the Authorization header
    authorization = request.headers.get("Authorization", "")
    access_token = ""
    if authorization.startswith("Bearer ") or authorization.startswith("bearer "):
        access_token = authorization.split(" ", 1)[1]

    await logout_from_supabase(access_token)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
