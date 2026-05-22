"""
agents/ranking_agent.py — AGENT 3: Embed jobs and rank by profile similarity.
"""

import json
import logging
from typing import Dict, List

logger = logging.getLogger("job_agent.ranking")


def build_job_text(job: Dict) -> str:
    parts = []
    if job.get("title"):
        parts.append(f"Job Title: {job['title']}")
    if job.get("company"):
        parts.append(f"Company: {job['company']}")
    if job.get("location"):
        parts.append(f"Location: {job['location']}")
    if job.get("description"):
        parts.append(f"Description: {job['description'][:1500]}")
    if job.get("salary"):
        parts.append(f"Salary: {job['salary']}")
    return "\n".join(parts)


def build_profile_text(profile: Dict) -> str:
    parts = [
        f"Name: {profile.get('name', '')}",
        f"Summary: {profile.get('summary', '')}",
        f"Skills: {', '.join(profile.get('skills', []))}",
    ]
    for exp in profile.get("experience", [])[:4]:
        parts.append(
            f"{exp.get('title', '')} at {exp.get('company', '')}: "
            + " ".join((exp.get("achievements") or exp.get("bullets") or [])[:2])
        )
    return "\n".join(parts)


def embed_and_store_jobs(jobs: List[Dict]) -> List[Dict]:
    from core.embeddings import embed_texts
    from core.vector_store import get_vector_store

    if not jobs:
        return []

    texts = [build_job_text(job) for job in jobs]
    vectors = embed_texts(texts, show_progress=False)
    store = get_vector_store()

    pinecone_vectors = []
    for i, (job, vec) in enumerate(zip(jobs, vectors)):
        job_id = str(job.get("job_id") or job.get("url", f"job_{i}"))
        job["job_text"] = texts[i]
        job["embedding"] = vec
        pinecone_vectors.append({
            "id": job_id,
            "values": vec,
            "metadata": {
                "title": job.get("title", ""),
                "company": job.get("company", ""),
                "url": job.get("url", ""),
            },
        })

    store.upsert(pinecone_vectors)
    return jobs


def rank_jobs_for_profile(profile: Dict, jobs: List[Dict], top_k: int = 10) -> List[Dict]:
    from core.embeddings import embed_text, rank_by_similarity

    profile_vec = embed_text(build_profile_text(profile))
    jobs_with_emb = embed_and_store_jobs(jobs)
    ranked = rank_by_similarity(profile_vec, jobs_with_emb, top_k=top_k)
    return ranked


def update_match_scores_in_db(ranked_jobs: List[Dict]) -> None:
    from core.config import get_db

    conn = get_db()
    for job in ranked_jobs:
        if job.get("job_id") and job.get("match_score") is not None:
            conn.execute(
                "UPDATE jobs SET match_score = ? WHERE id = ?",
                (job["match_score"], job["job_id"]),
            )
    conn.commit()
    conn.close()


def run_ranking_agent(
    profile: Dict,
    jobs: List[Dict],
    min_score: float = 55.0,
    top_k: int = 10,
) -> List[Dict]:
    logger.info("=== Ranking Agent START — %d jobs ===", len(jobs))
    ranked = rank_jobs_for_profile(profile, jobs, top_k=len(jobs))
    filtered = [j for j in ranked if j.get("match_score", 0) >= min_score][:top_k]
    update_match_scores_in_db(filtered)
    logger.info(
        "=== Ranking Agent DONE — %d above %.1f%% ===",
        len(filtered),
        min_score,
    )
    return filtered
