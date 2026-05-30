"""
TALVEX - Analytics Page
Comprehensive analytics dashboard with charts and insights.
"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.api_client import TALVEXClient

# ============================================================
# Constants
# ============================================================

PLATFORM_COLORS = {
    "linkedin": "#0A66C2",
    "indeed": "#2164F3",
    "naukri": "#4A90D9",
    "internshala": "#0066FF",
    "unstop": "#FF6B00",
    "foundit": "#FF5A00",
    "manual": "#6B7280",
    "email": "#6B7280",
}

STATUS_COLORS = {
    "Scraped": "#9CA3AF",
    "Tailored": "#A78BFA",
    "Submitted": "#60A5FA",
    "Screening": "#22D3EE",
    "Assessment": "#FB923C",
    "Interviewing": "#FBBF24",
    "Offer": "#34D399",
    "Rejected": "#F87171",
    "Ghosted": "#A1A1AA",
}

STATUS_ORDER = [
    "Scraped", "Tailored", "Submitted", "Screening",
    "Assessment", "Interviewing", "Offer", "Rejected", "Ghosted",
]


def render():
    st.markdown('<div class="page-title">Analytics</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-subtitle">Deep insights into your job application performance</div>', unsafe_allow_html=True)
    st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)

    # Load data
    try:
        analytics = TALVEXClient.get_analytics()
        applications = TALVEXClient.list_applications()
    except (ConnectionError, ValueError) as e:
        st.error(f"Could not load analytics data: {e}")
        return

    if not analytics and not applications:
        st.markdown('''
        <div class="talvex-card" style="text-align:center;padding:60px 20px;">
            <div style="font-size:56px;margin-bottom:16px;">📈</div>
            <div style="font-size:18px;font-weight:600;color:#111827;margin-bottom:8px;">No Data Yet</div>
            <div style="font-size:14px;color:#6B7280;">Start applying to jobs to see analytics and insights.</div>
        </div>
        ''', unsafe_allow_html=True)
        return

    # ============================================================
    # Top Stats
    # ============================================================
    total_apps = analytics.get("totalApplications", 0)
    avg_match = analytics.get("overallMatchRate", 0)
    response_rate = analytics.get("responseRate", 0)
    leak_alerts = analytics.get("leakAlerts", 0)
    total_personas = analytics.get("totalPersonas", 0)

    stats_html = f'''
    <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 16px;">
        <div class="stat-card">
            <div style="font-size:20px;margin-bottom:4px;">📋</div>
            <div class="stat-value" style="font-size:24px;">{total_apps}</div>
            <div class="stat-label">Total Applications</div>
        </div>
        <div class="stat-card">
            <div style="font-size:20px;margin-bottom:4px;">🎯</div>
            <div class="stat-value" style="font-size:24px;">{avg_match}%</div>
            <div class="stat-label">Avg Match Score</div>
        </div>
        <div class="stat-card">
            <div style="font-size:20px;margin-bottom:4px;">📨</div>
            <div class="stat-value" style="font-size:24px;">{response_rate}%</div>
            <div class="stat-label">Response Rate</div>
        </div>
        <div class="stat-card">
            <div style="font-size:20px;margin-bottom:4px;">🛡️</div>
            <div class="stat-value" style="font-size:24px;color:{'#DC2626' if leak_alerts > 0 else '#059669'};">{leak_alerts}</div>
            <div class="stat-label">Leak Alerts</div>
        </div>
        <div class="stat-card">
            <div style="font-size:20px;margin-bottom:4px;">👤</div>
            <div class="stat-value" style="font-size:24px;">{total_personas}</div>
            <div class="stat-label">Personas</div>
        </div>
    </div>
    '''
    st.markdown(stats_html, unsafe_allow_html=True)

    st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)

    # ============================================================
    # Conversion Funnel
    # ============================================================
    col_funnel, col_platform = st.columns([1, 1])

    with col_funnel:
        st.markdown('<div class="talvex-card"><div class="section-header">Conversion Funnel</div>', unsafe_allow_html=True)

        funnel_data = analytics.get("funnel", [])
        if funnel_data:
            labels = [f["label"] for f in funnel_data]
            counts = [f["count"] for f in funnel_data]
            colors = [STATUS_COLORS.get(label, "#9CA3AF") for label in labels]

            # Calculate percentages based on total
            max_count = max(counts) if counts else 1
            percentages = [round((c / max_count) * 100, 1) if max_count > 0 else 0 for c in counts]

            fig_funnel = go.Figure(go.Bar(
                y=labels,
                x=counts,
                orientation="h",
                marker_color=colors,
                text=[f"{c} ({p}%)" for c, p in zip(counts, percentages)],
                textposition="outside",
                hovertemplate="<b>%{y}</b>: %{x} applications<extra></extra>",
            ))
            fig_funnel.update_layout(
                height=400,
                margin=dict(l=100, r=50, t=10, b=10),
                xaxis=dict(visible=False),
                yaxis=dict(
                    tickfont=dict(size=11, color="#374151"),
                    categoryorder="array",
                    categoryarray=labels,
                ),
                plot_bgcolor="white",
                paper_bgcolor="white",
                showlegend=False,
                bargap=0.35,
            )
            st.plotly_chart(fig_funnel, use_container_width=True)
        else:
            st.markdown('<div class="empty-state"><div class="empty-state-text">No funnel data yet.</div></div>', unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

    with col_platform:
        st.markdown('<div class="talvex-card"><div class="section-header">Platform Breakdown</div>', unsafe_allow_html=True)

        platform_data = analytics.get("platformBreakdown", [])
        if platform_data:
            p_labels = [p["platform"].title() for p in platform_data]
            p_counts = [p["count"] for p in platform_data]
            p_colors = [PLATFORM_COLORS.get(p["platform"].lower(), "#6B7280") for p in platform_data]
            p_avg_scores = [p.get("avgScore", 0) for p in platform_data]

            fig_platform = go.Figure(go.Bar(
                x=p_labels,
                y=p_counts,
                marker_color=p_colors,
                text=p_counts,
                textposition="outside",
            ))
            fig_platform.update_layout(
                height=400,
                margin=dict(l=20, r=20, t=10, b=40),
                xaxis=dict(
                    tickfont=dict(size=11, color="#374151"),
                    tickangle=0,
                ),
                yaxis=dict(visible=False),
                plot_bgcolor="white",
                paper_bgcolor="white",
                showlegend=False,
                bargap=0.4,
            )
            st.plotly_chart(fig_platform, use_container_width=True)

            # Avg score per platform
            if any(p_avg_scores):
                st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
                st.markdown('<div style="font-size:13px;font-weight:600;color:#374151;margin-bottom:8px;">Avg Match Score by Platform</div>', unsafe_allow_html=True)
                for p, score in zip(platform_data, p_avg_scores):
                    pname = p["platform"].title()
                    scolor = "#059669" if score >= 60 else "#D97706" if score >= 40 else "#DC2626"
                    st.markdown(f'''
                    <div style="display:flex;align-items:center;justify-content:space-between;padding:4px 0;">
                        <span style="font-size:13px;color:#374151;">{pname}</span>
                        <span style="font-size:13px;font-weight:600;color:{scolor};">{score}%</span>
                    </div>
                    <div class="score-bar"><div class="score-bar-fill" style="width:{score}%;background:{scolor};"></div></div>
                    ''', unsafe_allow_html=True)
        else:
            st.markdown('<div class="empty-state"><div class="empty-state-text">No platform data yet.</div></div>', unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)

    # ============================================================
    # Score Distribution + Top Companies
    # ============================================================
    col_score, col_companies = st.columns([1, 1])

    with col_score:
        st.markdown('<div class="talvex-card"><div class="section-header">Score Distribution</div>', unsafe_allow_html=True)

        if applications:
            scores = [a.get("matchScore", 0) for a in applications if a.get("matchScore") is not None]
            if scores:
                fig_hist = px.histogram(
                    x=scores,
                    nbins=20,
                    color_discrete_sequence=["#A78BFA"],
                )
                fig_hist.update_layout(
                    height=300,
                    margin=dict(l=30, r=20, t=10, b=40),
                    xaxis_title="Match Score (%)",
                    yaxis_title="Count",
                    xaxis=dict(
                        tickfont=dict(size=11),
                        title_font=dict(size=12, color="#6B7280"),
                    ),
                    yaxis=dict(
                        tickfont=dict(size=11),
                        title_font=dict(size=12, color="#6B7280"),
                    ),
                    plot_bgcolor="white",
                    paper_bgcolor="white",
                    showlegend=False,
                    bargap=0.1,
                )
                # Color the bars based on score ranges
                fig_hist.update_traces(marker_color=scores, selector=dict(type='histogram'))
                # Use a single color instead
                fig_hist.update_traces(marker_color="#A78BFA")
                st.plotly_chart(fig_hist, use_container_width=True)

                # Score summary
                avg_s = sum(scores) / len(scores)
                max_s = max(scores)
                min_s = min(scores)
                above_70 = sum(1 for s in scores if s >= 70)
                st.markdown(f'''
                <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:12px;">
                    <div style="text-align:center;padding:8px;background:#F9FAFB;border-radius:6px;">
                        <div style="font-size:18px;font-weight:600;color:#7C3AED;">{avg_s:.1f}</div>
                        <div style="font-size:11px;color:#6B7280;">Average</div>
                    </div>
                    <div style="text-align:center;padding:8px;background:#F9FAFB;border-radius:6px;">
                        <div style="font-size:18px;font-weight:600;color:#059669;">{max_s:.1f}</div>
                        <div style="font-size:11px;color:#6B7280;">Highest</div>
                    </div>
                    <div style="text-align:center;padding:8px;background:#F9FAFB;border-radius:6px;">
                        <div style="font-size:18px;font-weight:600;color:#DC2626;">{min_s:.1f}</div>
                        <div style="font-size:11px;color:#6B7280;">Lowest</div>
                    </div>
                    <div style="text-align:center;padding:8px;background:#F9FAFB;border-radius:6px;">
                        <div style="font-size:18px;font-weight:600;color:#2563EB;">{above_70}</div>
                        <div style="font-size:11px;color:#6B7280;">Above 70%</div>
                    </div>
                </div>
                ''', unsafe_allow_html=True)
            else:
                st.markdown('<div class="empty-state"><div class="empty-state-text">No score data available.</div></div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="empty-state"><div class="empty-state-text">No applications to analyze.</div></div>', unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

    with col_companies:
        st.markdown('<div class="talvex-card"><div class="section-header">Top Companies</div>', unsafe_allow_html=True)

        if applications:
            from collections import Counter
            company_counts = Counter(a.get("company", "Unknown") for a in applications)
            top_companies = company_counts.most_common(10)

            if top_companies:
                comp_labels = [c[0] for c in top_companies]
                comp_counts = [c[1] for c in top_companies]

                fig_companies = go.Figure(go.Bar(
                    y=comp_labels,
                    x=comp_counts,
                    orientation="h",
                    marker_color="#7C3AED",
                    text=comp_counts,
                    textposition="outside",
                ))
                fig_companies.update_layout(
                    height=300,
                    margin=dict(l=120, r=40, t=10, b=10),
                    xaxis=dict(visible=False),
                    yaxis=dict(
                        tickfont=dict(size=11, color="#374151"),
                    ),
                    plot_bgcolor="white",
                    paper_bgcolor="white",
                    showlegend=False,
                    bargap=0.3,
                )
                st.plotly_chart(fig_companies, use_container_width=True)
            else:
                st.markdown('<div class="empty-state"><div class="empty-state-text">No company data.</div></div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="empty-state"><div class="empty-state-text">No applications to analyze.</div></div>', unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)

    # ============================================================
    # Salary Trends
    # ============================================================
    salary_data = analytics.get("salaryTrends", [])
    if salary_data and any(s.get("count", 0) > 0 for s in salary_data):
        st.markdown('<div class="talvex-card"><div class="section-header">Salary Trends</div>', unsafe_allow_html=True)

        active_salary = [s for s in salary_data if s.get("count", 0) > 0]
        sal_labels = [s.get("rangeLabel", "") for s in active_salary]
        sal_counts = [s.get("count", 0) for s in active_salary]

        fig_salary = go.Figure(go.Bar(
            x=sal_labels,
            y=sal_counts,
            marker_color="#FB923C",
            text=sal_counts,
            textposition="outside",
        ))
        fig_salary.update_layout(
            height=280,
            margin=dict(l=20, r=20, t=10, b=40),
            xaxis=dict(
                tickfont=dict(size=11, color="#374151"),
                title_font=dict(size=12, color="#6B7280"),
                title_text="Salary Range (INR)",
            ),
            yaxis=dict(
                tickfont=dict(size=11),
                title_font=dict(size=12, color="#6B7280"),
                title_text="Number of Jobs",
            ),
            plot_bgcolor="white",
            paper_bgcolor="white",
            showlegend=False,
            bargap=0.4,
        )
        st.plotly_chart(fig_salary, use_container_width=True)

        st.markdown("</div>", unsafe_allow_html=True)

    # ============================================================
    # Application Timeline (if data available)
    # ============================================================
    if applications:
        st.markdown('<div class="talvex-card"><div class="section-header">Application Activity</div>', unsafe_allow_html=True)

        dates = []
        for app in applications:
            created = app.get("createdAt", "")
            if created:
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    dates.append(dt.strftime("%Y-%m-%d"))
                except (ValueError, AttributeError):
                    pass

        if dates:
            date_counts = Counter(dates)
            sorted_dates = sorted(date_counts.items(), reverse=True)[:30]

            if sorted_dates:
                day_labels = [d[0] for d in sorted_dates]
                day_counts = [d[1] for d in sorted_dates]

                fig_timeline = go.Figure(go.Scatter(
                    x=day_labels,
                    y=day_counts,
                    mode="lines+markers",
                    line=dict(color="#7C3AED", width=2),
                    marker=dict(size=8, color="#7C3AED"),
                    fill="tozeroy",
                    fillcolor="rgba(124, 58, 237, 0.08)",
                ))
                fig_timeline.update_layout(
                    height=280,
                    margin=dict(l=20, r=20, t=10, b=40),
                    xaxis=dict(
                        tickfont=dict(size=10, color="#374151"),
                        title_font=dict(size=12, color="#6B7280"),
                    ),
                    yaxis=dict(
                        tickfont=dict(size=11),
                        title_font=dict(size=12, color="#6B7280"),
                        title_text="Applications",
                    ),
                    plot_bgcolor="white",
                    paper_bgcolor="white",
                    showlegend=False,
                )
                st.plotly_chart(fig_timeline, use_container_width=True)

        st.markdown("</div>", unsafe_allow_html=True)
