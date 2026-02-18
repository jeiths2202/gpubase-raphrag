"""API routers for Legacy Modernization platform."""

from .analysis import router as analysis_router
from .reports import router as reports_router

__all__ = ["analysis_router", "reports_router"]
