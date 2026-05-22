"""
agents/job_search.py — AGENT 2: Search job postings via Serper (with demo fallback).
"""

import json
import logging
import hashlib
from typing import Dict, List

import requests

logger = logging.getLogger("job_agent.job_search")


def _demo_jobs(job_titles: List[str], locations: List[str], skills: List[str], max_jobs: int) -> List[Dict]:
    """Synthetic jobs when no search API is configured."""
    title = job_titles[0] if job_titles else "Software Engineer"
    location = locations[0] if locations else "Remote"
    skill_str = ", ".join(skills[:3]) if skills else "Python, ML"
    companies = ["TechNova AI", "DataForge Labs", "CloudMind Systems", "NeuralPath Inc", "QuantumSoft"]
    jobs = []
    for i, company in enumerate(companies[:max_jobs]):
        jobs.append({
            "title": title,
            "company": company,
            "location": location,
            "url": f"https://example.com/jobs/{hashlib.md5(f'{company}{title}'.encode()).hexdigest()[:8]}",
            "description": (
                f"We are hiring a {title} at {company}. Location: {location}. "
                f"Required skills: {skill_str}. You will build ML pipelines, APIs, and "
                f"collaborate with cross-functional teams. Experience with Python and cloud is a plus."
            ),
            "salary": "Competitive",
            "source": "demo",
        })
    return jobs


def search_jobs_serper(job_titles: List[str], locations: List[str], max_jobs: int) -> List[Dict]:
    from core.config import SERPER_API_KEY

    if not SERPER_API_KEY:
        return []

    title = job_titles[0] if job_titles else "engineer"
    location = locations[0] if locations else "remote"
    query = f"{title} jobs {location} hiring"

    resp = requests.post(
        "https://google.serper.dev/search",
        headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
        json={"q": query, "num": min(max_jobs, 10)},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    jobs = []
    for item in data.get("organic", [])[:max_jobs]:
        jobs.append({
            "title": title,
            "company": item.get("title", "Unknown").split(" - ")[0][:80],
            "location": location,
            "url": item.get("link", ""),
            "description": item.get("snippet", "") + " " + item.get("title", ""),
            "salary": "",
            "source": "serper",
        })
    return jobs


def save_jobs_to_db(jobs: List[Dict]) -> List[Dict]:
    from core.config import get_db

    conn = get_db()
    saved = []
    for job in jobs:
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT OR IGNORE INTO jobs (title, company, location, url, description, salary, source)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.get("title", ""),
                    job.get("company", ""),
                    job.get("location", ""),
                    job.get("url", ""),
                    job.get("description", ""),
                    job.get("salary", ""),
                    job.get("source", ""),
                ),
            )
            if cur.rowcount:
                job["job_id"] = cur.lastrowid
            else:
                cur.execute("SELECT id FROM jobs WHERE url = ?", (job.get("url", ""),))
                row = cur.fetchone()
                if row:
                    job["job_id"] = row["id"]
        except Exception as e:
            logger.warning("Job DB insert failed: %s", e)
        saved.append(job)
    conn.commit()
    conn.close()
    return saved


def run_job_search(
    job_titles: List[str],
    locations: List[str],
    skills: List[str],
    max_jobs: int = 20,
) -> List[Dict]:
    logger.info("=== Job Search Agent START ===")
    jobs = search_jobs_serper(job_titles, locations, max_jobs)
    if not jobs:
        logger.warning("Serper returned no jobs — using demo dataset.")
        jobs = _demo_jobs(job_titles, locations, skills, max_jobs)
    jobs = save_jobs_to_db(jobs)
    try:
        from Agents.analytics import record_search_run
        record_search_run(job_titles, locations, len(jobs))
    except Exception as e:
        logger.warning("Could not record search run: %s", e)
    logger.info("=== Job Search Agent DONE — %d jobs ===", len(jobs))
    return jobs
