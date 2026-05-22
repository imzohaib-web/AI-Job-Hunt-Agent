"""
frontend/dashboard.py
=====================
Streamlit analytics dashboard — KPIs, charts, filters, CSV export.

Run standalone:
    streamlit run frontend/dashboard.py

Or as multipage app (with app.py):
    streamlit run app.py
    → use sidebar link "Analytics"
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from Agents.analytics import (
    APPLICATION_STATUSES,
    calculate_statistics,
    get_all_applications,
)

_DASHBOARD_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.kpi-card {
    background: linear-gradient(145deg, #151b2b 0%, #1a2236 100%);
    border: 1px solid #2d3748;
    border-radius: 12px;
    padding: 1rem 1.25rem;
    text-align: center;
}
.kpi-value { font-size: 1.75rem; font-weight: 700; color: #a5b4fc; }
.kpi-label { font-size: 0.85rem; color: #94a3b8; margin-top: 0.25rem; }
</style>
"""


def _kpi_card(label: str, value: str) -> None:
    st.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-value">{value}</div>
            <div class="kpi-label">{label}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_analytics_dashboard() -> None:
    """Render the full analytics UI (safe to call from pages/1_Analytics.py)."""
    st.markdown(_DASHBOARD_CSS, unsafe_allow_html=True)

    with st.sidebar:
        st.markdown("### 🔍 Filters")
        company_filter = st.text_input("Company", placeholder="e.g. Google", key="an_company")
        status_filter = st.selectbox(
            "Status",
            options=["all"] + list(APPLICATION_STATUSES),
            index=0,
            key="an_status",
        )
        st.markdown("**Match score range**")
        score_col1, score_col2 = st.columns(2)
        with score_col1:
            min_score = st.number_input("Min %", 0, 100, 0, key="an_min_score")
        with score_col2:
            max_score = st.number_input("Max %", 0, 100, 100, key="an_max_score")
        if min_score > max_score:
            st.warning("Min score should be ≤ max score.")

        st.divider()
        st.markdown("### ➕ Quick update")
        with st.expander("Update application status"):
            app_id_input = st.number_input("Application ID", min_value=1, step=1, key="an_app_id")
            new_status = st.selectbox("New status", APPLICATION_STATUSES, key="an_new_status")
            if st.button("Save status", key="an_save_status"):
                try:
                    from core.config import get_db
                    conn = get_db()
                    conn.execute(
                        "UPDATE applications SET status = ? WHERE id = ?",
                        (new_status, int(app_id_input)),
                    )
                    conn.commit()
                    conn.close()
                    st.success(f"Application #{app_id_input} → {new_status}")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

        st.divider()
        st.caption("Home: select **app** in the sidebar")

    company_arg = company_filter.strip() or None
    status_arg = None if status_filter == "all" else status_filter
    min_arg = float(min_score) if min_score > 0 else None
    max_arg = float(max_score) if max_score < 100 else None

    stats = calculate_statistics(
        company=company_arg,
        status=status_arg,
        min_score=min_arg,
        max_score=max_arg,
    )
    df = get_all_applications(
        company=company_arg,
        status=status_arg,
        min_score=min_arg,
        max_score=max_arg,
    )

    st.markdown("## 📊 Job Hunting Analytics")
    st.caption("Track searches, applications, match scores, and outcomes from your SQLite database.")

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    with k1:
        _kpi_card("Jobs searched", f"{stats['total_jobs_searched']:,}")
    with k2:
        _kpi_card("Applications", f"{stats['total_applications']:,}")
    with k3:
        _kpi_card("Avg match", f"{stats['average_match_score']}%")
    with k4:
        _kpi_card("Interview rate", f"{stats['interview_rate']}%")
    with k5:
        _kpi_card("Success rate", f"{stats['application_success_rate']}%")
    with k6:
        top_co = stats["top_companies"][0]["company"] if stats["top_companies"] else "—"
        _kpi_card("Top company", str(top_co)[:18])

    st.markdown("---")

    chart_left, chart_right = st.columns(2)
    with chart_left:
        st.markdown("#### Applications over time")
        if stats["applications_over_time"]:
            ts_df = pd.DataFrame(stats["applications_over_time"])
            ts_df["date"] = pd.to_datetime(ts_df["date"])
            st.line_chart(ts_df.set_index("date")["count"], width="stretch")
        else:
            st.info("No application history yet. Run the main workflow to generate data.")

    with chart_right:
        st.markdown("#### Match score distribution")
        if stats["match_score_distribution"]:
            dist_df = pd.DataFrame(stats["match_score_distribution"])
            st.bar_chart(dist_df.set_index("bucket")["count"], width="stretch")
        else:
            st.info("No match scores in filtered data.")

    chart_pie, chart_bar = st.columns(2)
    with chart_pie:
        st.markdown("#### Application status")
        if stats["status_breakdown"]:
            pie_df = pd.DataFrame(stats["status_breakdown"])
            try:
                import matplotlib.pyplot as plt

                fig, ax = plt.subplots(figsize=(5, 4))
                fig.patch.set_facecolor("#0b0f19")
                ax.set_facecolor("#0b0f19")
                colors = ["#6366f1", "#818cf8", "#a5b4fc", "#f87171", "#34d399"]
                ax.pie(
                    pie_df["count"],
                    labels=pie_df["status"],
                    autopct="%1.0f%%",
                    colors=colors[: len(pie_df)],
                    textprops={"color": "white", "fontsize": 9},
                )
                st.pyplot(fig, width="stretch")
                plt.close(fig)
            except ImportError:
                st.bar_chart(pie_df.set_index("status")["count"], width="stretch")
        else:
            st.info("No applications to chart.")

    with chart_bar:
        st.markdown("#### Top companies")
        if stats["top_companies"]:
            co_df = pd.DataFrame(stats["top_companies"])
            st.bar_chart(co_df.set_index("company")["applications"], width="stretch")
        else:
            st.info("No company data yet.")

    st.markdown("---")
    st.markdown("#### 📋 Applications detail")

    if df.empty:
        st.warning(
            "No applications match your filters. Run a workflow on the **Home** page "
            "to populate data."
        )
    else:
        display_df = df[
            [
                "application_id",
                "status",
                "candidate_name",
                "job_title",
                "company",
                "location",
                "match_score",
                "applied_at",
                "application_created_at",
            ]
        ].copy()
        display_df.columns = [
            "ID", "Status", "Candidate", "Role", "Company",
            "Location", "Match %", "Applied at", "Created",
        ]
        st.dataframe(display_df, width="stretch", hide_index=True)

        csv_bytes = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="⬇️ Download CSV report",
            data=csv_bytes,
            file_name="job_hunting_analytics_report.csv",
            mime="text/csv",
            type="primary",
            key="an_csv_download",
        )

    with st.expander("Raw statistics JSON"):
        st.json(stats)


if __name__ == "__main__":
    st.set_page_config(
        page_title="Job Hunt Analytics",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    render_analytics_dashboard()
