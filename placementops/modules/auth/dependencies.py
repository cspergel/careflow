# @forgeplan-node: auth-module
"""
FastAPI Depends() factories for RBAC enforcement.

These are the canonical exports imported by ALL other modules:

    from placementops.modules.auth.dependencies import require_role, require_write_permission

require_role(*allowed_roles):
    Returns a Depends() callable that raises HTTP 403 if the authenticated
    user's role_key (from the DB User row — not JWT) is not in allowed_roles.

require_write_permission:
    A Depends() callable that raises HTTP 403 for read_only users on any
    mutating request method (POST, PATCH, PUT, DELETE). Must intercept the
    request before any handler logic executes.

RolePermissions:
    Importable dict of role_key → frozenset of allowed action names.
    Used for documentation and by other modules — NOT the enforcement mechanism
    (that is require_role).
"""
# @forgeplan-spec: AC6
# @forgeplan-spec: AC7
# @forgeplan-spec: AC8
# @forgeplan-spec: AC9
# @forgeplan-spec: AC10
# @forgeplan-spec: AC11
# @forgeplan-spec: AC12
# @forgeplan-decision: D-auth-1-db-role-lookup -- require_role fetches User row from DB on every call. Why: JWT role_key in app_metadata can be stale after a role change; DB row is always authoritative per AC12

from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from placementops.core.auth import AuthContext, get_auth_context
from placementops.core.database import get_db
from placementops.core.models import User


# ── RBAC Role-Permission Mapping ─────────────────────────────────────────────
# @forgeplan-spec: AC6
# @forgeplan-spec: AC7
# @forgeplan-spec: AC8
# @forgeplan-spec: AC9
# @forgeplan-spec: AC10
# @forgeplan-spec: AC11

RolePermissions: dict[str, frozenset[str]] = {
    "admin": frozenset([
        # Full access across all modules
        "cases:create", "cases:read", "cases:update", "cases:delete",
        "assessments:create", "assessments:read", "assessments:update",
        "facilities:create", "facilities:read", "facilities:update", "facilities:delete",
        "matching:generate",
        "outreach:create", "outreach:approve", "outreach:send",
        "outcomes:record", "outcomes:read",
        "analytics:dashboard", "analytics:manager_summary", "analytics:outreach_performance",
        "queues:operations",
        "admin:users", "admin:config",
    ]),
    "intake_staff": frozenset([
        "cases:create", "cases:read", "cases:update",
        "cases:intake_complete",
    ]),
    "clinical_reviewer": frozenset([
        "cases:read",
        "assessments:create", "assessments:read", "assessments:update",
        "assessments:finalize",
        "cases:backward_transition",
        "queues:operations",
    ]),
    "placement_coordinator": frozenset([
        "cases:read", "cases:update",
        "matching:generate",
        "outreach:create", "outreach:approve", "outreach:send",
        "outcomes:record", "outcomes:read",
        "queues:operations",
        "facilities:read",
    ]),
    "manager": frozenset([
        "cases:read",
        "assessments:read",
        "facilities:read",
        "outreach:read",
        "outcomes:read",
        "analytics:dashboard", "analytics:manager_summary", "analytics:outreach_performance",
        "queues:operations",
        "cases:close",
    ]),
    "read_only": frozenset([
        "cases:read",
        "facilities:read",
        "assessments:read",
    ]),
}

# Mutating HTTP methods — read_only is blocked from all of these
_MUTATING_METHODS: frozenset[str] = frozenset(["POST", "PATCH", "PUT", "DELETE"])


# ── Internal: fetch role_key from DB row ──────────────────────────────────────

async def _get_db_role_key(user_id: UUID, session: AsyncSession) -> str:
    """
    Return the role_key from the User database row.

    AC12: authoritative source is the DB row, not the JWT claim.
    Raises HTTP 401 if the user is not found in the database.
    """
    # @forgeplan-spec: AC12
    user = await session.get(User, str(user_id))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated user not found in database",
        )
    return user.role_key


# ── require_role ──────────────────────────────────────────────────────────────

def require_role(*allowed_roles: str) -> Depends:
    """
    FastAPI Depends() factory: enforce that the caller's role is in allowed_roles.

    Returns a Depends() object directly — use it without wrapping in Depends():

    Usage:
        @router.post("/cases", dependencies=[require_role("admin", "intake_staff")])

    Returns HTTP 403 if the caller's DB role_key is not in the allowed set.
    Returns HTTP 401 if the caller is unauthenticated (propagated from get_auth_context).

    AC6:  intake_staff permitted for case creation
    AC7:  clinical_reviewer permitted for assessment creation
    AC8:  placement_coordinator permitted for match generation
    AC9:  manager permitted for analytics
    AC10: admin permitted everywhere
    AC11: read_only blocked from analytics and all mutating endpoints
    """
    # @forgeplan-spec: AC6
    # @forgeplan-spec: AC7
    # @forgeplan-spec: AC8
    # @forgeplan-spec: AC9
    # @forgeplan-spec: AC10
    # @forgeplan-spec: AC11
    allowed: frozenset[str] = frozenset(allowed_roles)

    async def _check_role(
        auth_ctx: AuthContext = Depends(get_auth_context),
        session: AsyncSession = Depends(get_db),
    ) -> AuthContext:
        # Fetch role from DB — not from JWT claims (AC12)
        db_role = await _get_db_role_key(auth_ctx.user_id, session)

        if db_role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{db_role}' is not permitted for this action",
            )
        return auth_ctx

    return Depends(_check_role)


# ── require_write_permission ──────────────────────────────────────────────────

async def _check_write_permission(
    request: Request,
    auth_ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> None:
    """
    Enforce that read_only users cannot execute mutating requests.

    Intercepts POST, PATCH, PUT, DELETE before any handler logic runs.
    Returns HTTP 403 for read_only role on any of those methods.

    AC11: read_only → 403 on POST/PATCH/DELETE; handler body never called.
    The constraint is: "require_write_permission Depends() must intercept the
    request before the handler body executes — no partial writes may occur."
    """
    # @forgeplan-spec: AC11
    if request.method in _MUTATING_METHODS:
        # Fetch role from DB — not from JWT claims (AC12)
        db_role = await _get_db_role_key(auth_ctx.user_id, session)
        if db_role == "read_only":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="read_only role cannot perform mutating operations",
            )


# Export as a Depends() object so other modules can write:
#   @router.post("/cases", dependencies=[require_write_permission])
# Do NOT wrap in Depends() — it already is one.
require_write_permission: Depends = Depends(_check_write_permission)
