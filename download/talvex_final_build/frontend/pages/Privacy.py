"""
TALVEX - Privacy Page
Canary email monitoring and data leak detection.
"""

import streamlit as st
import json
from datetime import datetime

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.api_client import TALVEXClient


def _privacy_status_badge(status: str) -> str:
    """Generate a privacy status badge."""
    s = status.lower() if status else "clean"
    if s == "clean":
        color, bg = "#059669", "#D1FAE5"
        label = "Clean"
    elif s == "leaked":
        color, bg = "#DC2626", "#FEE2E2"
        label = "Leaked"
    elif s == "monitoring":
        color, bg = "#D97706", "#FEF3C7"
        label = "Monitoring"
    else:
        color, bg = "#6B7280", "#F3F4F6"
        label = status.title() if status else "Unknown"
    return f'<span style="display:inline-block;padding:3px 12px;border-radius:9999px;font-size:12px;font-weight:600;background:{bg};color:{color};">{label}</span>'


def render():
    st.markdown('<div class="page-title">Privacy & Canary Monitoring</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-subtitle">Track data leak detection with canary emails for each application</div>', unsafe_allow_html=True)
    st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)

    # Load data
    try:
        canaries = TALVEXClient.list_canaries()
        applications = TALVEXClient.list_applications()
    except (ConnectionError, ValueError) as e:
        st.error(f"Could not load privacy data: {e}")
        return

    # Build app lookup
    app_lookup = {a["id"]: a for a in applications}

    # Stats
    total_canaries = len(canaries) if isinstance(canaries, list) else 0
    leaked = [c for c in canaries if c.get("leakFlagged")] if isinstance(canaries, list) else []
    monitoring = [c for c in canaries if not c.get("leakFlagged")] if isinstance(canaries, list) else []

    # Stats row
    stats_html = f'''
    <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px;">
        <div class="stat-card">
            <div style="font-size:24px;margin-bottom:6px;">🛡️</div>
            <div class="stat-value" style="color:#7C3AED;">{total_canaries}</div>
            <div class="stat-label">Active Canaries</div>
        </div>
        <div class="stat-card">
            <div style="font-size:24px;margin-bottom:6px;">🟢</div>
            <div class="stat-value" style="color:#059669;">{len(monitoring)}</div>
            <div class="stat-label">Monitoring</div>
        </div>
        <div class="stat-card">
            <div style="font-size:24px;margin-bottom:6px;">🔴</div>
            <div class="stat-value" style="color:#DC2626;">{len(leaked)}</div>
            <div class="stat-label">Leaked</div>
        </div>
    </div>
    '''
    st.markdown(stats_html, unsafe_allow_html=True)
    st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)

    # ============================================================
    # Leak Alerts (highlighted)
    # ============================================================
    if leaked:
        st.markdown('<div class="talvex-alert talvex-alert-error" style="font-size:14px;font-weight:600;">🚨 Leak Detected — {len(leaked)} canary email{"s" if len(leaked) != 1 else ""} triggered!</div>'.format(len(leaked)), unsafe_allow_html=True)
        st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)

        for canary in leaked:
            app = app_lookup.get(canary.get("appId", ""), {})
            company = app.get("company", "Unknown") if app else "Unknown"
            role = app.get("roleTitle", "") if app else ""
            email = canary.get("canaryEmail", "")
            details = canary.get("leakDetails", "No details provided")

            st.markdown(f'''
            <div style="background:#FEF2F2;border:1px solid #FECACA;border-radius:10px;padding:16px;margin-bottom:10px;">
                <div style="display:flex;align-items:center;justify-content:space-between;">
                    <div style="font-size:15px;font-weight:600;color:#991B1B;">{company} {role}</div>
                    <span style="font-size:11px;font-weight:500;color:#DC2626;background:#FEE2E2;padding:2px 8px;border-radius:4px;">LEAKED</span>
                </div>
                <div style="font-size:12px;color:#7F1D1D;margin-top:4px;">📧 {email}</div>
                <div style="font-size:13px;color:#92400E;margin-top:6px;">{details}</div>
            </div>
            ''', unsafe_allow_html=True)

        st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)

    # ============================================================
    # Create Canary
    # ============================================================
    st.markdown('<div class="section-header">Create Canary</div>', unsafe_allow_html=True)

    with st.form("create_canary_form"):
        if applications:
            app_options = {f"{a.get('company', '')} - {a.get('roleTitle', '')} ({a.get('status', '')})": a.get('id', '') for a in applications}

            # Filter out apps that already have canaries
            existing_app_ids = {c.get("appId") for c in canaries} if isinstance(canaries, list) else set()
            available_apps = {k: v for k, v in app_options.items() if v not in existing_app_ids}

            if available_apps:
                selected_app = st.selectbox("Select Application", options=list(available_apps.keys()))
                canary_email = st.text_input("Canary Email (optional)", placeholder="Leave blank to auto-generate", help="A unique email address for leak detection")
                canary_slug = st.text_input("Tracking Slug (optional)", placeholder="Auto-generated if blank")

                if st.form_submit_button("Create Canary", type="primary", use_container_width=True):
                    app_id = available_apps[selected_app]
                    email_val = canary_email.strip() if canary_email.strip() else f"talvex.canary.{app_id[:8]}@example.com"
                    slug_val = canary_slug.strip() if canary_slug.strip() else None

                    with st.spinner("Creating canary..."):
                        try:
                            result = TALVEXClient.create_canary({
                                "appId": app_id,
                                "canaryEmail": email_val,
                                "trackingSlug": slug_val,
                            })
                            st.success(f"Canary created for {selected_app}")
                            st.session_state.refresh_key += 1
                            st.rerun()
                        except (ConnectionError, ValueError) as e:
                            st.error(str(e))
            else:
                st.info("All applications already have canary monitoring.")
        else:
            st.info("No applications available. Create applications first.")

    st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)

    # ============================================================
    # Active Canaries Table
    # ============================================================
    st.markdown('<div class="section-header">All Canaries</div>', unsafe_allow_html=True)

    if isinstance(canaries, list) and canaries:
        rows_html = ""
        for canary in canaries:
            app = app_lookup.get(canary.get("appId", ""), {})
            company = app.get("company", "Unknown") if app else "Unknown"
            role = app.get("roleTitle", "") if app else ""
            email = canary.get("canaryEmail", "")
            flagged = canary.get("leakFlagged", False)
            created = canary.get("createdAt", "")

            if created:
                try:
                    dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    created_str = dt.strftime("%Y-%m-%d %H:%M")
                except (ValueError, AttributeError):
                    created_str = str(created)[:16]
            else:
                created_str = "N/A"

            status_label = "🟢 Monitoring" if not flagged else "🔴 Leaked"
            bg_color = "#FFFFFF" if not flagged else "#FEF2F2"
            border_color = "#E5E7EB" if not flagged else "#FECACA"

            canary_id = canary.get("id", "")

            rows_html += f'''
            <div style="background:{bg_color};border:1px solid {border_color};border-radius:8px;padding:12px 16px;margin-bottom:6px;">
                <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;">
                    <div style="flex:1;min-width:0;">
                        <div style="font-size:14px;font-weight:600;color:#111827;">{company} {role}</div>
                        <div style="font-size:12px;color:#6B7280;margin-top:2px;">📧 {email}</div>
                        <div style="font-size:11px;color:#9CA3AF;margin-top:2px;">Created: {created_str}</div>
                    </div>
                    <div style="display:flex;align-items:center;gap:8px;flex-shrink:0;">
                        {status_label}
                    </div>
                </div>
            </div>
            '''

            # Flag button (only for non-flagged)
            if not flagged:
                cols_flag = st.columns([3, 1])
                with cols_flag[1]:
                    if st.button("🚩 Flag as Leaked", key=f"flag_{canary_id}", use_container_width=True):
                        with st.spinner("Flagging..."):
                            try:
                                TALVEXClient.flag_canary(canary_id, {
                                    "leakFlagged": True,
                                    "leakDetails": "Manually flagged as leaked by user.",
                                })
                                st.warning("Canary flagged as leaked!")
                                st.session_state.refresh_key += 1
                                st.rerun()
                            except (ConnectionError, ValueError) as e:
                                st.error(str(e))

        st.markdown(rows_html, unsafe_allow_html=True)
    else:
        st.markdown('''
        <div class="talvex-card" style="text-align:center;padding:40px 20px;">
            <div style="font-size:48px;margin-bottom:12px;">🛡️</div>
            <div style="font-size:14px;color:#9CA3AF;">No canary emails set up yet. Create one for an application to start monitoring.</div>
        </div>
        ''', unsafe_allow_html=True)
