# @forgeplan-node: facilities-module
"""
Facilities module — facility directory CRUD for PlacementOps.

Exports the FastAPI router for registration in main.py:
    from placementops.modules.facilities import router
    app.include_router(router, prefix="/api/v1")
"""

from placementops.modules.facilities.router import router

__all__ = ["router"]
