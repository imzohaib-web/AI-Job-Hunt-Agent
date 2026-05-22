"""
backend/schemas/requests.py
---------------------------
Validated request bodies for POST endpoints.
"""

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class SearchJobsRequest(BaseModel):
    """Body for POST /search_jobs."""

    job_title: str = Field(..., min_length=1, max_length=200, examples=["AI Engineer"])
    location: str = Field(..., min_length=1, max_length=200, examples=["Remote"])
    skills: Optional[List[str]] = Field(
        default=None,
        description="Optional skills to improve demo/Serper search context",
    )
    max_jobs: int = Field(default=20, ge=1, le=50)

    @field_validator("job_title", "location")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()


class GenerateDocumentsRequest(BaseModel):
    """Body for POST /generate_documents."""

    resume_path: str = Field(
        ...,
        min_length=1,
        description="Absolute or project-relative path to uploaded resume (PDF/DOCX)",
    )
    job_description: str = Field(
        ...,
        min_length=20,
        description="Full job description text used for tailoring and prep",
    )
    job_title: Optional[str] = Field(
        default="Target Role",
        description="Role title (optional; improves tailoring quality)",
    )
    company: Optional[str] = Field(
        default="Target Company",
        description="Company name (optional)",
    )

    @field_validator("resume_path", "job_description", "job_title", "company")
    @classmethod
    def strip_optional(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if isinstance(v, str) else v
