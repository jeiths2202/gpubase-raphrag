"""API Routers"""

from .credentials import router as credentials_router
from .search import router as search_router
from .jobs import router as jobs_router
from .reports import router as reports_router
from .dashboard import router as dashboard_router
from .cache import router as cache_router
from .tasks import router as tasks_router

__all__ = ["credentials_router", "search_router", "jobs_router", "reports_router", "dashboard_router", "cache_router", "tasks_router"]
