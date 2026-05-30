"""
TALVEX - Resume Page
Upload, analyze, and manage resumes with ATS scoring and skill detection.
Includes job description match analysis section.
"""

import streamlit as st
import json
import os
from datetime import datetime

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.api_client import TALVEXClient


def _score_circle_html(score: float, size: int = 100) -> str:
    """Generate HTML for a circular score indicator."""
    if score >= 80:
        color = "#059669"
        bg = "#D1FAE5"
    elif score >= 60:
        color = "#D97706"
        bg = "#FEF3C7"
    else:
        color = "#DC2626"
        bg = "#FEE2E2"

    return f'''
    <div style="width:{size}px;height:{size}px;border-radius:50%;background:{bg};display:flex;flex-direction:column;align-items:center;justify-content:center;margin:0 auto;">
        <div style="font-size:{int(size*0.35)}px;font-weight:700;color:{color};line-height:1;">{score}</div>
        <div style="font-size:{int(size*0.13)}px;color:{color};opacity:0.7;">ATS Score</div>
    </div>
    '''


def _contact_info_html(contact_info: dict) -> str:
    """Format contact info as HTML."""
    if not contact_info:
        return '<span style="color:#9CA3AF;font-size:13px;">No contact info detected</span>'
    items = []
    icons = {
        "email": "📧",
        "phone": "📱",
        "linkedin": "💼",
        "github": "💻",
    }
    for key, value in contact_info.items():
        icon = icons.get(key, "📌")
        items.append(f'<div style="font-size:13px;margin:2px 0;"><span style="margin-right:6px;">{icon}</span>{value}</div>')
    return "".join(items)


def render():
    st.markdown('<div class="page-title">Resume</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-subtitle">Upload and analyze your resumes for ATS optimization</div>', unsafe_allow_html=True)
    st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)

    # Load applications for the selector
    try:
        applications = TALVEXClient.list_applications()
    except (ConnectionError, ValueError) as e:
        applications = []
        st.error(f"Could not load applications: {e}")

    # ============================================================
    # Upload Section
    # ============================================================
    st.markdown('<div class="section-header">Upload Resume</div>', unsafe_allow_html=True)

    upload_col1, upload_col2 = st.columns([2, 1])

    with upload_col1:
        uploaded_file = st.file_uploader(
            "Choose a resume file",
            type=["pdf", "docx", "txt"],
            help="Supported formats: PDF, DOCX, TXT",
        )

    with upload_col2:
        app_options = {}
        if applications:
            app_options = {
                f"{a.get('company', '')} - {a.get('roleTitle', '')}": a.get('id', '')
                for a in applications
            }

        if app_options:
            selected_app = st.selectbox(
                "Attach to Application",
                options=list(app_options.keys()),
                key="resume_app_select",
            )
        else:
            st.warning("Create an application first to attach a resume.")
            selected_app = None

    if uploaded_file and selected_app and app_options:
        app_id = app_options[selected_app]

        if st.button("📤 Upload & Analyze", type="primary", use_container_width=True):
            with st.spinner("Analyzing resume..."):
                try:
                    result = TALVEXClient.upload_resume(app_id, uploaded_file)
                    st.session_state["resume_analysis"] = result.get("analysis", {})
                    st.session_state["resume_upload"] = result.get("upload", {})
                    st.success("Resume uploaded and analyzed successfully!")
                    st.session_state.refresh_key += 1
                    st.rerun()
                except (ConnectionError, ValueError) as e:
                    st.error(f"Upload failed: {e}")
                except Exception as e:
                    st.error(f"An unexpected error occurred: {e}")

    # ============================================================
    # Analysis Results
    # ============================================================
    analysis = st.session_state.get("resume_analysis")
    upload_info = st.session_state.get("resume_upload")

    if analysis:
        st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)
        st.markdown('<div class="section-header">Analysis Results</div>', unsafe_allow_html=True)

        ats_score = analysis.get("atsScore", 0)
        word_count = analysis.get("wordCount", 0)
        detected_skills = analysis.get("detectedSkills", [])
        detected_sections = analysis.get("detectedSections", [])
        contact_info = analysis.get("contactInfo", {})
        issues = analysis.get("issues", [])
        recommendations = analysis.get("recommendations", [])

        # Score + Quick Stats
        col_score, col_stats = st.columns([1, 2])

        with col_score:
            st.markdown(_score_circle_html(ats_score, size=130), unsafe_allow_html=True)

        with col_stats:
            st.markdown('''
            <div class="talvex-card" style="margin-top:8px;">
            ''', unsafe_allow_html=True)
            stats_rows = [
                ("📄", "File Name", upload_info.get("fileName", "N/A") if upload_info else "N/A"),
                ("📊", "File Size", f"{upload_info.get('fileSize', 0) / 1024:.1f} KB" if upload_info else "N/A"),
                ("📝", "Word Count", str(word_count)),
                ("🔄", "Version", f"v{upload_info.get('version', 1)}" if upload_info else "v1"),
                ("🤖", "OCR Used", "Yes" if analysis.get("ocrUsed") else "No"),
            ]
            for icon, label, value in stats_rows:
                st.markdown(f'''
                <div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #F3F4F6;">
                    <span style="font-size:13px;color:#6B7280;">{icon} {label}</span>
                    <span style="font-size:13px;font-weight:500;color:#111827;">{value}</span>
                </div>
                ''', unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)

        # Detected Skills, Sections, Contact Info, Issues, Recommendations
        col_details1, col_details2 = st.columns(2)

        with col_details1:
            # Detected Skills
            st.markdown('<div class="talvex-card">', unsafe_allow_html=True)
            st.markdown('<div style="font-size:14px;font-weight:600;color:#374151;margin-bottom:10px;">🧠 Detected Skills</div>', unsafe_allow_html=True)
            if detected_skills:
                badges = " ".join(f'<span class="skill-badge">{s}</span>' for s in detected_skills[:20])
                st.markdown(f'<div style="display:flex;flex-wrap:wrap;gap:4px;">{badges}</div>', unsafe_allow_html=True)
            else:
                st.markdown('<span style="font-size:12px;color:#9CA3AF;">No skills detected</span>', unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

            st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

            # Detected Sections
            st.markdown('<div class="talvex-card">', unsafe_allow_html=True)
            st.markdown('<div style="font-size:14px;font-weight:600;color:#374151;margin-bottom:10px;">📑 Detected Sections</div>', unsafe_allow_html=True)
            if detected_sections:
                sections_html = "".join(
                    f'<div style="display:inline-flex;align-items:center;gap:4px;padding:4px 10px;margin:2px;border-radius:6px;background:#F3F4F6;font-size:12px;font-weight:500;color:#374151;">✓ {s}</div>'
                    for s in detected_sections
                )
                st.markdown(f'<div style="display:flex;flex-wrap:wrap;gap:2px;">{sections_html}</div>', unsafe_allow_html=True)
            else:
                st.markdown('<span style="font-size:12px;color:#9CA3AF;">No sections detected</span>', unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

        with col_details2:
            # Contact Info
            st.markdown('<div class="talvex-card">', unsafe_allow_html=True)
            st.markdown('<div style="font-size:14px;font-weight:600;color:#374151;margin-bottom:10px;">🪪 Contact Info</div>', unsafe_allow_html=True)
            st.markdown(_contact_info_html(contact_info), unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

            st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

            # Issues
            st.markdown('<div class="talvex-card">', unsafe_allow_html=True)
            st.markdown('<div style="font-size:14px;font-weight:600;color:#374151;margin-bottom:10px;">⚠️ Issues Found</div>', unsafe_allow_html=True)
            if issues:
                for issue in issues:
                    st.markdown(f'''
                    <div style="font-size:13px;color:#DC2626;padding:4px 0;border-bottom:1px solid #FEF2F2;">• {issue}</div>
                    ''', unsafe_allow_html=True)
            else:
                st.markdown('<span style="font-size:13px;color:#059669;">✅ No issues found!</span>', unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

        # Recommendations
        if recommendations:
            st.markdown('<div class="talvex-card">', unsafe_allow_html=True)
            st.markdown('<div style="font-size:14px;font-weight:600;color:#374151;margin-bottom:10px;">💡 Recommendations</div>', unsafe_allow_html=True)
            for rec in recommendations:
                st.markdown(f'''
                <div style="font-size:13px;color:#2563EB;padding:4px 0;border-bottom:1px solid #EFF6FF;">• {rec}</div>
                ''', unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

    # ============================================================
    # Match Analysis: Resume vs Job Description
    # ============================================================
    st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)
    st.markdown('<div class="section-header">Match Analysis</div>', unsafe_allow_html=True)

    if applications:
        # Select an application that has a job description
        apps_with_jd = [a for a in applications if a.get("jobDescription")]
        if apps_with_jd:
            match_options = {
                f"{a.get('company', '')} - {a.get('roleTitle', '')} (Score: {a.get('matchScore', 0)}%)": a
                for a in apps_with_jd
            }
            selected_match_label = st.selectbox(
                "Select Application to Analyze",
                options=list(match_options.keys()),
                key="match_analysis_select",
            )
            selected_match_app = match_options[selected_match_label]

            col_analyze_btn, col_tip = st.columns([1, 3])
            with col_analyze_btn:
                if st.button("🔍 Analyze Match", type="primary", use_container_width=True, key="analyze_match_btn"):
                    with st.spinner("Analyzing job description..."):
                        try:
                            jd_text = selected_match_app.get("jobDescription", "")
                            jd_analysis = TALVEXClient.analyze_jd(jd_text)
                            st.session_state["jd_analysis"] = jd_analysis
                            st.session_state["jd_analysis_app"] = selected_match_app
                            st.success("Job description analyzed successfully!")
                        except ConnectionError as e:
                            st.error(f"Backend error: {e}")
                        except ValueError as e:
                            st.error(f"Analysis error: {e}")
                        except Exception as e:
                            st.error(f"Unexpected error: {e}")

            # Show existing match score info
            with col_tip:
                match_score = selected_match_app.get("matchScore", 0)
                ats_score = selected_match_app.get("atsScore", 0)
                keywords = selected_match_app.get("extractedKeywords", "[]")
                try:
                    kw_list = json.loads(keywords) if isinstance(keywords, str) else keywords
                except (json.JSONDecodeError, TypeError):
                    kw_list = []
                st.markdown(f'''
                <div style="font-size:12px;color:#6B7280;padding-top:8px;">
                    Current Match Score: <b style="color:{'#059669' if match_score >= 70 else '#D97706' if match_score >= 40 else '#DC2626'};">{match_score}%</b>
                    &nbsp;|&nbsp; ATS Score: <b>{ats_score}%</b>
                    &nbsp;|&nbsp; Keywords Extracted: <b>{len(kw_list)}</b>
                </div>
                ''', unsafe_allow_html=True)

        # Show analysis results
        jd_analysis = st.session_state.get("jd_analysis")
        jd_app = st.session_state.get("jd_analysis_app")

        if jd_analysis and jd_app:
            st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

            col_jd1, col_jd2 = st.columns(2)

            with col_jd1:
                st.markdown('<div class="talvex-card">', unsafe_allow_html=True)
                st.markdown('<div style="font-size:14px;font-weight:600;color:#374151;margin-bottom:10px;">🧩 Required Skills</div>', unsafe_allow_html=True)

                required_skills = jd_analysis.get("requiredSkills", [])
                if required_skills:
                    badges = " ".join(f'<span class="skill-badge">{s}</span>' for s in required_skills[:20])
                    st.markdown(f'<div style="display:flex;flex-wrap:wrap;gap:4px;">{badges}</div>', unsafe_allow_html=True)
                else:
                    st.markdown('<span style="font-size:12px;color:#9CA3AF;">No skills extracted</span>', unsafe_allow_html=True)

                st.markdown("</div>", unsafe_allow_html=True)

                st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

                # Experience Level & Work Mode
                st.markdown('<div class="talvex-card">', unsafe_allow_html=True)
                st.markdown('<div style="font-size:14px;font-weight:600;color:#374151;margin-bottom:10px;">📋 Job Profile</div>', unsafe_allow_html=True)

                exp_level = jd_analysis.get("experienceLevel", "Not Specified")
                work_mode = jd_analysis.get("workMode", "Not Specified")

                st.markdown(f'''
                <div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #F3F4F6;">
                    <span style="font-size:13px;color:#6B7280;">📊 Experience Level</span>
                    <span style="font-size:13px;font-weight:500;color:#111827;">{exp_level}</span>
                </div>
                <div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #F3F4F6;">
                    <span style="font-size:13px;color:#6B7280;">🏠 Work Mode</span>
                    <span style="font-size:13px;font-weight:500;color:#111827;">{work_mode}</span>
                </div>
                ''', unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)

            with col_jd2:
                # Perks
                st.markdown('<div class="talvex-card">', unsafe_allow_html=True)
                st.markdown('<div style="font-size:14px;font-weight:600;color:#374151;margin-bottom:10px;">🎁 Perks & Benefits</div>', unsafe_allow_html=True)

                perks = jd_analysis.get("perks", [])
                if perks:
                    for perk in perks:
                        st.markdown(f'''
                        <div style="font-size:13px;color:#059669;padding:4px 0;border-bottom:1px solid #F0FDF4;">✓ {perk}</div>
                        ''', unsafe_allow_html=True)
                else:
                    st.markdown('<span style="font-size:12px;color:#9CA3AF;">No perks detected from description</span>', unsafe_allow_html=True)

                st.markdown("</div>", unsafe_allow_html=True)

                st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

                # Persona Skills Comparison
                persona = jd_app.get("persona")
                if persona:
                    try:
                        persona_skills = json.loads(persona.get("skillsJson", "[]"))
                    except (json.JSONDecodeError, TypeError):
                        persona_skills = []

                    if persona_skills and required_skills:
                        persona_set = set(s.lower() for s in persona_skills)
                        jd_set = set(s.lower() for s in required_skills)
                        matched = persona_set & jd_set
                        missing = jd_set - persona_set

                        st.markdown('<div class="talvex-card">', unsafe_allow_html=True)
                        st.markdown(f'<div style="font-size:14px;font-weight:600;color:#374151;margin-bottom:10px;">👤 Skill Gap vs {persona.get("name", "Persona")}</div>', unsafe_allow_html=True)

                        st.markdown(f'<div style="font-size:12px;color:#059669;margin-bottom:4px;">✅ Matched ({len(matched)}):</div>', unsafe_allow_html=True)
                        if matched:
                            m_badges = " ".join(f'<span class="skill-badge">{s}</span>' for s in sorted(matched)[:15])
                            st.markdown(f'<div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:8px;">{m_badges}</div>', unsafe_allow_html=True)

                        st.markdown(f'<div style="font-size:12px;color:#DC2626;margin-bottom:4px;">❌ Missing ({len(missing)}):</div>', unsafe_allow_html=True)
                        if missing:
                            miss_badges = " ".join(f'<span style="display:inline-flex;align-items:center;padding:2px 10px;border-radius:9999px;font-size:12px;font-weight:500;background:#FEE2E2;color:#DC2626;margin:2px;">{s}</span>' for s in sorted(missing)[:15])
                            st.markdown(f'<div style="display:flex;flex-wrap:wrap;gap:4px;">{miss_badges}</div>', unsafe_allow_html=True)

                        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info("Create an application with a job description to use match analysis.")

    # ============================================================
    # Version History
    # ============================================================
    if applications and selected_app and app_options:
        st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)
        st.markdown('<div class="section-header">Version History</div>', unsafe_allow_html=True)

        app_id = app_options[selected_app]
        try:
            versions = TALVEXClient.get_resume_versions(app_id)
        except (ConnectionError, ValueError):
            versions = []

        if versions:
            import pandas as pd
            version_rows = []
            for v in versions:
                created = v.get("createdAt", "")
                if created:
                    try:
                        dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                        created_str = dt.strftime("%Y-%m-%d %H:%M")
                    except (ValueError, AttributeError):
                        created_str = created
                else:
                    created_str = "N/A"
                version_rows.append({
                    "Version": f"v{v.get('version', 1)}",
                    "Hash": v.get("contentHash", "")[:12] + "...",
                    "Uploaded": created_str,
                })
            df = pd.DataFrame(version_rows)
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.markdown('<div style="font-size:13px;color:#9CA3AF;padding:12px;">No resume versions uploaded for this application.</div>', unsafe_allow_html=True)
