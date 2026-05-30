"""
TALVEX - Pipeline Page
Kanban-style pipeline view for application status tracking.
"""

import streamlit as st

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.api_client import TALVEXClient

# ============================================================
# Constants
# ============================================================

STATUSES = [
    "Scraped", "Tailored", "Submitted", "Screening",
    "Assessment", "Interviewing", "Offer", "Rejected", "Ghosted",
]

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

FSM_TRANSITIONS = {
    "Scraped": ["Tailored", "Rejected"],
    "Tailored": ["Submitted", "Rejected"],
    "Submitted": ["Screening", "Assessment", "Interviewing", "Ghosted", "Rejected"],
    "Screening": ["Assessment", "Interviewing", "Rejected", "Ghosted"],
    "Assessment": ["Interviewing", "Rejected", "Ghosted"],
    "Interviewing": ["Offer", "Rejected", "Ghosted"],
}

TERMINAL_STATES = {"Offer", "Rejected", "Ghosted"}


def _status_badge(status: str) -> str:
    color = STATUS_COLORS.get(status, "#9CA3AF")
    bg = STATUS_BG_COLORS.get(status, "#F3F4F6")
    return f'<span style="display:inline-block;padding:2px 8px;border-radius:9999px;font-size:11px;font-weight:600;background:{bg};color:{color};">{status}</span>'


def _platform_badge(platform: str) -> str:
    p = platform.lower() if platform else "manual"
    color = PLATFORM_COLORS.get(p, "#6B7280")
    name = platform.title() if platform and platform != "manual" else "Manual"
    return f'<span style="display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:500;background:#F3F4F6;color:#374151;"><span style="width:6px;height:6px;border-radius:50%;background:{color};display:inline-block;"></span>{name}</span>'


def _score_color(score):
    if score >= 70:
        return "#059669"
    elif score >= 40:
        return "#D97706"
    return "#DC2626"


def render():
    st.markdown('<div class="page-title">Pipeline</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-subtitle">Track and advance your job applications through each stage</div>', unsafe_allow_html=True)
    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

    # ============================================================
    # Filters
    # ============================================================
    filter_col1, filter_col2 = st.columns([3, 1])
    with filter_col1:
        filter_platform = st.selectbox(
            "Filter by Platform",
            options=["All Platforms"] + list(p.title() for p in PLATFORM_COLORS.keys()),
            format_func=lambda x: x,
            key="pipeline_platform_filter",
        )
    with filter_col2:
        view_mode = st.selectbox(
            "View",
            options=["Kanban", "Table"],
            key="pipeline_view_mode",
        )

    # Load applications
    try:
        applications = TALVEXClient.list_applications()
    except (ConnectionError, ValueError) as e:
        st.error(f"Could not load applications: {e}")
        return

    # Apply platform filter
    if filter_platform != "All Platforms":
        applications = [a for a in applications if a.get("platform", "").lower() == filter_platform.lower()]

    if not applications:
        st.markdown('''
        <div class="talvex-card" style="text-align:center;padding:60px 20px;">
            <div style="font-size:56px;margin-bottom:16px;">📋</div>
            <div style="font-size:18px;font-weight:600;color:#111827;margin-bottom:8px;">Pipeline Is Empty</div>
            <div style="font-size:14px;color:#6B7280;">Search for jobs and ingest them to start tracking your applications.</div>
        </div>
        ''', unsafe_allow_html=True)
        return

    # ============================================================
    # Kanban View
    # ============================================================
    if view_mode == "Kanban":
        # Group by status
        by_status = {s: [] for s in STATUSES}
        for app in applications:
            status = app.get("status", "Scraped")
            if status in by_status:
                by_status[status].append(app)

        # Display as scrollable columns
        # Use tabs for each status group to avoid too many columns
        tab_labels = ["Scraped → Tailored → Submitted", "Screening → Assessment → Interviewing", "Offer / Rejected / Ghosted"]

        tab1, tab2, tab3 = st.tabs(tab_labels)

        for tab, statuses in [(tab1, ["Scraped", "Tailored", "Submitted"]),
                               (tab2, ["Screening", "Assessment", "Interviewing"]),
                               (tab3, ["Offer", "Rejected", "Ghosted"])]:
            with tab:
                cols = st.columns(len(statuses))
                for idx, status in enumerate(statuses):
                    with cols[idx]:
                        apps = by_status.get(status, [])
                        count = len(apps)
                        color = STATUS_COLORS.get(status, "#9CA3AF")
                        bg = STATUS_BG_COLORS.get(status, "#F3F4F6")

                        st.markdown(f'''
                        <div class="kanban-column">
                            <div class="kanban-column-header" style="background:{bg};color:{color};">
                                {status} <span style="opacity:0.7;">({count})</span>
                            </div>
                        ''', unsafe_allow_html=True)

                        if apps:
                            for app in apps:
                                app_id = app.get("id", "")
                                company = app.get("company", "Unknown")
                                role = app.get("roleTitle", "")
                                score = app.get("matchScore", 0)
                                platform = app.get("platform", "manual")
                                s_color = _score_color(score)

                                st.markdown(f'''
                                <div class="kanban-card">
                                    <div style="font-size:13px;font-weight:600;color:#111827;margin-bottom:2px;">{company}</div>
                                    <div style="font-size:12px;color:#6B7280;margin-bottom:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{role}</div>
                                    <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
                                        <span style="font-size:12px;font-weight:600;color:{s_color};">{score}%</span>
                                        {_platform_badge(platform)}
                                    </div>
                                </div>
                                ''', unsafe_allow_html=True)

                                # Action buttons
                                valid_transitions = FSM_TRANSITIONS.get(status, [])
                                if valid_transitions:
                                    advance_options = ["Advance To:"] + valid_transitions
                                    selected = st.selectbox(
                                        "Status",
                                        options=advance_options,
                                        key=f"advance_{app_id}",
                                        label_visibility="collapsed",
                                    )
                                    if selected != "Advance To:":
                                        if st.button(f"✓ Move to {selected}", key=f"adv_btn_{app_id}", use_container_width=True, type="primary"):
                                            with st.spinner("Advancing..."):
                                                try:
                                                    result = TALVEXClient.advance_application(app_id, selected)
                                                    st.success(f"Moved to {result.get('newStatus', selected)}")
                                                    st.session_state.refresh_key += 1
                                                    st.rerun()
                                                except (ConnectionError, ValueError) as e:
                                                    st.error(str(e))

                                # Delete button
                                if st.button("🗑️", key=f"del_{app_id}", help="Delete Application"):
                                    with st.spinner("Deleting..."):
                                        try:
                                            TALVEXClient.delete_application(app_id)
                                            st.success("Application deleted.")
                                            st.session_state.refresh_key += 1
                                            st.rerun()
                                        except (ConnectionError, ValueError) as e:
                                            st.error(str(e))

                                st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)
                        else:
                            st.markdown('<div style="text-align:center;padding:20px 0;font-size:12px;color:#9CA3AF;">No applications</div>', unsafe_allow_html=True)

                        st.markdown("</div>", unsafe_allow_html=True)

    # ============================================================
    # Table View
    # ============================================================
    else:
        # Simple table view
        rows = []
        for app in applications:
            rows.append({
                "Company": app.get("company", ""),
                "Role": app.get("roleTitle", ""),
                "Status": app.get("status", ""),
                "Platform": app.get("platform", "").title(),
                "Match Score": f"{app.get('matchScore', 0)}%",
                "ATS Score": f"{app.get('atsScore', 0)}%",
                "Location": app.get("location", ""),
            })

        if rows:
            import pandas as pd
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True, height=500)

            # Advance selected application
            st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)
            st.markdown('<div class="section-header">Advance Application</div>', unsafe_allow_html=True)

            app_options = {f"{a.get('company', '')} - {a.get('roleTitle', '')} ({a.get('status', '')})": a.get('id', '') for a in applications}

            if app_options:
                selected_app_label = st.selectbox("Select Application", options=list(app_options.keys()), key="table_advance_select")
                selected_app_id = app_options[selected_app_label]

                current_status = next((a.get("status", "Scraped") for a in applications if a.get("id") == selected_app_id), "Scraped")
                valid_transitions = FSM_TRANSITIONS.get(current_status, [])

                if valid_transitions:
                    target = st.selectbox("Move To", options=valid_transitions, key="table_advance_target")
                    if st.button("Advance Status", type="primary", key="table_advance_btn"):
                        with st.spinner("Advancing..."):
                            try:
                                result = TALVEXClient.advance_application(selected_app_id, target)
                                st.success(f"Moved to {result.get('newStatus', target)}")
                                st.session_state.refresh_key += 1
                                st.rerun()
                            except (ConnectionError, ValueError) as e:
                                st.error(str(e))
                else:
                    st.info("This application is in a terminal state and cannot be advanced.")
