"""
backend/routers/documents.py
----------------------------
POST /generate_documents — tailored resume, cover letter, interview prep.
"""

import logging

from fastapi import APIRouter, Depends, status

from backend.dependencies import get_documents_service
from backend.schemas.requests import GenerateDocumentsRequest
from backend.schemas.responses import GenerateDocumentsResponse
from backend.services.documents_service import DocumentsService

logger = logging.getLogger("job_agent.api.routes.documents")

router = APIRouter(tags=["Documents"])


@router.post(
    "/generate_documents",
    response_model=GenerateDocumentsResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate tailored application materials",
)
async def generate_documents(
    body: GenerateDocumentsRequest,
    service: DocumentsService = Depends(get_documents_service),
) -> GenerateDocumentsResponse:
    result = await service.generate_all(
        resume_path=body.resume_path,
        job_description=body.job_description,
        job_title=body.job_title or "Target Role",
        company=body.company or "Target Company",
    )
    return GenerateDocumentsResponse(
        success=True,
        tailored_resume=result["tailored_resume"],
        cover_letter=result["cover_letter"],
        interview_prep=result["interview_prep"],
    )
