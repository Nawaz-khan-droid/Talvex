"""
TALVEX - Dashboard Page
Overview with stats, funnel, recent applications, and quick actions.
"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.api_client import TALVEXClient


def _status_badge(status: str, colors: dict, bg_colors: dict) -> str:
    """Generate an HTML status badge."""
    color = colors.get(status, "#9CA3AF")
    bg = bg_colors.get(status, "#F3F4F6")
    return f'<span style="display:inline-block;padding:3px 12px;border-radius:9999px;font-size:12px;font-weight:600;background:{bg};color:{color};">{status}</span>'


def _platform_badge(platform: str, colors: dict) -> str:
    """Generate an HTML platform badge with colored dot."""
    p = platform.lower() if platform else "manual"
    color = colors.get(p, "#6B7280")
    name = platform.title() if platform and platform != "manual" else "Manual"
    return f'<span style="display:inline-flex;align-items:center;gap:5px;padding:3px 10px;border-radius:6px;font-size:12px;font-weight:500;background:#F3F4F6;color:#374151;"><span style="width:8px;height:8px;border-radius:50%;background:{color};display:inline-block;"></span>{name}</span>'


def _render_stats_card(icon: str, label: str, value, bg_color: str = "#F5F3FF", value_color: str = "#7C3AED") -> str:
    """Generate HTML for a stats card."""
    return f'''
    <div class="stat-card">
        <div style="font-size:24px;margin-bottom:6px;">{icon}</div>
        <div class="stat-value" style="color:{value_color};">{value}</div>
        <div class="stat-label">{label}</div>
    </div>
    '''


def render():
    st.markdown('<div class="page-title">Dashboard</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-subtitle">Your job application command center overview</div>', unsafe_allow_html=True)
    st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)

    # Load data
    try:
        analytics = TALVEXClient.get_analytics()
        applications = TALVEXClient.list_applications()
    except (ConnectionError, ValueError) as e:
        st.error(f"Could not connect to the TALVEX backend. Please ensure the server is running.")
        st.code(str(e))
        st.info("Tip: Start the backend with `cd /home/z/my-project/backend && uvicorn main:app --host 0.0.0.0 --port 8000`")
        return

    # ============================================================
    # Stats Cards Row
    # ============================================================
    total_apps = analytics.get("totalApplications", 0)
    active_pipeline = sum(
        item["count"] for item in analytics.get("funnel", [])
        if item["label"] not in {"Offer", "Rejected", "Ghosted"}
    )
    avg_match = analytics.get("overallMatchRate", 0)
    leak_alerts = analytics.get("leakAlerts", 0)
    total_personas = analytics.get("totalPersonas", 0)

    stats_html = f"""
    <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px;">
        {_render_stats_card("📋", "Total Applications", total_apps, "#F5F3FF", "#7C3AED")}
        {_render_stats_card("🔄", "Active Pipeline", active_pipeline, "#ECFDF5", "#059669")}
        {_render_stats_card("🎯", "Avg Match Score", f"{avg_match}%", "#FFF7ED", "#EA580C")}
        {_render_stats_card("🛡️", "Leak Alerts", leak_alerts, "#FEF2F2" if leak_alerts > 0 else "#F0FDF4", "#DC2626" if leak_alerts > 0 else "#059669")}
        {_render_stats_card("👤", "Personas", total_personas, "#EFF6FF", "#2563EB")}
    </div>
    """
    st.markdown(stats_html, unsafe_allow_html=True)

    st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)

    # ============================================================
    # Application Funnel + Recent Applications (2 column)
    # ============================================================
    col_funnel, col_recent = st.columns([1, 1.2])

    with col_funnel:
        st.markdown('<div class="talvex-card"><div class="section-header">Application Funnel</div>', unsafe_allow_html=True)

        funnel_data = analytics.get("funnel", [])
        if funnel_data:
            labels = [f["label"] for f in funnel_data]
            counts = [f["count"] for f in funnel_data]
            colors = [
                {"Scraped": "#9CA3AF", "Tailored": "#A78BFA", "Submitted": "#60A5FA",
                 "Screening": "#22D3EE", "Assessment": "#FB923C", "Interviewing": "#FBBF24",
                 "Offer": "#34D399", "Rejected": "#F87171", "Ghosted": "#A1A1AA"}.get(label, "#9CA3AF")
                for label in labels
            ]

            fig = go.Figure(go.Bar(
                y=labels,
                x=counts,
                orientation="h",
                marker_color=colors,
                text=counts,
                textposition="outside",
                hovertemplate="<b>%{y}</b>: %{x} applications<extra></extra>",
            ))
            fig.update_layout(
                height=380,
                margin=dict(l=90, r=30, t=10, b=10),
                xaxis=dict(visible=False),
                yaxis=dict(
                    tickfont=dict(size=12, color="#374151"),
                    categoryorder="array",
                    categoryarray=labels,
                ),
                plot_bgcolor="white",
                paper_bgcolor="white",
                showlegend=False,
                bargap=0.35,
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.markdown('<div class="empty-state"><div class="empty-state-icon">📊</div><div class="empty-state-text">No application data yet. Start by searching for jobs!</div></div>', unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

    with col_recent:
        st.markdown('<div class="talvex-card"><div class="section-header">Recent Applications</div>', unsafe_allow_html=True)

        if applications:
            # Show latest 5
            recent = applications[:5]
            rows_html = ""
            for app in recent:
                status = app.get("status", "Scraped")
                platform = app.get("platform", "manual")
                company = app.get("company", "Unknown")
                role = app.get("roleTitle", "Unknown")
                score = app.get("matchScore", 0)

                # Score color
                if score >= 70:
                    score_color = "#059669"
                elif score >= 40:
                    score_color = "#D97706"
                else:
                    score_color = "#DC2626"

                rows_html += f"""
                <div style="display:flex;align-items:center;justify-content:space-between;padding:10px 0;border-bottom:1px solid #F3F4F6;">
                    <div style="flex:1;min-width:0;">
                        <div style="font-weight:600;font-size:14px;color:#111827;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{company}</div>
                        <div style="font-size:12px;color:#6B7280;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{role}</div>
                    </div>
                    <div style="display:flex;align-items:center;gap:8px;flex-shrink:0;margin-left:12px;">
                        <span style="font-size:13px;font-weight:600;color:{score_color};">{score}%</span>
                        {_platform_badge(platform, PLATFORM_COLORS)}
                        {_status_badge(status, STATUS_COLORS, STATUS_BG_COLORS)}
                    </div>
                </div>
                """

            st.markdown(f'<div class="scroll-container">{rows_html}</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="empty-state"><div class="empty-state-icon">📭</div><div class="empty-state-text">No applications yet. Start by searching for jobs!</div></div>', unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)

    # ============================================================
    # Quick Actions
    # ============================================================
    st.markdown('<div class="section-header">Quick Actions</div>', unsafe_allow_html=True)

    col_a1, col_a2, col_a3, col_a4 = st.columns(4)

    with col_a1:
        if st.button("🔍  Search Jobs", use_container_width=True, type="primary"):
            st.session_state.page = "Job Search"
            st.rerun()

    with col_a2:
        if st.button("👤  Create Persona", use_container_width=True):
            st.session_state.page = "Personas"
            st.rerun()

    with col_a3:
        if st.button("🎯  Interview Prep", use_container_width=True):
            st.session_state.page = "Interview Prep"
            st.rerun()

    with col_a4:
        if st.button("📈  View Analytics", use_container_width=True):
            st.session_state.page = "Analytics"
            st.rerun()

    # ============================================================
    # Follow-Up Alerts
    # ============================================================
    st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)
    st.markdown('<div class="section-header">🔔 Follow-Up Alerts</div>', unsafe_allow_html=True)

    try:
        follow_up_data = TALVEXClient.get_follow_up_alerts(days_threshold=7)
        alerts = follow_up_data.get("alerts", [])
    except (ConnectionError, ValueError):
        alerts = []

    if alerts:
        for alert in alerts[:5]:
            urgency = alert.get("urgency", "Low")
            company = alert.get("company", "Unknown")
            role = alert.get("roleTitle", "")
            status = alert.get("status", "")
            days_since = alert.get("daysSinceApplied", 0)
            app_id = alert.get("applicationId", "")

            if urgency == "High":
                urgency_color, urgency_bg = "#DC2626", "#FEE2E2"
                urgency_icon = "🔴"
            elif urgency == "Medium":
                urgency_color, urgency_bg = "#D97706", "#FEF3C7"
                urgency_icon = "🟡"
            else:
                urgency_color, urgency_bg = "#2563EB", "#DBEAFE"
                urgency_icon = "🔵"

            col_alert, col_btn = st.columns([4, 1])
            with col_alert:
                st.markdown(f'''
                <div style="background:{urgency_bg};border:1px solid {urgency_color}33;border-radius:8px;padding:12px 16px;margin-bottom:8px;">
                    <div style="display:flex;align-items:center;justify-content:space-between;">
                        <div>
                            <div style="font-size:14px;font-weight:600;color:#111827;">{urgency_icon} {company} - {role}</div>
                            <div style="font-size:12px;color:#6B7280;margin-top:2px;">{days_since} days since applied · Status: {status} · Urgency: {urgency}</div>
                        </div>
                    </div>
                </div>
                ''', unsafe_allow_html=True)
            with col_btn:
                if st.button("📝 Follow Up", key=f"followup_{app_id}", use_container_width=True):
                    with st.spinner("Generating template..."):
                        try:
                            template = TALVEXClient.get_follow_up_template(app_id)
                            st.session_state["follow_up_template"] = template.get("template", "")
                            st.session_state["follow_up_app"] = company
                            st.success("Template generated!")
                        except (ConnectionError, ValueError) as e:
                            st.error(str(e))

        # Show generated template if exists
        template_text = st.session_state.get("follow_up_template")
        if template_text:
            app_name = st.session_state.get("follow_up_app", "Company")
            st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
            st.markdown(f'<div class="section-header">Follow-Up Template for {app_name}</div>', unsafe_allow_html=True)
            st.text_area("Template", value=template_text, height=300, key="follow_up_template_area")
    else:
        st.markdown('''
        <div class="talvex-card" style="text-align:center;padding:30px 20px;">
            <div style="font-size:32px;margin-bottom:8px;">✅</div>
            <div style="font-size:14px;color:#6B7280;">No follow-up alerts right now. All applications are within the 7-day threshold.</div>
        </div>
        ''', unsafe_allow_html=True)

    # ============================================================
    # Platform Breakdown (bottom row)
    # ============================================================
    st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)
    st.markdown('<div class="talvex-card"><div class="section-header">Platform Breakdown</div>', unsafe_allow_html=True)

    platform_data = analytics.get("platformBreakdown", [])
    if platform_data:
        p_labels = [p["platform"].title() for p in platform_data]
        p_counts = [p["count"] for p in platform_data]
        p_colors = [
            PLATFORM_COLORS.get(p["platform"].lower(), "#6B7280")
            for p in platform_data
        ]

        fig_platform = go.Figure(go.Bar(
            x=p_labels,
            y=p_counts,
            marker_color=p_colors,
            text=p_counts,
            textposition="outside",
        ))
        fig_platform.update_layout(
            height=280,
            margin=dict(l=20, r=20, t=10, b=40),
            xaxis=dict(tickfont=dict(size=11, color="#374151")),
            yaxis=dict(visible=False),
            plot_bgcolor="white",
            paper_bgcolor="white",
            showlegend=False,
            bargap=0.4,
        )
        st.plotly_chart(fig_platform, use_container_width=True)
    else:
        st.markdown('<div class="empty-state"><div class="empty-state-text">No platform data available yet.</div></div>', unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


# Need access to constants from app.py - import them for use here
# They are imported via sys.path from the parent app module
# We define them locally to avoid circular imports
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

STATUS_BG_COLORS = {
    "Scraped": "#F3F4F6",
    "Tailored": "#F5F3FF",
    "Submitted": "#EFF6FF",
    "Screening": "#ECFEFF",
    "Assessment": "#FFF7ED",
    "Interviewing": "#FFFBEB",
    "Offer": "#ECFDF5",
    "Rejected": "#FEF2F2",
    "Ghosted": "#F4F4F5",
}
