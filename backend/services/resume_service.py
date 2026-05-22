"""
backend/services/resume_service.py
----------------------------------
Resume upload persistence and profile parsing via Agents.profile_parser.
"""

import logging
import uuid
from pathlib import Path

from backend.config import ALLOWED_RESUME_EXTENSIONS, MAX_UPLOAD_BYTES, UPLOAD_DIR
from backend.exceptions import NotFoundError, ValidationError, AgentProcessingError

logger = logging.getLogger("job_agent.api.resume")


class ResumeService:
    """Handles file validation, storage, and profile extraction."""

    @staticmethod
    def validate_extension(filename: str) -> str:
        suffix = Path(filename).suffix.lower()
        if suffix not in ALLOWED_RESUME_EXTENSIONS:
            raise ValidationError(
                f"Unsupported file type '{suffix}'. Allowed: {', '.join(ALLOWED_RESUME_EXTENSIONS)}"
            )
        return suffix

    async def save_upload(self, filename: str, content: bytes) -> Path:
        """Write uploaded bytes to a unique path under data/api_uploads/."""
        if len(content) > MAX_UPLOAD_BYTES:
            raise ValidationError(
                f"File exceeds maximum size of {MAX_UPLOAD_BYTES // (1024 * 1024)} MB"
            )
        if not content:
            raise ValidationError("Empty file uploaded")

        suffix = self.validate_extension(filename)
        safe_name = f"{uuid.uuid4().hex}{suffix}"
        dest = UPLOAD_DIR / safe_name
        dest.write_bytes(content)
        logger.info("Saved upload to %s (%d bytes)", dest, len(content))
        return dest

    @staticmethod
    def resolve_resume_path(resume_path: str) -> Path:
        """Resolve user-provided path (absolute or relative to project root)."""
        from backend.config import PROJECT_ROOT

        p = Path(resume_path)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        p = p.resolve()
        if not p.is_file():
            raise NotFoundError(f"Resume not found: {p}")
        if p.suffix.lower() not in ALLOWED_RESUME_EXTENSIONS:
            raise ValidationError(f"Resume must be PDF or DOCX, got: {p.suffix}")
        return p

    async def parse_resume(self, file_path: Path) -> dict:
        """
        Run profile parser in a thread pool (CPU + LLM I/O bound).
        Returns structured profile dict from Agents.profile_parser.
        """
        import asyncio
        from Agents.profile_parser import run_profile_parser

        logger.info("Parsing resume: %s", file_path)
        try:
            profile = await asyncio.to_thread(run_profile_parser, str(file_path))
            return profile
        except ValueError as e:
            raise ValidationError(str(e)) from e
        except Exception as e:
            logger.exception("Profile parsing failed")
            raise AgentProcessingError(f"Profile parsing failed: {e}") from e
