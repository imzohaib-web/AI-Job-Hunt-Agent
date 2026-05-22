"""
backend/routers/analytics.py
----------------------------
GET /analytics — dashboard metrics from SQLite.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, status

from backend.dependencies import get_analytics_service
from backend.schemas.responses import AnalyticsResponse
from backend.services.analytics_service import AnalyticsService

logger = logging.getLogger("job_agent.api.routes.analytics")

router = APIRouter(tags=["Analytics"])


@router.get(
    "/analytics",
    response_model=AnalyticsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get job search and match analytics",
)
async def get_analytics(
    profile_id: Optional[int] = Query(
        default=None,
        description="Optional profile ID to include skill breakdown",
    ),
    service: AnalyticsService = Depends(get_analytics_service),
) -> AnalyticsResponse:
    metrics = await service.get_summary(profile_id)
    return AnalyticsResponse(success=True, metrics=metrics)
