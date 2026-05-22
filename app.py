"""
AI Job Hunting Agent — Streamlit dashboard
Run: streamlit run app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from core.config import DATA_DIR, OUTPUT_DIR, MIN_MATCH_SCORE, MAX_JOBS
from orchestrator import run_full_pipeline, run_single_job_pipeline

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Job Hunting Agent",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom dark theme CSS ─────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    .main .block-container {
        padding-top: 1.5rem;
        max-width: 1200px;
    }

    .hero-title {
        font-size: 2rem;
        font-weight: 700;
        background: linear-gradient(135deg, #a5b4fc 0%, #6366f1 50%, #818cf8 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.25rem;
    }

    .hero-sub {
        color: #94a3b8;
        font-size: 0.95rem;
        margin-bottom: 1.5rem;
    }

    .job-card {
        background: linear-gradient(145deg, #151b2b 0%, #1a2236 100%);
        border: 1px solid #2d3748;
        border-radius: 12px;
        padding: 1rem 1.25rem;
        margin-bottom: 0.75rem;
    }

    .match-badge {
        display: inline-block;
        padding: 0.2rem 0.65rem;
        border-radius: 999px;
        font-weight: 600;
        font-size: 0.85rem;
    }

    .match-high { background: #064e3b; color: #6ee7b7; }
    .match-mid  { background: #422006; color: #fcd34d; }
    .match-low  { background: #450a0a; color: #fca5a5; }

    .pipeline-log {
        background: #0f1419;
        border-radius: 8px;
        padding: 0.75rem 1rem;
        font-size: 0.82rem;
        color: #cbd5e1;
        max-height: 220px;
        overflow-y: auto;
    }

    div[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0b0f19 0%, #111827 100%);
    }

    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #4f46e5, #6366f1);
        border: none;
        font-weight: 600;
        padding: 0.6rem 1.5rem;
        border-radius: 8px;
    }

    .stButton > button[kind="primary"]:hover {
        background: linear-gradient(135deg, #4338ca, #4f46e5);
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def _match_class(score: float) -> str:
    if score >= 80:
        return "match-high"
    if score >= 65:
        return "match-mid"
    return "match-low"


def _save_uploaded_resume(uploaded) -> str:
    upload_dir = DATA_DIR / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / uploaded.name
    path.write_bytes(uploaded.getbuffer())
    return str(path)


def _parse_list_field(text: str) -> list[str]:
    return [p.strip() for p in text.replace(";", ",").split(",") if p.strip()]


def _render_job_card(job: dict, rank: int) -> None:
    score = float(job.get("match_score", 0))
    badge_class = _match_class(score)
    company = job.get("company", "—")
    title = job.get("title", "—")
    location = job.get("location", "—")
    url = job.get("url", "")

    link_html = (
        f'<a href="{url}" target="_blank" style="color:#818cf8;">View posting</a>'
        if url
        else ""
    )
    st.markdown(
        f"""
        <div class="job-card">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;">
                <div>
                    <span style="color:#64748b;font-size:0.8rem;">#{rank}</span>
                    <div style="font-size:1.1rem;font-weight:600;color:#f1f5f9;">{title}</div>
                    <div style="color:#94a3b8;">{company} · {location}</div>
                </div>
                <span class="match-badge {badge_class}">{score:.1f}% match</span>
            </div>
            <div style="margin-top:0.5rem;font-size:0.85rem;color:#64748b;">
                {(job.get('description') or '')[:200]}…
            </div>
            <div style="margin-top:0.4rem;">{link_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_tailored_resume(tailored: dict) -> None:
    if not tailored:
        st.info("No tailored resume yet. Run the workflow first.")
        return

    st.markdown("#### Professional summary")
    st.write(tailored.get("tailored_summary", "—"))

    skills = tailored.get("skills_to_highlight", [])
    if skills:
        st.markdown("#### Skills to highlight")
        st.markdown(" ".join(f"`{s}`" for s in skills))

    st.markdown("#### Experience highlights")
    for exp in tailored.get("experience", []):
        with st.expander(f"{exp.get('title', '')} @ {exp.get('company', '')}", expanded=False):
            for bullet in exp.get("bullets") or exp.get("achievements") or []:
                st.markdown(f"- {bullet}")

    notes = tailored.get("tailoring_notes")
    if notes:
        st.caption(f"Notes: {notes}")

    path = tailored.get("resume_path")
    if path and Path(path).is_file():
        with open(path, "rb") as f:
            st.download_button(
                "Download tailored resume (.docx)",
                data=f.read(),
                file_name=Path(path).name,
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )


def _render_cover_letter(cl: dict) -> None:
    if not cl or not cl.get("content"):
        st.info("No cover letter generated yet.")
        return
    st.text_area("Cover letter", cl["content"], height=400)
    for key, label, mime in [
        ("docx_path", "Download .docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("txt_path", "Download .txt", "text/plain"),
    ]:
        p = cl.get(key)
        if p and Path(p).is_file():
            with open(p, "rb") as f:
                st.download_button(label, f.read(), file_name=Path(p).name, mime=mime, key=key)


def _render_interview_prep(ip: dict) -> None:
    if not ip:
        st.info("No interview prep yet.")
        return

    prep = ip.get("prep", {})
    if ip.get("markdown"):
        with st.expander("Full prep guide (markdown)", expanded=False):
            st.markdown(ip["markdown"])

    for label, key in [
        ("Behavioral questions", "behavioral_questions"),
        ("Technical questions", "technical_questions"),
        ("Role-specific questions", "role_specific_questions"),
    ]:
        items = prep.get(key, [])
        if not items:
            continue
        st.markdown(f"#### {label}")
        for i, q in enumerate(items, 1):
            with st.expander(f"Q{i}: {q.get('question', '')[:80]}", expanded=i == 1):
                if q.get("why_asked"):
                    st.caption(q["why_asked"])
                st.markdown("**Model answer**")
                st.write(q.get("model_answer", ""))
                if q.get("tips"):
                    st.info(q["tips"])
                if q.get("follow_ups"):
                    st.markdown("Follow-ups: " + " · ".join(q["follow_ups"]))

    if prep.get("questions_to_ask_interviewer"):
        st.markdown("#### Questions to ask the interviewer")
        for q in prep["questions_to_ask_interviewer"]:
            st.markdown(f"- {q}")


# ── Session state ─────────────────────────────────────────────────────────────
if "pipeline_result" not in st.session_state:
    st.session_state.pipeline_result = None
if "selected_job_idx" not in st.session_state:
    st.session_state.selected_job_idx = 0
if "resume_path" not in st.session_state:
    st.session_state.resume_path = None


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Settings")
    min_score = st.slider("Minimum match %", 40, 90, int(MIN_MATCH_SCORE * 100) if MIN_MATCH_SCORE <= 1 else int(MIN_MATCH_SCORE))
    max_jobs = st.number_input("Max jobs to fetch", 5, 30, MAX_JOBS)
    extra_skills = st.text_input("Extra skills (comma-separated)", placeholder="Python, LangChain, RAG")
    st.divider()
    st.markdown("**API keys** (`.env`)")
    st.caption("GROQ_API_KEY or GOOGLE_API_KEY required for LLM steps.")
    st.caption("SERPER_API_KEY optional for live job search.")

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown('<p class="hero-title">AI Job Hunting Agent</p>', unsafe_allow_html=True)
st.markdown(
    '<p class="hero-sub">Autonomous multi-agent workflow — search, rank, tailor, and prepare your application.</p>',
    unsafe_allow_html=True,
)

# ── Input row ─────────────────────────────────────────────────────────────────
col_left, col_right = st.columns([1, 1], gap="large")

with col_left:
    st.markdown("##### Resume")
    uploaded = st.file_uploader(
        "Upload PDF or DOCX",
        type=["pdf", "docx"],
        help="Your resume powers profile parsing and tailoring.",
    )

with col_right:
    st.markdown("##### Search preferences")
    job_title = st.text_input("Job title(s)", placeholder="AI Engineer, ML Engineer")
    location = st.text_input("Location(s)", placeholder="Remote, Germany, London")

run_clicked = st.button("🚀 Run full workflow", type="primary", use_container_width=True)

# ── Run pipeline ──────────────────────────────────────────────────────────────
if run_clicked:
    if not uploaded:
        st.error("Please upload a resume before running the workflow.")
    elif not job_title.strip():
        st.error("Please enter at least one job title.")
    elif not location.strip():
        st.error("Please enter at least one location.")
    else:
        resume_path = _save_uploaded_resume(uploaded)
        st.session_state.resume_path = resume_path
        titles = _parse_list_field(job_title)
        locations = _parse_list_field(location)
        skills = _parse_list_field(extra_skills)

        with st.status("Running multi-agent pipeline…", expanded=True) as status:
            try:
                result = run_full_pipeline(
                    resume_path=resume_path,
                    job_titles=titles,
                    locations=locations,
                    skills=skills,
                    max_jobs=int(max_jobs),
                    min_score=float(min_score),
                )
                st.session_state.pipeline_result = result
                st.session_state.selected_job_idx = 0
                if result.get("error"):
                    status.update(label="Pipeline finished with errors", state="error")
                else:
                    status.update(label="Pipeline complete", state="complete")
            except Exception as exc:
                st.session_state.pipeline_result = None
                status.update(label="Pipeline failed", state="error")
                st.exception(exc)

result = st.session_state.pipeline_result

if result:
    if result.get("error"):
        st.error(result["error"])

    # Profile snapshot
    profile = result.get("profile") or {}
    if profile.get("name"):
        st.success(
            f"Profile: **{profile.get('name')}** · "
            f"{len(profile.get('skills', []))} skills · "
            f"{len(profile.get('experience', []))} roles"
        )

    ranked = result.get("ranked_jobs") or []
    tailored = result.get("tailored_cv") or {}
    cover = result.get("cover_letter") or {}
    interview = result.get("interview_prep") or {}
    analytics = result.get("analytics") or {}

    # Metrics row
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Jobs ranked", len(ranked))
    m2.metric("Avg match", f"{analytics.get('avg_match_score', 0)}%")
    m3.metric("Top match", f"{ranked[0].get('match_score', 0)}%" if ranked else "—")
    m4.metric("Jobs in DB", analytics.get("total_jobs_found", 0))

    tab_jobs, tab_resume, tab_letter, tab_interview, tab_log = st.tabs(
        ["Ranked jobs", "Tailored resume", "Cover letter", "Interview prep", "Pipeline log"]
    )

    with tab_jobs:
        if not ranked:
            st.warning("No jobs met your minimum match threshold. Try lowering the match % slider.")
        else:
            job_labels = [
                f"{j.get('match_score', 0)}% — {j.get('title', '')} @ {j.get('company', '')}"
                for j in ranked
            ]
            selected_idx = st.selectbox(
                "Focus job (for materials below)",
                range(len(ranked)),
                format_func=lambda i: job_labels[i],
                index=st.session_state.selected_job_idx,
                key="job_select",
            )
            st.session_state.selected_job_idx = selected_idx

            if st.button("Regenerate materials for selected job"):
                resume_path = st.session_state.resume_path
                if resume_path and Path(resume_path).is_file():
                    with st.spinner("Tailoring for selected job…"):
                        sub = run_single_job_pipeline(resume_path, ranked[selected_idx])
                        result["tailored_cv"] = sub.get("tailored_cv")
                        result["cover_letter"] = sub.get("cover_letter")
                        result["interview_prep"] = sub.get("interview_prep")
                        result["selected_job"] = ranked[selected_idx]
                        st.session_state.pipeline_result = result
                        st.rerun()
                else:
                    st.warning("Re-upload your resume to regenerate materials.")

            st.markdown("##### All ranked matches")
            for i, job in enumerate(ranked, 1):
                _render_job_card(job, i)

    with tab_resume:
        _render_tailored_resume(result.get("tailored_cv"))

    with tab_letter:
        _render_cover_letter(result.get("cover_letter"))

    with tab_interview:
        _render_interview_prep(result.get("interview_prep"))

    with tab_log:
        logs = result.get("status_log", [])
        log_html = "<div class='pipeline-log'>" + "<br>".join(logs) + "</div>"
        st.markdown(log_html, unsafe_allow_html=True)

else:
    st.markdown("---")
    st.markdown(
        """
        **Get started**
        1. Upload your resume (PDF or DOCX)
        2. Enter target job titles and locations
        3. Click **Run full workflow**

        The orchestrator will parse your profile, search jobs, rank by semantic match,
        then tailor your resume, write a cover letter, and generate interview prep.
        """
    )
