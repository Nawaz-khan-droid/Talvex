"""
TALVEX - Interview Prep Page
Generate interview questions, tips, and prep materials for your applications.
"""

import streamlit as st
import json

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.api_client import TALVEXClient


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


def render():
    st.markdown('<div class="page-title">Interview Prep</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-subtitle">Generate personalized interview questions and preparation materials</div>', unsafe_allow_html=True)
    st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)

    # Load applications
    try:
        applications = TALVEXClient.list_applications()
    except (ConnectionError, ValueError) as e:
        st.error(f"Could not load applications: {e}")
        return

    # Filter for applications that have job descriptions
    apps_with_jd = [a for a in applications if a.get("jobDescription")]

    if not apps_with_jd:
        st.markdown('''
        <div class="talvex-card" style="text-align:center;padding:60px 20px;">
            <div style="font-size:56px;margin-bottom:16px;">🎯</div>
            <div style="font-size:18px;font-weight:600;color:#111827;margin-bottom:8px;">No Applications Yet</div>
            <div style="font-size:14px;color:#6B7280;max-width:400px;margin:0 auto;">
                Search for jobs and ingest them into your pipeline to generate interview prep materials.
            </div>
        </div>
        ''', unsafe_allow_html=True)
        return

    # ============================================================
    # Application Selector
    # ============================================================
    app_options = {
        f"{a.get('company', '')} - {a.get('roleTitle', '')}": a
        for a in apps_with_jd
    }

    col_select, col_status = st.columns([3, 1])
    with col_select:
        selected_label = st.selectbox(
            "Select Application",
            options=list(app_options.keys()),
            key="interview_prep_select",
        )
    with col_status:
        selected_app = app_options[selected_label]
        status = selected_app.get("status", "Scraped")
        color = STATUS_COLORS.get(status, "#9CA3AF")
        bg = STATUS_BG_COLORS.get(status, "#F3F4F6")
        st.markdown(f'''
        <div style="margin-top:28px;text-align:center;padding:8px 16px;border-radius:8px;background:{bg};color:{color};font-size:14px;font-weight:600;">
            {status}
        </div>
        ''', unsafe_allow_html=True)

    selected_app = app_options[selected_label]

    # Show company and role info
    company = selected_app.get("company", "")
    role = selected_app.get("roleTitle", "")
    match_score = selected_app.get("matchScore", 0)
    jd = selected_app.get("jobDescription", "")

    st.markdown(f'''
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:16px;">
        <div class="talvex-card" style="text-align:center;padding:12px;">
            <div style="font-size:11px;color:#6B7280;">Company</div>
            <div style="font-size:16px;font-weight:600;color:#111827;">{company}</div>
        </div>
        <div class="talvex-card" style="text-align:center;padding:12px;">
            <div style="font-size:11px;color:#6B7280;">Role</div>
            <div style="font-size:16px;font-weight:600;color:#111827;">{role}</div>
        </div>
        <div class="talvex-card" style="text-align:center;padding:12px;">
            <div style="font-size:11px;color:#6B7280;">Match Score</div>
            <div style="font-size:16px;font-weight:600;color:{'#059669' if match_score >= 70 else '#D97706' if match_score >= 40 else '#DC2626'};">{match_score}%</div>
        </div>
    </div>
    ''', unsafe_allow_html=True)

    # ============================================================
    # Generate Button
    # ============================================================
    if st.button("🎯 Generate Interview Prep", type="primary", use_container_width=True, key="gen_interview_prep"):
        with st.spinner("Generating personalized interview prep..."):
            try:
                result = TALVEXClient.generate_interview_prep(
                    job_description=jd,
                    company=company,
                    role=role,
                )
                st.session_state["interview_prep"] = result
                st.success("Interview prep generated successfully!")
            except ConnectionError as e:
                st.error(f"Backend error: {e}")
            except ValueError as e:
                st.error(f"Analysis error: {e}")
            except Exception as e:
                st.error(f"Unexpected error: {e}")

    # ============================================================
    # Display Results
    # ============================================================
    prep = st.session_state.get("interview_prep")
    if not prep:
        st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)
        st.markdown('''
        <div class="talvex-card" style="text-align:center;padding:40px 20px;">
            <div style="font-size:48px;margin-bottom:12px;">🎯</div>
            <div style="font-size:14px;color:#9CA3AF;">Select an application and click "Generate Interview Prep" to get started.</div>
        </div>
        ''', unsafe_allow_html=True)
        return

    questions = prep.get("questions", [])
    general_tips = prep.get("generalTips", prep.get("general_tips", []))

    # ============================================================
    # Questions Section
    # ============================================================
    st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)
    st.markdown(f'<div class="section-header">Interview Questions ({len(questions)})</div>', unsafe_allow_html=True)

    # Group by category
    categories = {}
    for q in questions:
        cat = q.get("category", "General")
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(q)

    tab_labels = list(categories.keys())
    if tab_labels:
        tabs = st.tabs(tab_labels)

        for tab, cat_name in zip(tabs, tab_labels):
            with tab:
                cat_questions = categories[cat_name]
                for i, q in enumerate(cat_questions):
                    question_text = q.get("question", "")
                    tip_text = q.get("tip", "")
                    category = q.get("category", "General")

                    # Category color
                    cat_colors = {
                        "Behavioral": ("#7C3AED", "#F5F3FF"),
                        "Technical": ("#2563EB", "#DBEAFE"),
                        "Role-Specific": ("#059669", "#D1FAE5"),
                    }
                    color, bg = cat_colors.get(category, ("#6B7280", "#F3F4F6"))

                    st.markdown(f'''
                    <div class="talvex-card" style="margin-bottom:10px;border-left:4px solid {color};">
                        <div style="display:flex;align-items:start;gap:12px;">
                            <div style="width:28px;height:28px;border-radius:50%;background:{bg};color:{color};display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:700;flex-shrink:0;">
                                {i+1}
                            </div>
                            <div style="flex:1;">
                                <div style="font-size:14px;font-weight:600;color:#111827;margin-bottom:4px;">{question_text}</div>
                                <div style="font-size:12px;color:#6B7280;background:#F9FAFB;padding:8px 10px;border-radius:6px;">
                                    💡 <b>Tip:</b> {tip_text}
                                </div>
                            </div>
                        </div>
                    </div>
                    ''', unsafe_allow_html=True)

    # ============================================================
    # General Tips Section
    # ============================================================
    if general_tips:
        st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)
        st.markdown(f'<div class="section-header">General Interview Tips ({len(general_tips)})</div>', unsafe_allow_html=True)

        st.markdown('<div class="talvex-card">', unsafe_allow_html=True)
        for tip in general_tips:
            st.markdown(f'''
            <div style="display:flex;align-items:start;gap:8px;padding:6px 0;border-bottom:1px solid #F3F4F6;">
                <span style="font-size:14px;flex-shrink:0;">✅</span>
                <span style="font-size:13px;color:#374151;">{tip}</span>
            </div>
            ''', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    # ============================================================
    # Job Description Reference (collapsible)
    # ============================================================
    st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)

    with st.expander("📄 Full Job Description Reference"):
        st.markdown(f'''
        <div class="talvex-card" style="max-height:400px;overflow-y:auto;">
            <div style="font-size:12px;color:#4B5563;line-height:1.6;white-space:pre-wrap;">{jd[:5000]}</div>
        </div>
        ''', unsafe_allow_html=True)
