"""
agents/analytics.py — AGENT 8: Dashboard metrics from SQLite.
"""

import json
import logging
from typing import Dict, Optional

logger = logging.getLogger("job_agent.analytics")


def compute_dashboard_metrics(profile_id: Optional[int] = None) -> Dict:
    from core.config import get_db

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) AS c FROM jobs")
    total_jobs = cur.fetchone()["c"]

    cur.execute("SELECT AVG(match_score) AS avg FROM jobs WHERE match_score > 0")
    row = cur.fetchone()
    avg_match = round(row["avg"] or 0, 1)

    cur.execute(
        "SELECT COUNT(*) AS c FROM applications WHERE status = 'applied'"
    )
    applied = cur.fetchone()["c"]

    top_skills = []
    if profile_id:
        cur.execute("SELECT skills FROM profiles WHERE id = ?", (profile_id,))
        prow = cur.fetchone()
        if prow and prow["skills"]:
            try:
                top_skills = json.loads(prow["skills"])[:8]
            except json.JSONDecodeError:
                pass

    conn.close()
    return {
        "total_jobs_found": total_jobs,
        "avg_match_score": avg_match,
        "applications_submitted": applied,
        "top_skills": top_skills,
    }
