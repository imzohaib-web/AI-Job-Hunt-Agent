"""
orchestrator.py
===============
LangGraph Multi-Agent Orchestrator
====================================
Connects all 8 agents into a single state machine using LangGraph.
Each node is one agent. Edges define the flow.

Flow:
  parse_profile → search_jobs → embed_rank → company_research
       → tailor_resume → cover_letter → interview_prep → done

Conditional edges skip agents if data is missing or score is too low.

Usage:
  from orchestrator import run_full_pipeline
  result = run_full_pipeline(resume_path, preferences)
"""

import json
import logging
from pathlib import Path
from typing import TypedDict, List, Optional, Dict, Any

logger = logging.getLogger("job_agent.orchestrator")


# ── State Definition ──────────────────────────────────────────────────────────

class AgentState(TypedDict):
    """Shared state passed between all agents in the graph."""

    # Inputs
    resume_path:  str
    job_titles:   List[str]
    locations:    List[str]
    skills:       List[str]
    max_jobs:     int
    min_score:    float

    # Agent outputs (accumulated as pipeline runs)
    profile:        Optional[Dict]       # from profile_parser
    raw_jobs:       Optional[List[Dict]] # from job_search
    ranked_jobs:    Optional[List[Dict]] # from ranking_agent
    selected_job:   Optional[Dict]       # job chosen for tailoring
    company_info:   Optional[Dict]       # from company_research
    tailored_cv:    Optional[Dict]       # from resume_tailor
    cover_letter:   Optional[Dict]       # from cover_letter
    interview_prep: Optional[Dict]       # from interview_prep
    analytics:      Optional[Dict]       # from analytics

    # Control
    error:          Optional[str]
    status_log:     List[str]            # human-readable log of steps


# ── Agent Nodes ───────────────────────────────────────────────────────────────

def node_parse_profile(state: AgentState) -> AgentState:
    """Node 1: Parse resume and extract structured profile."""
    from Agents.profile_parser import run_profile_parser

    logger.info("[Node] parse_profile")
    state["status_log"].append("📄 Parsing resume...")

    try:
        profile = run_profile_parser(state["resume_path"])
        state["profile"] = profile

        # Merge user-provided skills with parsed skills
        user_skills = state.get("skills", [])
        parsed_skills = profile.get("skills", [])
        combined = list({s.lower(): s for s in (parsed_skills + user_skills)}.values())
        state["profile"]["skills"] = combined

        state["status_log"].append(
            f"✅ Profile parsed: {profile.get('name')} | "
            f"{len(profile.get('skills',[]))} skills | "
            f"{len(profile.get('experience',[]))} jobs"
        )
    except Exception as e:
        from core.llm_client import LLMConfigurationError, _unwrap_retry_error, _friendly_error

        inner = _unwrap_retry_error(e)
        if isinstance(inner, LLMConfigurationError) or isinstance(e, ValueError):
            msg = str(inner if isinstance(inner, LLMConfigurationError) else e)
        elif "RetryError" in type(e).__name__ or "Authentication" in type(inner).__name__:
            msg = _friendly_error(inner)
        else:
            msg = str(inner)
        state["error"] = f"Profile parsing failed: {msg}"
        state["status_log"].append(f"❌ Profile parsing error: {msg}")
        logger.error("parse_profile node error: %s", e)

    return state


def node_search_jobs(state: AgentState) -> AgentState:
    """Node 2: Search for relevant job postings."""
    from Agents.job_search import run_job_search
    from core.config import MAX_JOBS

    logger.info("[Node] search_jobs")
    state["status_log"].append("🔍 Searching for jobs...")

    if state.get("error"):
        return state

    try:
        profile = state.get("profile", {})
        skills  = profile.get("skills", state.get("skills", []))

        jobs = run_job_search(
            job_titles = state["job_titles"],
            locations  = state["locations"],
            skills     = skills[:5],
            max_jobs   = state.get("max_jobs", MAX_JOBS),
        )
        state["raw_jobs"] = jobs
        state["status_log"].append(f"✅ Found {len(jobs)} job postings")
    except Exception as e:
        state["error"] = f"Job search failed: {e}"
        state["status_log"].append(f"❌ Job search error: {e}")

    return state


def node_rank_jobs(state: AgentState) -> AgentState:
    """Node 3: Embed jobs and rank by semantic similarity."""
    from Agents.ranking_agent import run_ranking_agent

    logger.info("[Node] rank_jobs")
    state["status_log"].append("🎯 Ranking jobs by match score...")

    if state.get("error") or not state.get("raw_jobs"):
        state["status_log"].append("⚠️ Skipping ranking — no jobs to rank")
        return state

    try:
        ranked = run_ranking_agent(
            profile   = state["profile"],
            jobs      = state["raw_jobs"],
            min_score = state.get("min_score", 55.0),
            top_k     = 10,
        )
        state["ranked_jobs"] = ranked

        if ranked:
            top = ranked[0]
            state["selected_job"] = top  # default: best match
            state["status_log"].append(
                f"✅ Ranked {len(ranked)} jobs. "
                f"Top match: {top.get('title')} @ {top.get('company')} "
                f"({top.get('match_score')}%)"
            )
        else:
            state["status_log"].append("⚠️ No jobs above minimum score threshold")
    except Exception as e:
        state["error"] = f"Ranking failed: {e}"
        state["status_log"].append(f"❌ Ranking error: {e}")

    return state


def node_company_research(state: AgentState) -> AgentState:
    """Node 4: Research the top company."""
    from Agents.comapany_research import research_company

    logger.info("[Node] company_research")

    job = state.get("selected_job")
    if not job or not job.get("company"):
        state["status_log"].append("⚠️ Skipping company research — no company name")
        return state

    state["status_log"].append(f"🏢 Researching {job['company']}...")

    try:
        info = research_company(job["company"], job.get("title", ""))
        state["company_info"] = info
        state["status_log"].append(
            f"✅ Company research complete: {info.get('industry','')} | "
            f"Tech: {', '.join(info.get('tech_stack',[])[:4])}"
        )
    except Exception as e:
        # Non-fatal — company research is nice-to-have
        state["company_info"] = {}
        state["status_log"].append(f"⚠️ Company research limited: {e}")

    return state


def node_tailor_resume(state: AgentState) -> AgentState:
    """Node 5: Tailor resume for the selected job."""
    from Agents.resume_tailor import run_resume_tailor

    logger.info("[Node] tailor_resume")

    if not state.get("selected_job"):
        state["status_log"].append("⚠️ Skipping resume tailoring — no job selected")
        return state

    state["status_log"].append("📝 Tailoring resume...")

    try:
        tailored = run_resume_tailor(
            profile = state["profile"],
            job     = state["selected_job"],
        )
        state["tailored_cv"] = tailored
        state["status_log"].append(
            f"✅ Resume tailored: {Path(tailored.get('resume_path','')).name}"
        )
    except Exception as e:
        state["error"] = f"Resume tailoring failed: {e}"
        state["status_log"].append(f"❌ Resume tailor error: {e}")

    return state


def node_cover_letter(state: AgentState) -> AgentState:
    """Node 6: Generate cover letter."""
    from Agents.cover_letter import run_cover_letter_agent

    logger.info("[Node] cover_letter")

    if not state.get("selected_job"):
        state["status_log"].append("⚠️ Skipping cover letter — no job selected")
        return state

    state["status_log"].append("✉️ Writing cover letter...")

    try:
        result = run_cover_letter_agent(
            profile      = state["profile"],
            job          = state["selected_job"],
            company_info = state.get("company_info"),
        )
        state["cover_letter"] = result
        state["status_log"].append(
            f"✅ Cover letter written ({len(result.get('content','').split())} words)"
        )
    except Exception as e:
        state["status_log"].append(f"⚠️ Cover letter error: {e}")
        state["cover_letter"] = {}

    return state


def node_interview_prep(state: AgentState) -> AgentState:
    """Node 7: Generate interview preparation materials."""
    from Agents.interview_prep import run_interview_prep_agent

    logger.info("[Node] interview_prep")

    if not state.get("selected_job"):
        state["status_log"].append("⚠️ Skipping interview prep — no job selected")
        return state

    state["status_log"].append("🎤 Preparing interview questions...")

    try:
        result = run_interview_prep_agent(
            profile      = state["profile"],
            job          = state["selected_job"],
            company_info = state.get("company_info"),
        )
        state["interview_prep"] = result
        prep = result.get("prep", {})
        n_q = (len(prep.get("behavioral_questions", [])) +
               len(prep.get("technical_questions", [])))
        state["status_log"].append(f"✅ Generated {n_q} interview questions")
    except Exception as e:
        state["status_log"].append(f"⚠️ Interview prep error: {e}")
        state["interview_prep"] = {}

    return state


def node_analytics(state: AgentState) -> AgentState:
    """Node 8: Compute analytics dashboard."""
    from Agents.analytics import compute_dashboard_metrics

    logger.info("[Node] analytics")
    state["status_log"].append("📊 Computing analytics...")

    try:
        profile_id = state.get("profile", {}).get("profile_id")
        metrics = compute_dashboard_metrics(profile_id)
        state["analytics"] = metrics
        state["status_log"].append(
            f"✅ Analytics ready: {metrics.get('total_jobs_found',0)} jobs | "
            f"avg match {metrics.get('avg_match_score',0)}%"
        )
    except Exception as e:
        state["status_log"].append(f"⚠️ Analytics error: {e}")
        state["analytics"] = {}

    return state


# ── Conditional Edges ─────────────────────────────────────────────────────────

def should_continue_after_search(state: AgentState) -> str:
    """After search: continue to ranking only if we have jobs."""
    if state.get("error"):
        return "analytics"  # Skip to analytics to show what went wrong
    if not state.get("raw_jobs"):
        return "analytics"
    return "rank_jobs"


def should_continue_after_ranking(state: AgentState) -> str:
    """After ranking: skip tailoring if no good matches."""
    if state.get("error"):
        return "analytics"
    if not state.get("ranked_jobs"):
        return "analytics"
    return "company_research"


# ── Graph Builder ─────────────────────────────────────────────────────────────

def build_graph():
    """Build and compile the LangGraph state machine."""
    from langgraph.graph import StateGraph, END

    graph = StateGraph(AgentState)

    # Add all agent nodes
    graph.add_node("parse_profile",    node_parse_profile)
    graph.add_node("search_jobs",      node_search_jobs)
    graph.add_node("rank_jobs",        node_rank_jobs)
    graph.add_node("company_research", node_company_research)
    graph.add_node("tailor_resume",    node_tailor_resume)
    graph.add_node("cover_letter",     node_cover_letter)
    graph.add_node("interview_prep",   node_interview_prep)
    graph.add_node("analytics",        node_analytics)

    # Set entry point
    graph.set_entry_point("parse_profile")

    # Fixed edges
    graph.add_edge("parse_profile", "search_jobs")

    # Conditional edges
    graph.add_conditional_edges(
        "search_jobs",
        should_continue_after_search,
        {"rank_jobs": "rank_jobs", "analytics": "analytics"},
    )
    graph.add_conditional_edges(
        "rank_jobs",
        should_continue_after_ranking,
        {"company_research": "company_research", "analytics": "analytics"},
    )

    # Linear tail
    graph.add_edge("company_research", "tailor_resume")
    graph.add_edge("tailor_resume",    "cover_letter")
    graph.add_edge("cover_letter",     "interview_prep")
    graph.add_edge("interview_prep",   "analytics")
    graph.add_edge("analytics",        END)

    return graph.compile()


# ── Public API ────────────────────────────────────────────────────────────────

def run_full_pipeline(
    resume_path: str,
    job_titles:  List[str],
    locations:   List[str],
    skills:      Optional[List[str]] = None,
    max_jobs:    int = 20,
    min_score:   float = 55.0,
) -> AgentState:
    """
    Run the complete multi-agent pipeline.

    Args:
        resume_path: Path to resume PDF/DOCX
        job_titles:  e.g. ["AI Engineer", "ML Engineer"]
        locations:   e.g. ["Remote", "Germany"]
        skills:      Optional extra skills to inject
        max_jobs:    Max jobs to search for
        min_score:   Minimum match % to include

    Returns:
        Final AgentState with all outputs populated
    """
    logger.info("=" * 60)
    logger.info("MULTI-AGENT PIPELINE START")
    logger.info("Resume: %s | Titles: %s | Locations: %s",
                resume_path, job_titles, locations)
    logger.info("=" * 60)

    # Build graph
    app = build_graph()

    # Initial state
    initial_state: AgentState = {
        "resume_path":  resume_path,
        "job_titles":   job_titles,
        "locations":    locations,
        "skills":       skills or [],
        "max_jobs":     max_jobs,
        "min_score":    min_score,
        "profile":      None,
        "raw_jobs":     None,
        "ranked_jobs":  None,
        "selected_job": None,
        "company_info": None,
        "tailored_cv":  None,
        "cover_letter": None,
        "interview_prep": None,
        "analytics":    None,
        "error":        None,
        "status_log":   ["🚀 Pipeline started"],
    }

    # Run pipeline
    final_state = app.invoke(initial_state)

    # Persist application for analytics dashboard
    try:
        from Agents.analytics import record_application_from_pipeline
        record_application_from_pipeline(final_state)
    except Exception as e:
        logger.warning("Could not save application for analytics: %s", e)

    logger.info("=" * 60)
    logger.info("PIPELINE COMPLETE")
    for log_line in final_state.get("status_log", []):
        logger.info("  %s", log_line)
    logger.info("=" * 60)

    return final_state


def run_single_job_pipeline(
    resume_path: str,
    job: Dict,
) -> Dict:
    """
    Shortcut: run only tailoring + cover letter + interview prep
    for a single job (skips search/ranking).
    Useful when user manually selects a job.
    """
    from Agents.profile_parser import run_profile_parser
    from Agents.comapany_research import research_company
    from Agents.resume_tailor import run_resume_tailor
    from Agents.cover_letter import run_cover_letter_agent
    from Agents.interview_prep import run_interview_prep_agent

    profile  = run_profile_parser(resume_path)
    company_info = research_company(job.get("company",""), job.get("title",""))
    tailored = run_resume_tailor(profile, job)
    cl       = run_cover_letter_agent(profile, job, company_info)
    prep     = run_interview_prep_agent(profile, job, company_info)

    return {
        "profile":        profile,
        "company_info":   company_info,
        "tailored_cv":    tailored,
        "cover_letter":   cl,
        "interview_prep": prep,
    }


# ── CLI Entry ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 4:
        print("Usage: python orchestrator.py <resume.pdf> <job_title1,title2> <location1,location2>")
        print("Example: python orchestrator.py resume.pdf 'AI Engineer,ML Engineer' 'Remote,Germany'")
        sys.exit(1)

    resume  = sys.argv[1]
    titles  = [t.strip() for t in sys.argv[2].split(",")]
    locs    = [l.strip() for l in sys.argv[3].split(",")]

    result  = run_full_pipeline(resume, titles, locs)

    print("\n=== PIPELINE RESULTS ===")
    for log in result.get("status_log", []):
        print(log)

    if result.get("ranked_jobs"):
        print(f"\nTop {len(result['ranked_jobs'])} matched jobs:")
        for job in result["ranked_jobs"][:5]:
            print(f"  {job['match_score']}% — {job['title']} @ {job['company']}")

    if result.get("tailored_cv"):
        print(f"\nTailored resume: {result['tailored_cv'].get('resume_path')}")
    if result.get("cover_letter"):
        print(f"Cover letter: {result['cover_letter'].get('docx_path')}")
    if result.get("interview_prep"):
        print(f"Interview prep: {result['interview_prep'].get('file_path')}")