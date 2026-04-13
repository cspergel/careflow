# @forgeplan-node: auth-module
"""
Auth module for PlacementOps.

Provides:
  - POST /api/v1/auth/login
  - GET  /api/v1/auth/me
  - POST /api/v1/auth/logout

Exports for all other modules:
  - require_role(*allowed_roles) -> FastAPI Depends() factory
  - require_write_permission -> FastAPI Depends() callable
  - RolePermissions -> dict[str, set[str]]
"""

from placementops.modules.auth.middleware import validate_jwt_secret
from placementops.modules.auth.dependencies import require_role, require_write_permission, RolePermissions
from placementops.modules.auth.router import router

__all__ = [
    "router",
    "require_role",
    "require_write_permission",
    "RolePermissions",
    "validate_jwt_secret",
]
