"""
Preload state — shared between lifespan task (main.py) and health endpoint.
Kept in a separate module to avoid circular imports.
"""

# Mutable dict updated by main.py lifespan, read by routers/health.py
preload_status: dict = {
    "state": "pending",  # pending | loading | completed | failed
    "loaded": 0,
    "failed": 0,
    "total": 0,
    "current_product": None,
    "elapsed_seconds": None,
}


def get_preload_status() -> dict:
    """Return a snapshot of the current preload status."""
    return dict(preload_status)
