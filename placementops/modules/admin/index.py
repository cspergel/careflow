# @forgeplan-node: admin-surfaces
"""
Canonical public interface for the admin-surfaces module.

Other modules import the router from here:
    from placementops.modules.admin.index import router
"""

from placementops.modules.admin.router import router

__all__ = ["router"]
