"""
backend/main.py
===============
Production FastAPI entry point for the AI Job Hunting Agent.

Architecture
------------
- **Routers** (`backend/routers/`) — HTTP routes only; no business logic.
- **Services** (`backend/services/`) — wrap Agents/* and core/*; run sync code via asyncio.to_thread.
- **Schemas** (`backend/schemas/`) — Pydantic request/response validation.
- **Exceptions** (`backend/exceptions.py`) — domain errors → HTTP status codes.

Run from project root (with venv activated):

    uvicorn backend.main:app --reload

Interactive docs:
    http://127.0.0.1:8000/docs

Environment:
    Copy `.env` to project root with GROQ_API_KEY or GOOGLE_API_KEY for LLM agents.
"""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Ensure project root is on sys.path so `Agents`, `core`, `orchestrator` import correctly
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.config import API_TITLE, API_VERSION, CORS_ORIGINS
from backend.exceptions import APIError
from backend.routers import (
    analytics_router,
    documents_router,
    health_router,
    jobs_router,
    resume_router,
)

# Dedicated API logger (core/config.py already configures root logging)
logger = logging.getLogger("job_agent.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup: ensure upload dirs exist and DB is initialized (via core.config import).
    Shutdown: optional cleanup hook.
    """
    from backend.config import UPLOAD_DIR
    from core.config import init_db  # noqa: F401 — triggers DB init on import

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    init_db()
    logger.info("API started — %s v%s", API_TITLE, API_VERSION)
    yield
    logger.info("API shutdown")


def create_app() -> FastAPI:
    """Application factory — used by uvicorn and tests."""
    app = FastAPI(
        title=API_TITLE,
        version=API_VERSION,
        description=(
            "REST API for the AI Job Hunting multi-agent system. "
            "Upload resumes, search jobs, generate tailored documents, and view analytics."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ── CORS ───────────────────────────────────────────────────────────────────
    # Allows Streamlit (8501) and other frontends to call the API from the browser.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS if CORS_ORIGINS != ["*"] else ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ──────────────────────────────────────────────────────────────
    app.include_router(health_router)
    app.include_router(resume_router)
    app.include_router(jobs_router)
    app.include_router(documents_router)
    app.include_router(analytics_router)

    # ── Exception handlers ─────────────────────────────────────────────────────
    @app.exception_handler(APIError)
    async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
        logger.warning("APIError %s %s: %s", request.method, request.url.path, exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content={"success": False, "detail": exc.message},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        logger.warning("Validation error on %s: %s", request.url.path, exc.errors())
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"success": False, "detail": exc.errors()},
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "detail": "Internal server error"},
        )

    return app


# Uvicorn loads this object: `uvicorn backend.main:app`
app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
