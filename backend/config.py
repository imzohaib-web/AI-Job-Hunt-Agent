"""
backend/config.py
-----------------
API-specific settings (separate from core/config.py project paths).
"""

import os
from pathlib import Path

# Project root (parent of backend/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Upload directory for temporary resume files served by the API
UPLOAD_DIR = PROJECT_ROOT / "data" / "api_uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Allowed resume MIME types and extensions
ALLOWED_RESUME_EXTENSIONS = {".pdf", ".docx"}
MAX_UPLOAD_BYTES = int(os.getenv("API_MAX_UPLOAD_MB", "10")) * 1024 * 1024

# CORS — comma-separated origins in .env, or "*" for dev
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:8501,http://127.0.0.1:8501").split(",")
    if o.strip()
]

API_TITLE = "AI Job Hunting Agent API"
API_VERSION = "1.0.0"
