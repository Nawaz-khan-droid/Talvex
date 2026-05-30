"""
TALVEX - Personas Page
Manage job personas with skills, master bullets, and application counts.
"""

import streamlit as st
import json

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.api_client import TALVEXClient


def _skill_badges(skills_json_str: str) -> str:
    """Generate HTML skill badges from a JSON string of skills."""
    try:
        skills = json.loads(skills_json_str) if skills_json_str else []
    except (json.JSONDecodeError, TypeError):
        skills = []
    if not skills:
        return '<span style="font-size:12px;color:#9CA3AF;">No skills defined</span>'
    return " ".join(f'<span class="skill-badge">{s}</span>' for s in skills[:15])


def render():
    st.markdown('<div class="page-title">Personas</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-subtitle">Manage your professional identities for tailored job applications</div>', unsafe_allow_html=True)
    st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)

    # Load personas
    try:
        personas = TALVEXClient.list_personas()
    except (ConnectionError, ValueError) as e:
        st.error(f"Could not load personas: {e}")
        return

    # ============================================================
    # Create Persona Section
    # ============================================================
    with st.expander("➕ Create New Persona", expanded=False):
        create_name = st.text_input("Persona Name", placeholder="e.g., Full Stack Developer", key="create_persona_name")
        create_skills_raw = st.text_area(
            "Skills (comma-separated)",
            placeholder="Python, JavaScript, React, Node.js, PostgreSQL...",
            key="create_persona_skills",
            height=80,
        )
        create_bullets = st.text_area(
            "Master Bullets (one per line)",
            placeholder="Built scalable microservices handling 1M+ requests/day\nLed a team of 5 engineers to deliver a React dashboard\nDesigned REST APIs consumed by 50+ internal clients...",
            key="create_persona_bullets",
            height=120,
        )

        create_col1, create_col2 = st.columns([1, 4])
        with create_col1:
            create_btn = st.button("Create Persona", type="primary", use_container_width=True, key="create_persona_btn")

        if create_btn:
            if not create_name.strip():
                st.warning("Please enter a persona name.")
            else:
                skills_list = [s.strip() for s in create_skills_raw.split(",") if s.strip()]
                skills_json = json.dumps(skills_list)
                bullets = create_bullets.strip()

                with st.spinner("Creating persona..."):
                    try:
                        result = TALVEXClient.create_persona({
                            "name": create_name.strip(),
                            "skillsJson": skills_json,
                            "masterBullets": bullets if bullets else "No bullets defined yet.",
                        })
                        st.success(f"Persona '{create_name.strip()}' created successfully!")
                        st.session_state.refresh_key += 1
                        st.rerun()
                    except (ConnectionError, ValueError) as e:
                        st.error(f"Failed to create persona: {e}")

    st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)

    # ============================================================
    # Persona Cards
    # ============================================================
    if personas:
        cols = st.columns(min(len(personas), 3))
        for i, persona in enumerate(personas):
            col = cols[i % len(cols)]
            with col:
                persona_id = persona.get("id", "")
                name = persona.get("name", "Unnamed")
                skills_json = persona.get("skillsJson", "[]")
                app_count = persona.get("applicationCount", 0)
                master_bullets = persona.get("masterBullets", "")

                try:
                    skills_list = json.loads(skills_json) if skills_json else []
                    skill_count = len(skills_list)
                except (json.JSONDecodeError, TypeError):
                    skills_list = []
                    skill_count = 0

                st.markdown(f'''
                <div class="talvex-card">
                    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;">
                        <div style="font-size:16px;font-weight:600;color:#111827;">{name}</div>
                        <span style="font-size:12px;color:#7C3AED;font-weight:600;background:#F5F3FF;padding:2px 8px;border-radius:9999px;">{app_count} App{"s" if app_count != 1 else ""}</span>
                    </div>
                    <div style="font-size:12px;color:#6B7280;margin-bottom:8px;">{skill_count} Skills</div>
                    <div style="display:flex;flex-wrap:wrap;gap:2px;margin-bottom:10px;">
                        {_skill_badges(skills_json)}
                    </div>
                </div>
                ''', unsafe_allow_html=True)

                # Edit / Delete buttons
                btn_col1, btn_col2 = st.columns(2)
                with btn_col1:
                    if st.button("✏️ Edit", key=f"edit_persona_{persona_id}", use_container_width=True):
                        st.session_state[f"editing_{persona_id}"] = True
                        st.rerun()

                with btn_col2:
                    if st.button("🗑️ Delete", key=f"delete_persona_{persona_id}", use_container_width=True):
                        st.session_state[f"confirm_delete_{persona_id}"] = True

                # Confirm delete
                if st.session_state.get(f"confirm_delete_{persona_id}", False):
                    st.warning(f"⚠️ Delete '{name}'? This is permanent if no applications are linked.")
                    del_col1, del_col2 = st.columns(2)
                    with del_col1:
                        if st.button("Yes, Delete", key=f"confirm_del_yes_{persona_id}", use_container_width=True):
                            with st.spinner("Deleting..."):
                                try:
                                    TALVEXClient.delete_persona(persona_id)
                                    st.success(f"Persona '{name}' deleted.")
                                    st.session_state.refresh_key += 1
                                    st.rerun()
                                except (ConnectionError, ValueError) as e:
                                    st.error(str(e))
                    with del_col2:
                        if st.button("Cancel", key=f"confirm_del_no_{persona_id}", use_container_width=True):
                            st.session_state[f"confirm_delete_{persona_id}"] = False
                            st.rerun()

                # Inline edit
                if st.session_state.get(f"editing_{persona_id}", False):
                    st.markdown("<div class='talvex-divider'></div>", unsafe_allow_html=True)
                    st.markdown('<div style="font-size:13px;font-weight:600;color:#374151;margin-bottom:8px;">Edit Persona</div>', unsafe_allow_html=True)

                    edit_name = st.text_input("Name", value=name, key=f"edit_name_{persona_id}")
                    edit_skills = st.text_area("Skills (comma-separated)", value=", ".join(skills_list), key=f"edit_skills_{persona_id}", height=60)
                    edit_bullets = st.text_area("Master Bullets", value=master_bullets, key=f"edit_bullets_{persona_id}", height=80)

                    edit_col1, edit_col2 = st.columns(2)
                    with edit_col1:
                        if st.button("Save", key=f"save_persona_{persona_id}", type="primary", use_container_width=True):
                            new_skills = [s.strip() for s in edit_skills.split(",") if s.strip()]
                            with st.spinner("Saving..."):
                                try:
                                    TALVEXClient.update_persona(persona_id, {
                                        "name": edit_name,
                                        "skillsJson": json.dumps(new_skills),
                                        "masterBullets": edit_bullets,
                                    })
                                    st.success("Persona updated!")
                                    st.session_state[f"editing_{persona_id}"] = False
                                    st.session_state.refresh_key += 1
                                    st.rerun()
                                except (ConnectionError, ValueError) as e:
                                    st.error(str(e))
                    with edit_col2:
                        if st.button("Cancel", key=f"cancel_edit_{persona_id}", use_container_width=True):
                            st.session_state[f"editing_{persona_id}"] = False
                            st.rerun()

                st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
    else:
        st.markdown('''
        <div class="talvex-card" style="text-align:center;padding:60px 20px;">
            <div style="font-size:56px;margin-bottom:16px;">👤</div>
            <div style="font-size:18px;font-weight:600;color:#111827;margin-bottom:8px;">No Personas Yet</div>
            <div style="font-size:14px;color:#6B7280;max-width:400px;margin:0 auto;">
                Create personas to represent different professional identities. Each persona has its own skills, experience bullets, and match scoring.
            </div>
        </div>
        ''', unsafe_allow_html=True)
