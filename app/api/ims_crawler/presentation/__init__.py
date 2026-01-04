"""
Presentation Layer - FastAPI Routers and API Models

HTTP interface for IMS Crawler features.
Handles request/response serialization and API documentation.
"""

from .routers import credentials_router, search_router, jobs_router, reports_router, dashboard_router, cache_router, tasks_router

__all__ = ["credentials_router", "search_router", "jobs_router", "reports_router", "dashboard_router", "cache_router", "tasks_router"]
