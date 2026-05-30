"""
TALVEX - Job Search Page
Search jobs via RapidAPI JSearch and ingest them into the pipeline.
"""

import streamlit as st
import json

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.api_client import TALVEXClient


COUNTRY_OPTIONS = {
    "United States": "us",
    "India": "in",
    "United Kingdom": "uk",
    "Canada": "ca",
    "Germany": "de",
    "Australia": "au",
    "Singapore": "sg",
    "UAE": "ae",
}

DATE_POSTED_OPTIONS = {
    "All Time": None,
    "Past 24 Hours": "24h",
    "Past 3 Days": "3d",
    "Past Week": "7d",
    "Past Month": "30d",
}


def _salary_display(salary_min, salary_max, currency):
    """Format salary range for display."""
    if not salary_min and not salary_max:
        return "Not Disclosed"
    cur = currency.upper() if currency else "USD"
    if cur == "INR":
        def fmt(v):
            if v is None:
                return ""
            if v >= 100000:
                return f"{v/100000:.1f}L"
            return f"{v/1000:.0f}K"
        min_s = fmt(salary_min)
        max_s = fmt(salary_max)
    else:
        def fmt(v):
            if v is None:
                return ""
            if v >= 1000000:
                return f"${v/1000000:.1f}M"
            return f"${v/1000:.0f}K"
        min_s = fmt(salary_min)
        max_s = fmt(salary_max)
    if min_s and max_s:
        return f"{min_s} - {max_s} {cur}"
    elif max_s:
        return f"Up to {max_s} {cur}"
    elif min_s:
        return f"From {min_s} {cur}"
    return "Not Disclosed"


def _work_mode_badge(work_mode):
    """Generate work mode badge HTML."""
    if not work_mode:
        return ""
    wm = work_mode.lower()
    if wm == "remote":
        color, bg = "#059669", "#D1FAE5"
    elif wm == "onsite":
        color, bg = "#2563EB", "#DBEAFE"
    else:
        color, bg = "#D97706", "#FEF3C7"
    return f'<span style="display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:500;background:{bg};color:{color};">{work_mode.title()}</span>'


def render():
    st.markdown('<div class="page-title">Job Search</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-subtitle">Search and discover jobs from across the web</div>', unsafe_allow_html=True)
    st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)

    # Load personas for ingestion
    try:
        personas = TALVEXClient.list_personas()
    except (ConnectionError, ValueError):
        personas = []

    # ============================================================
    # Search Bar
    # ============================================================
    search_col1, search_col2, search_col3 = st.columns([3, 1, 1])

    with search_col1:
        query = st.text_input(
            "Job Title / Keywords",
            placeholder="e.g., Full Stack Developer, Data Scientist...",
            label_visibility="collapsed",
        )

    with search_col2:
        country_label = st.selectbox(
            "Country",
            options=list(COUNTRY_OPTIONS.keys()),
            index=0,
            label_visibility="collapsed",
        )

    with search_col3:
        date_label = st.selectbox(
            "Date Posted",
            options=list(DATE_POSTED_OPTIONS.keys()),
            index=0,
            label_visibility="collapsed",
        )

    # Search button
    search_clicked = st.button("🔍  Search Jobs", type="primary", use_container_width=True)

    # Perform search
    if search_clicked and query:
        country = COUNTRY_OPTIONS[country_label]
        date_posted = DATE_POSTED_OPTIONS[date_label]

        with st.spinner("Searching jobs..."):
            try:
                results = TALVEXClient.search_jobs(
                    query=query,
                    country=country,
                    num_pages=1,
                    date_posted=date_posted,
                )
                st.session_state["search_results"] = results
                st.session_state["search_results_page"] = 1
            except ConnectionError as e:
                st.error(f"Search failed: {e}")
                return
            except Exception as e:
                st.error(f"An error occurred: {e}")
                return
    elif search_clicked and not query:
        st.warning("Please enter a search query.")
        return

    # ============================================================
    # Search Results
    # ============================================================
    results = st.session_state.get("search_results")
    if results:
        jobs = results.get("results", [])
        total_count = results.get("totalCount", 0)
        page_num = results.get("pageNumber", 1)

        st.markdown(f'<div style="font-size:14px;color:#6B7280;margin-bottom:16px;">Showing {len(jobs)} of {total_count:,} results</div>', unsafe_allow_html=True)

        if jobs:
            # Display jobs as cards in a grid
            cols = st.columns(2)
            for i, job in enumerate(jobs):
                col = cols[i % 2]

                job_title = job.get("job_title", "Unknown Title")
                employer = job.get("employer_name", "Unknown Company")
                location_parts = [
                    job.get("job_city", ""),
                    job.get("job_state", ""),
                    job.get("job_country", ""),
                ]
                location = ", ".join(p for p in location_parts if p) or "Remote"
                salary_min = job.get("job_min_salary")
                salary_max = job.get("job_max_salary")
                salary_currency = job.get("job_salary_currency", "USD")
                apply_link = job.get("job_apply_link", "")
                employment_type = job.get("job_employment_type", "")
                is_remote = job.get("job_is_remote")
                job_desc = job.get("job_description", "")
                employer_logo = job.get("employer_logo", "")
                job_id = job.get("job_id", "")
                posted_date = job.get("job_posted_at_datetime_utc", "")

                work_mode = "Remote" if is_remote else "Onsite"
                salary_str = _salary_display(salary_min, salary_max, salary_currency)

                with col:
                    st.markdown(f'''
                    <div class="talvex-card" style="margin-bottom:12px;">
                        <div style="display:flex;align-items:start;justify-content:space-between;gap:12px;">
                            <div style="flex:1;min-width:0;">
                                <div style="font-size:15px;font-weight:600;color:#111827;margin-bottom:4px;">{job_title}</div>
                                <div style="font-size:13px;color:#6B7280;">{employer}</div>
                            </div>
                        </div>
                        <div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:8px;">
                            <span style="font-size:12px;color:#374151;">📍 {location}</span>
                            {_work_mode_badge(work_mode)}
                            <span style="font-size:12px;color:#6B7280;">💰 {salary_str}</span>
                            {"<span style='font-size:12px;color:#6B7280;'>💼 " + employment_type.title() + "</span>" if employment_type else ""}
                        </div>
                    </div>
                    ''', unsafe_allow_html=True)

                    # Ingest button
                    if personas:
                        selected_persona = st.selectbox(
                            "Persona",
                            options=[p["id"] for p in personas],
                            format_func=lambda pid: next((p["name"] for p in personas if p["id"] == pid), "Select"),
                            key=f"persona_{job_id}_{i}",
                            label_visibility="collapsed",
                        )
                        btn_cols = st.columns([1, 1])
                        with btn_cols[0]:
                            if st.button("📥 Ingest", key=f"ingest_{job_id}_{i}", use_container_width=True, type="primary"):
                                with st.spinner("Ingesting job..."):
                                    try:
                                        persona = next((p for p in personas if p["id"] == selected_persona), None)
                                        skills_json = persona["skillsJson"] if persona else "[]"
                                        ingest_data = {
                                            "personaId": selected_persona,
                                            "company": employer,
                                            "roleTitle": job_title,
                                            "jobDescription": job_desc[:5000] if job_desc else f"{job_title} at {employer}",
                                            "jobUrl": apply_link,
                                            "platform": "manual",
                                            "location": location,
                                            "salaryMin": int(salary_min) if salary_min else None,
                                            "salaryMax": int(salary_max) if salary_max else None,
                                            "salaryCurrency": salary_currency,
                                            "workMode": work_mode.lower(),
                                        }
                                        result = TALVEXClient.ingest_job(ingest_data)
                                        st.success(f"Ingested: {employer} - {job_title}")
                                        st.session_state.refresh_key += 1
                                    except (ConnectionError, ValueError) as e:
                                        st.error(f"Ingest failed: {e}")
                        with btn_cols[1]:
                            if apply_link:
                                st.markdown(f'<a href="{apply_link}" target="_blank" class="talvex-btn talvex-btn-secondary" style="text-decoration:none;display:block;text-align:center;padding:8px 16px;border-radius:8px;font-size:14px;font-weight:500;">🔗 Apply</a>', unsafe_allow_html=True)
                    else:
                        st.warning("Create a persona first to ingest jobs.")

                    st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)

            # Pagination
            st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)
            page_col1, page_col2, page_col3 = st.columns([1, 1, 1])
            with page_col1:
                if page_num > 1:
                    if st.button("← Previous Page", use_container_width=True):
                        with st.spinner("Loading previous page..."):
                            try:
                                results = TALVEXClient.search_jobs(
                                    query=query,
                                    country=COUNTRY_OPTIONS[country_label],
                                    num_pages=page_num - 1,
                                    date_posted=DATE_POSTED_OPTIONS[date_label],
                                )
                                st.session_state["search_results"] = results
                                st.rerun()
                            except ConnectionError as e:
                                st.error(f"Failed: {e}")
            with page_col2:
                st.markdown(f'<div style="text-align:center;padding-top:8px;font-size:13px;color:#6B7280;">Page {page_num}</div>', unsafe_allow_html=True)
            with page_col3:
                if len(jobs) >= 10:
                    if st.button("Next Page →", use_container_width=True):
                        with st.spinner("Loading next page..."):
                            try:
                                results = TALVEXClient.search_jobs(
                                    query=query,
                                    country=COUNTRY_OPTIONS[country_label],
                                    num_pages=page_num + 1,
                                    date_posted=DATE_POSTED_OPTIONS[date_label],
                                )
                                st.session_state["search_results"] = results
                                st.rerun()
                            except ConnectionError as e:
                                st.error(f"Failed: {e}")
        else:
            st.markdown('<div class="empty-state"><div class="empty-state-icon">🔍</div><div class="empty-state-text">No jobs found. Try different keywords or filters.</div></div>', unsafe_allow_html=True)

    else:
        # Empty state - no search yet
        st.markdown('''
        <div class="talvex-card" style="text-align:center;padding:60px 20px;">
            <div style="font-size:56px;margin-bottom:16px;">🔍</div>
            <div style="font-size:18px;font-weight:600;color:#111827;margin-bottom:8px;">Search for Jobs</div>
            <div style="font-size:14px;color:#6B7280;max-width:400px;margin:0 auto;">
                Enter a job title, keywords, or company name to discover opportunities across multiple job platforms.
            </div>
            <div style="margin-top:20px;display:flex;flex-wrap:wrap;justify-content:center;gap:8px;">
                <span class="skill-badge">Full Stack Developer</span>
                <span class="skill-badge">Data Scientist</span>
                <span class="skill-badge">Product Manager</span>
                <span class="skill-badge">UX Designer</span>
                <span class="skill-badge">DevOps Engineer</span>
            </div>
        </div>
        ''', unsafe_allow_html=True)
