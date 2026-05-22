"""
agents/analytics.py
===================
Application tracking, search history, and dashboard statistics.

SQLite tables used:
  - jobs, profiles, applications (core/config.py)
  - search_runs (logged job searches)

Public API:
  - save_application()
  - get_all_applications()
  - calculate_statistics()
  - record_search_run()
  - record_application_from_pipeline()
  - compute_dashboard_metrics()  # backward compatible with API/orchestrator
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger("job_agent.analytics")

# Valid application lifecycle statuses
APPLICATION_STATUSES = (
    "pending",
    "applied",
    "interview",
    "rejected",
    "offer",
)


def ensure_analytics_schema() -> None:
    """Create analytics-specific tables (safe to call repeatedly)."""
    from core.config import get_db

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS search_runs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            job_titles  TEXT,
            locations   TEXT,
            jobs_found  INTEGER DEFAULT 0,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Index for faster dashboard filters
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_applications_status
        ON applications(status)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_jobs_company
        ON jobs(company)
    """)
    conn.commit()
    conn.close()


# Run schema migration on import
ensure_analytics_schema()


def record_search_run(
    job_titles: List[str],
    locations: List[str],
    jobs_found: int,
) -> int:
    """Log one job-search execution for analytics (total jobs searched)."""
    from core.config import get_db

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO search_runs (job_titles, locations, jobs_found)
        VALUES (?, ?, ?)
        """,
        (json.dumps(job_titles), json.dumps(locations), jobs_found),
    )
    run_id = cur.lastrowid
    conn.commit()
    conn.close()
    logger.info("Recorded search run #%s (%d jobs)", run_id, jobs_found)
    return run_id


def save_application(
    job_id: int,
    profile_id: int,
    status: str = "pending",
    tailored_resume: Optional[str] = None,
    cover_letter: Optional[str] = None,
    interview_prep: Optional[Any] = None,
    notes: Optional[str] = None,
    applied_at: Optional[str] = None,
) -> int:
    """
    Create or update an application record.

    Args:
        job_id:          FK to jobs.id
        profile_id:      FK to profiles.id
        status:          pending | applied | interview | rejected | offer
        tailored_resume: Path to tailored resume file
        cover_letter:    Path to cover letter file
        interview_prep:  Dict or JSON string for interview prep
        notes:           Free-text notes
        applied_at:      ISO timestamp when applied (auto-set if status=applied)

    Returns:
        application id
    """
    from core.config import get_db

    if status not in APPLICATION_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Use one of {APPLICATION_STATUSES}")

    if interview_prep is not None and not isinstance(interview_prep, str):
        interview_prep = json.dumps(interview_prep)

    if status == "applied" and not applied_at:
        applied_at = datetime.utcnow().isoformat()

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM applications WHERE job_id = ? AND profile_id = ?",
        (job_id, profile_id),
    )
    row = cur.fetchone()

    if row:
        app_id = row["id"]
        cur.execute(
            """
            UPDATE applications
            SET status = ?, tailored_resume = COALESCE(?, tailored_resume),
                cover_letter = COALESCE(?, cover_letter),
                interview_prep = COALESCE(?, interview_prep),
                notes = COALESCE(?, notes),
                applied_at = COALESCE(?, applied_at)
            WHERE id = ?
            """,
            (
                status,
                tailored_resume,
                cover_letter,
                interview_prep,
                notes,
                applied_at,
                app_id,
            ),
        )
    else:
        cur.execute(
            """
            INSERT INTO applications (
                job_id, profile_id, status, tailored_resume,
                cover_letter, interview_prep, notes, applied_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                profile_id,
                status,
                tailored_resume,
                cover_letter,
                interview_prep,
                notes,
                applied_at,
            ),
        )
        app_id = cur.lastrowid

    conn.commit()
    conn.close()
    logger.info("Saved application #%s (job=%s, status=%s)", app_id, job_id, status)
    return app_id


def get_all_applications(
    company: Optional[str] = None,
    status: Optional[str] = None,
    min_score: Optional[float] = None,
    max_score: Optional[float] = None,
) -> pd.DataFrame:
    """
    Return applications joined with job and profile data as a pandas DataFrame.

    Filters:
        company:   case-insensitive substring match on jobs.company
        status:    exact application status
        min_score: minimum jobs.match_score (0–100)
        max_score: maximum jobs.match_score
    """
    from core.config import get_db

    sql = """
        SELECT
            a.id              AS application_id,
            a.status,
            a.applied_at,
            a.notes,
            a.tailored_resume,
            a.cover_letter,
            a.created_at      AS application_created_at,
            j.id              AS job_id,
            j.title           AS job_title,
            j.company,
            j.location,
            j.match_score,
            j.url             AS job_url,
            j.source,
            j.fetched_at,
            p.id              AS profile_id,
            p.name            AS candidate_name,
            p.email           AS candidate_email
        FROM applications a
        LEFT JOIN jobs j ON a.job_id = j.id
        LEFT JOIN profiles p ON a.profile_id = p.id
        WHERE 1=1
    """
    params: List[Any] = []

    if company:
        sql += " AND LOWER(j.company) LIKE LOWER(?)"
        params.append(f"%{company.strip()}%")
    if status and status != "all":
        sql += " AND a.status = ?"
        params.append(status)
    if min_score is not None:
        sql += " AND j.match_score >= ?"
        params.append(min_score)
    if max_score is not None:
        sql += " AND j.match_score <= ?"
        params.append(max_score)

    sql += " ORDER BY a.created_at DESC"

    conn = get_db()
    df = pd.read_sql_query(sql, conn, params=params)
    conn.close()

    if not df.empty:
        df["match_score"] = pd.to_numeric(df["match_score"], errors="coerce").fillna(0)
    return df


def calculate_statistics(
    company: Optional[str] = None,
    status: Optional[str] = None,
    min_score: Optional[float] = None,
    max_score: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Compute dashboard KPIs and chart-ready series.

    Returns dict with:
        total_jobs_searched, total_applications, average_match_score,
        top_companies, interview_rate, application_success_rate,
        status_breakdown, applications_over_time, match_score_distribution
    """
    from core.config import get_db

    conn = get_db()
    cur = conn.cursor()

    # Total jobs searched (sum of all search runs + jobs in DB as fallback)
    cur.execute("SELECT COALESCE(SUM(jobs_found), 0) AS t FROM search_runs")
    searched_from_runs = cur.fetchone()["t"]
    cur.execute("SELECT COUNT(*) AS c FROM jobs")
    total_jobs_in_db = cur.fetchone()["c"]
    total_jobs_searched = max(searched_from_runs, total_jobs_in_db)

    df = get_all_applications(
        company=company,
        status=status,
        min_score=min_score,
        max_score=max_score,
    )

    total_applications = len(df)
    avg_match = round(float(df["match_score"].mean()), 1) if total_applications else 0.0

    # Top companies by application count
    if total_applications and "company" in df.columns:
        top_companies = (
            df.groupby("company", dropna=False)
            .size()
            .reset_index(name="applications")
            .sort_values("applications", ascending=False)
            .head(10)
            .to_dict(orient="records")
        )
    else:
        top_companies = []

    # Rates (percentages 0–100)
    if total_applications:
        status_counts = df["status"].value_counts().to_dict()
        applied_plus = sum(
            status_counts.get(s, 0)
            for s in ("applied", "interview", "rejected", "offer")
        )
        interviews = status_counts.get("interview", 0)
        offers = status_counts.get("offer", 0)
        interview_rate = round(
            (interviews / applied_plus * 100) if applied_plus else 0, 1
        )
        application_success_rate = round(
            (offers / applied_plus * 100) if applied_plus else 0, 1
        )
        status_breakdown = [
            {"status": k, "count": int(v)} for k, v in status_counts.items()
        ]
    else:
        interview_rate = 0.0
        application_success_rate = 0.0
        status_breakdown = []

    # Applications over time (by created_at date)
    applications_over_time: List[Dict] = []
    if total_applications and "application_created_at" in df.columns:
        ts = pd.to_datetime(df["application_created_at"], errors="coerce")
        daily = (
            df.assign(date=ts.dt.date)
            .groupby("date", dropna=True)
            .size()
            .reset_index(name="count")
        )
        applications_over_time = [
            {"date": str(row["date"]), "count": int(row["count"])}
            for _, row in daily.iterrows()
        ]

    # Match score buckets for bar chart
    match_distribution: List[Dict] = []
    if total_applications:
        bins = [0, 50, 60, 70, 80, 90, 100]
        labels = ["0-49", "50-59", "60-69", "70-79", "80-89", "90-100"]
        cuts = pd.cut(
            df["match_score"],
            bins=bins,
            labels=labels,
            include_lowest=True,
        )
        dist = cuts.value_counts().sort_index()
        match_distribution = [
            {"bucket": str(idx), "count": int(cnt)} for idx, cnt in dist.items()
        ]

    conn.close()

    return {
        "total_jobs_searched": int(total_jobs_searched),
        "total_applications": total_applications,
        "average_match_score": avg_match,
        "top_companies": top_companies,
        "interview_rate": interview_rate,
        "application_success_rate": application_success_rate,
        "status_breakdown": status_breakdown,
        "applications_over_time": applications_over_time,
        "match_score_distribution": match_distribution,
    }


def record_application_from_pipeline(state: Dict[str, Any]) -> Optional[int]:
    """
    Persist application after a successful orchestrator run.
    Called with final AgentState dict.
    """
    profile = state.get("profile") or {}
    job = state.get("selected_job") or {}
    profile_id = profile.get("profile_id")
    job_id = job.get("job_id")

    if not profile_id or not job_id:
        logger.warning("Skipping application save — missing profile_id or job_id")
        return None

    tailored = state.get("tailored_cv") or {}
    cover = state.get("cover_letter") or {}
    prep = state.get("interview_prep") or {}

    return save_application(
        job_id=int(job_id),
        profile_id=int(profile_id),
        status="pending",
        tailored_resume=tailored.get("resume_path"),
        cover_letter=cover.get("docx_path") or cover.get("txt_path"),
        interview_prep=prep.get("prep"),
        notes="Auto-saved from pipeline run",
    )


def compute_dashboard_metrics(profile_id: Optional[int] = None) -> Dict:
    """Backward-compatible summary for FastAPI / orchestrator analytics node."""
    stats = calculate_statistics()
    result = {
        "total_jobs_found": stats["total_jobs_searched"],
        "total_jobs_searched": stats["total_jobs_searched"],
        "avg_match_score": stats["average_match_score"],
        "average_match_score": stats["average_match_score"],
        "applications_submitted": stats["total_applications"],
        "total_applications": stats["total_applications"],
        "interview_rate": stats["interview_rate"],
        "application_success_rate": stats["application_success_rate"],
        "top_companies": stats["top_companies"],
        "top_skills": [],
    }
    if profile_id:
        from core.config import get_db
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT skills FROM profiles WHERE id = ?", (profile_id,))
        row = cur.fetchone()
        conn.close()
        if row and row["skills"]:
            try:
                result["top_skills"] = json.loads(row["skills"])[:8]
            except json.JSONDecodeError:
                pass
    return result
