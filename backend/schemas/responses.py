"""
backend/schemas/responses.py
----------------------------
Standard API response shapes.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    message: str = "AI Job Hunting Agent Running"


class ProfileResponse(BaseModel):
    success: bool = True
    resume_path: str
    profile: Dict[str, Any]


class JobItem(BaseModel):
    title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    url: Optional[str] = None
    description: Optional[str] = None
    salary: Optional[str] = None
    source: Optional[str] = None
    job_id: Optional[int] = None


class JobsListResponse(BaseModel):
    success: bool = True
    count: int
    jobs: List[Dict[str, Any]]


class TailoredResumeOut(BaseModel):
    tailored_summary: Optional[str] = None
    skills_to_highlight: List[str] = Field(default_factory=list)
    experience: List[Dict[str, Any]] = Field(default_factory=list)
    ats_keywords_added: List[str] = Field(default_factory=list)
    tailoring_notes: Optional[str] = None
    resume_path: Optional[str] = None


class CoverLetterOut(BaseModel):
    content: str = ""
    txt_path: Optional[str] = None
    docx_path: Optional[str] = None


class InterviewPrepOut(BaseModel):
    prep: Dict[str, Any] = Field(default_factory=dict)
    markdown: Optional[str] = None
    file_path: Optional[str] = None


class GenerateDocumentsResponse(BaseModel):
    success: bool = True
    tailored_resume: Dict[str, Any]
    cover_letter: Dict[str, Any]
    interview_prep: Dict[str, Any]


class AnalyticsResponse(BaseModel):
    success: bool = True
    metrics: Dict[str, Any]
