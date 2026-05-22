"""
backend/routers/health.py
-------------------------
GET / — API health and version info.
"""

from fastapi import APIRouter

from backend.schemas.responses import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/", response_model=HealthResponse, status_code=200)
async def root() -> HealthResponse:
    """Root endpoint — confirms the API is running."""
    return HealthResponse(message="AI Job Hunting Agent Running")
