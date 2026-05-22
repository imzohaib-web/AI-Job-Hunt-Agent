"""API route modules."""

from backend.routers.analytics import router as analytics_router
from backend.routers.documents import router as documents_router
from backend.routers.health import router as health_router
from backend.routers.jobs import router as jobs_router
from backend.routers.resume import router as resume_router

__all__ = [
    "health_router",
    "resume_router",
    "jobs_router",
    "documents_router",
    "analytics_router",
]
