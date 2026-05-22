"""
backend/services/job_service.py
-------------------------------
Job search via Agents.job_search.run_job_search.
"""

import asyncio
import logging
from typing import List, Optional

from backend.exceptions import AgentProcessingError

logger = logging.getLogger("job_agent.api.jobs")


class JobSearchService:
    """Wraps the job search agent for API consumption."""

    async def search(
        self,
        job_title: str,
        location: str,
        skills: Optional[List[str]] = None,
        max_jobs: int = 20,
    ) -> list:
        from Agents.job_search import run_job_search

        titles = [t.strip() for t in job_title.split(",") if t.strip()] or [job_title]
        locations = [l.strip() for l in location.split(",") if l.strip()] or [location]
        skill_list = skills or []

        logger.info("Job search: titles=%s locations=%s", titles, locations)
        try:
            jobs = await asyncio.to_thread(
                run_job_search,
                job_titles=titles,
                locations=locations,
                skills=skill_list,
                max_jobs=max_jobs,
            )
            return jobs
        except Exception as e:
            logger.exception("Job search failed")
            raise AgentProcessingError(f"Job search failed: {e}") from e
