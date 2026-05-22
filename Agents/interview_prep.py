"""
agents/interview_prep.py — AGENT 7: Interview questions and model answers.
"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("job_agent.interview_prep")

INTERVIEW_SYSTEM = """You are a senior engineering interviewer. Return ONLY valid JSON."""

INTERVIEW_PROMPT = """
Generate interview preparation JSON for this candidate and role.

CANDIDATE: {name} | Skills: {skills} | Experience: {experience}
ROLE: {job_title} at {company}
{company_context}
Description: {job_description}

Return JSON with behavioral_questions (4), technical_questions (5),
role_specific_questions (3), questions_to_ask_interviewer, key_talking_points,
red_flags_to_avoid, preparation_checklist.
"""


def generate_interview_prep(
    profile: Dict, job: Dict, company_info: Optional[Dict] = None
) -> Dict:
    from core.llm_client import call_llm_json

    exp_summary = []
    for exp in profile.get("experience", [])[:3]:
        bullets = exp.get("achievements") or exp.get("bullets", [])
        exp_summary.append(f"{exp.get('title')} @ {exp.get('company')}: {bullets[0] if bullets else ''}")

    company_context = ""
    if company_info:
        company_context = f"Company mission: {company_info.get('mission', '')}"

    prompt = INTERVIEW_PROMPT.format(
        name=profile.get("name", ""),
        skills=", ".join(profile.get("skills", [])[:15]),
        experience="; ".join(exp_summary),
        job_title=job.get("title", ""),
        company=job.get("company", ""),
        company_context=company_context,
        job_description=(job.get("description") or "")[:2000],
    )
    prep = call_llm_json(prompt, system=INTERVIEW_SYSTEM)
    if "error" in prep:
        skills = profile.get("skills", [])
        prep = _fallback_prep(profile, skills)
    return prep


def _fallback_prep(profile: Dict, skills: List[str]) -> Dict:
    return {
        "behavioral_questions": [
            {
                "question": "Tell me about yourself.",
                "model_answer": f"I'm {profile.get('name', 'a developer')} skilled in {', '.join(skills[:3])}.",
                "tips": "Keep it under 2 minutes.",
            }
        ],
        "technical_questions": [
            {
                "question": f"Describe your experience with {skills[0] if skills else 'your stack'}.",
                "difficulty": "medium",
                "model_answer": "Use a specific project example.",
                "follow_ups": [],
            }
        ],
        "role_specific_questions": [],
        "questions_to_ask_interviewer": [
            "What does success look like in the first 90 days?",
        ],
        "key_talking_points": skills[:5],
        "red_flags_to_avoid": ["Speaking negatively about past employers"],
        "preparation_checklist": ["Research the company", "Prepare STAR stories"],
    }


def format_prep_as_markdown(prep: Dict, profile: Dict, job: Dict) -> str:
    lines = [
        f"# Interview Preparation",
        f"**Role:** {job.get('title', '')} at {job.get('company', '')}",
        f"**Candidate:** {profile.get('name', '')}",
        "",
    ]
    for i, q in enumerate(prep.get("behavioral_questions", []), 1):
        lines.append(f"## Behavioral Q{i}: {q.get('question', '')}")
        lines.append(q.get("model_answer", ""))
        lines.append("")
    for i, q in enumerate(prep.get("technical_questions", []), 1):
        lines.append(f"## Technical Q{i}: {q.get('question', '')}")
        lines.append(q.get("model_answer", ""))
        lines.append("")
    return "\n".join(lines)


def run_interview_prep_agent(
    profile: Dict,
    job: Dict,
    company_info: Optional[Dict] = None,
    output_dir: Optional[Path] = None,
) -> Dict:
    from core.config import OUTPUT_DIR

    if output_dir is None:
        output_dir = OUTPUT_DIR
    output_dir.mkdir(exist_ok=True)

    logger.info("=== Interview Prep Agent START ===")
    prep = generate_interview_prep(profile, job, company_info)
    markdown = format_prep_as_markdown(prep, profile, job)
    safe = re.sub(r"[^\w\s-]", "", job.get("company", "co")).replace(" ", "_")
    file_path = output_dir / f"InterviewPrep_{safe}.md"
    file_path.write_text(markdown, encoding="utf-8")
    logger.info("=== Interview Prep Agent DONE ===")
    return {"prep": prep, "file_path": str(file_path), "markdown": markdown}
