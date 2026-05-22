"""
backend/services/documents_service.py
-------------------------------------
Tailored resume, cover letter, and interview prep generation.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict

from backend.exceptions import AgentProcessingError
from backend.services.resume_service import ResumeService

logger = logging.getLogger("job_agent.api.documents")


class DocumentsService:
    """
    Builds a job dict from description text and runs tailoring agents.
    Uses orchestrator.run_single_job_pipeline when possible, or direct agent calls.
    """

    def __init__(self) -> None:
        self._resume_svc = ResumeService()

    @staticmethod
    def build_job_from_request(
        job_description: str,
        job_title: str,
        company: str,
    ) -> Dict[str, Any]:
        """Minimal job dict expected by resume_tailor / cover_letter / interview_prep."""
        return {
            "title": job_title,
            "company": company,
            "description": job_description,
            "location": "",
            "url": "",
        }

    async def generate_all(
        self,
        resume_path: str,
        job_description: str,
        job_title: str = "Target Role",
        company: str = "Target Company",
    ) -> Dict[str, Any]:
        """
        Parse profile (if needed) and generate tailored resume, cover letter, interview prep.
        Runs synchronous agent code in thread pool for async-friendly API.
        """
        path = self._resume_svc.resolve_resume_path(resume_path)
        job = self.build_job_from_request(job_description, job_title, company)

        logger.info("Generating documents for %s — role: %s @ %s", path, job_title, company)

        def _run_pipeline() -> Dict[str, Any]:
            from Agents.profile_parser import run_profile_parser
            from Agents.comapany_research import research_company
            from Agents.resume_tailor import run_resume_tailor
            from Agents.cover_letter import run_cover_letter_agent
            from Agents.interview_prep import run_interview_prep_agent

            profile = run_profile_parser(str(path))
            company_info = research_company(job.get("company", ""), job.get("title", ""))
            tailored = run_resume_tailor(profile, job)
            cover = run_cover_letter_agent(profile, job, company_info)
            interview = run_interview_prep_agent(profile, job, company_info)
            return {
                "tailored_resume": tailored,
                "cover_letter": cover,
                "interview_prep": interview,
            }

        try:
            return await asyncio.to_thread(_run_pipeline)
        except Exception as e:
            logger.exception("Document generation failed")
            raise AgentProcessingError(f"Document generation failed: {e}") from e
