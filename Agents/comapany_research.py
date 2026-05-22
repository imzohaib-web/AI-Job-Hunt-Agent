"""
agents/company_research.py
==========================
AGENT 4 — Company Research Agent
===================================
Researches company background, culture, and tech stack.
Combines web scraping (free) + LLM summarization (Groq free).

Input:  Company name + optional website URL
Output: Structured company summary dict
"""

import logging
import time
from typing import Dict, Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("job_agent.company_research")

RESEARCH_SYSTEM = """You are a company research analyst.
Summarize company information concisely for job applicants.
Focus on: what they build, tech stack, culture, size, funding stage.
Return ONLY valid JSON."""

RESEARCH_PROMPT = """
Based on this company information, extract a structured summary:

{{
  "name": "Company name",
  "industry": "Industry/sector",
  "size": "startup/mid-size/enterprise or headcount if known",
  "founded": "year or null",
  "headquarters": "city, country",
  "mission": "one sentence mission/what they do",
  "products": ["product/service 1", "product/service 2"],
  "tech_stack": ["technology 1", "technology 2"],
  "culture_keywords": ["keyword1", "keyword2"],
  "funding_stage": "Series A / public / bootstrapped / unknown",
  "why_apply": "2-3 reasons a candidate might want to work here",
  "interview_tips": ["tip 1", "tip 2"]
}}

Company information to analyze:
{raw_info}
"""


def search_company_info(company_name: str) -> str:
    """
    Gather raw company information from web search.
    Uses Serper API if available, falls back to direct scraping.
    """
    from core.config import SERPER_API_KEY

    raw_parts = []

    # Try Serper search first
    if SERPER_API_KEY:
        try:
            resp = requests.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
                json={"q": f"{company_name} company tech stack culture careers", "num": 5},
                timeout=10,
            )
            data = resp.json()

            # Extract knowledge graph if available
            if kg := data.get("knowledgeGraph"):
                raw_parts.append(f"Company: {kg.get('title', '')}")
                raw_parts.append(f"Type: {kg.get('type', '')}")
                raw_parts.append(f"Description: {kg.get('description', '')}")
                for attr, val in (kg.get("attributes") or {}).items():
                    raw_parts.append(f"{attr}: {val}")

            # Collect organic snippets
            for result in data.get("organic", [])[:3]:
                raw_parts.append(result.get("snippet", ""))

        except Exception as e:
            logger.warning("Serper company search failed: %s", e)

    # Try scraping company homepage / Glassdoor / LinkedIn
    search_urls = [
        f"https://www.glassdoor.com/Overview/{company_name.replace(' ', '-')}-overview.htm",
    ]

    for url in search_urls:
        try:
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "nav", "header", "footer"]):
                tag.decompose()
            text = soup.get_text(separator=" ", strip=True)
            raw_parts.append(text[:2000])
            break
        except Exception:
            continue

    if not raw_parts:
        # Last resort: minimal info
        raw_parts.append(f"Company name: {company_name}")
        raw_parts.append("No additional information found. Provide generic summary.")

    return "\n".join(raw_parts)[:4000]


def research_company(company_name: str, job_title: str = "") -> Dict:
    """
    Research a company and return structured summary.

    Args:
        company_name: Name of the company
        job_title:    Job title being applied for (for context)

    Returns:
        Structured company info dict
    """
    if not company_name or company_name.strip() == "":
        return {"name": "Unknown", "industry": "", "mission": "", "tech_stack": []}

    logger.info("Researching company: %s", company_name)

    # Gather raw info
    raw_info = search_company_info(company_name)
    if job_title:
        raw_info += f"\n\nJob being applied for: {job_title}"

    # Summarize with LLM
    from core.llm_client import call_llm_json

    prompt = RESEARCH_PROMPT.format(raw_info=raw_info)
    summary = call_llm_json(prompt, system=RESEARCH_SYSTEM)

    if "error" in summary:
        logger.warning("Company research LLM failed, returning minimal info.")
        return {
            "name":         company_name,
            "industry":     "",
            "mission":      "",
            "tech_stack":   [],
            "why_apply":    "",
            "interview_tips": [],
        }

    logger.info("Company research complete: %s (%s)", company_name, summary.get("industry", ""))
    return summary


def run_company_research_agent(jobs: list) -> list:
    """
    Research all unique companies in the job list.

    Args:
        jobs: List of job dicts with "company" field

    Returns:
        Jobs with added "company_info" field
    """
    logger.info("=== Company Research Agent START — %d jobs ===", len(jobs))

    # Deduplicate companies to avoid redundant API calls
    company_cache: Dict[str, Dict] = {}

    for job in jobs:
        company = job.get("company", "")
        if not company:
            continue

        if company not in company_cache:
            company_cache[company] = research_company(company, job.get("title", ""))
            time.sleep(1)  # Rate limit protection

        job["company_info"] = company_cache[company]

    logger.info("=== Company Research Agent DONE ===")
    return jobs