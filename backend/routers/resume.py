"""
backend/routers/resume.py
-------------------------
POST /upload_resume — PDF/DOCX upload and profile parsing.
"""

import logging

from fastapi import APIRouter, Depends, File, UploadFile, status

from backend.dependencies import get_resume_service
from backend.exceptions import ValidationError
from backend.schemas.responses import ProfileResponse
from backend.services.resume_service import ResumeService

logger = logging.getLogger("job_agent.api.routes.resume")

router = APIRouter(prefix="", tags=["Resume"])


@router.post(
    "/upload_resume",
    response_model=ProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and parse a resume",
    description="Accepts a PDF (or DOCX) resume, saves it temporarily, and returns structured profile JSON.",
)
async def upload_resume(
    file: UploadFile = File(..., description="Resume file (PDF or DOCX)"),
    service: ResumeService = Depends(get_resume_service),
) -> ProfileResponse:
    if not file.filename:
        raise ValidationError("Filename is required")

    content = await file.read()
    saved_path = await service.save_upload(file.filename, content)
    profile = await service.parse_resume(saved_path)

    # Strip very large raw text from API response (optional)
    profile_out = {k: v for k, v in profile.items() if k != "raw_text"}
    if "raw_text" in profile:
        profile_out["raw_text_length"] = len(profile["raw_text"])

    logger.info("Profile parsed for %s (id=%s)", profile.get("name"), profile.get("profile_id"))
    return ProfileResponse(
        success=True,
        resume_path=str(saved_path),
        profile=profile_out,
    )
