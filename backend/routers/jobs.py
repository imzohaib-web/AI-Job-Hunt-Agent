"""
backend/routers/jobs.py
-----------------------
POST /search_jobs — search job postings via job_search agent.
"""

import logging

from fastapi import APIRouter, Depends, status

from backend.dependencies import get_job_service
from backend.schemas.requests import SearchJobsRequest
from backend.schemas.responses import JobsListResponse
from backend.services.job_service import JobSearchService

logger = logging.getLogger("job_agent.api.routes.jobs")

router = APIRouter(tags=["Jobs"])


@router.post(
    "/search_jobs",
    response_model=JobsListResponse,
    status_code=status.HTTP_200_OK,
    summary="Search for job postings",
)
async def search_jobs(
    body: SearchJobsRequest,
    service: JobSearchService = Depends(get_job_service),
) -> JobsListResponse:
    jobs = await service.search(
        job_title=body.job_title,
        location=body.location,
        skills=body.skills,
        max_jobs=body.max_jobs,
    )
    logger.info("Returning %d jobs", len(jobs))
    return JobsListResponse(success=True, count=len(jobs), jobs=jobs)
