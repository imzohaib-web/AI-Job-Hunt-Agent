"""
backend/dependencies.py
-----------------------
FastAPI dependency injection — shared service instances per request.
"""

from functools import lru_cache

from backend.services.analytics_service import AnalyticsService
from backend.services.documents_service import DocumentsService
from backend.services.job_service import JobSearchService
from backend.services.resume_service import ResumeService


@lru_cache
def get_resume_service() -> ResumeService:
    return ResumeService()


@lru_cache
def get_job_service() -> JobSearchService:
    return JobSearchService()


@lru_cache
def get_documents_service() -> DocumentsService:
    return DocumentsService()


@lru_cache
def get_analytics_service() -> AnalyticsService:
    return AnalyticsService()
