"""
TALVEX - Job Application Command Center
Streamlit Frontend - Main Entry Point
"""

import streamlit as st

st.set_page_config(
    page_title="TALVEX",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# Custom CSS
# ============================================================

CUSTOM_CSS = """
<style>
    /* === Font & Base === */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    html, body, [class*="st-"] {
        font-family: 'Inter', system-ui, -apple-system, sans-serif !important;
    }

    /* === Primary Colors === */
    :root {
        --primary: #7C3AED;
        --primary-light: #A78BFA;
        --primary-dark: #6D28D9;
        --primary-bg: #F5F3FF;
        --primary-border: #DDD6FE;
    }

    /* === Hide default Streamlit branding === */
    #MainMenu, footer, header { visibility: hidden; }
    #MainMenu { height: 0px; }
    footer { height: 0px; }

    /* === Sidebar Styling === */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #7C3AED 0%, #5B21B6 100%) !important;
        width: 260px !important;
    }
    section[data-testid="stSidebar"] * {
        color: #FFFFFF !important;
    }
    section[data-testid="stSidebar"] .stMarkdown {
        color: #FFFFFF !important;
    }
    section[data-testid="stSidebar"] a {
        color: #E0D5F5 !important;
        text-decoration: none !important;
        transition: all 0.2s ease;
    }
    section[data-testid="stSidebar"] a:hover {
        color: #FFFFFF !important;
        background: rgba(255,255,255,0.15) !important;
        border-radius: 8px;
    }
    section[data-testid="stSidebar"] .stRadio > div {
        background: transparent !important;
        border: none !important;
    }
    section[data-testid="stSidebar"] .stRadio label {
        padding: 10px 14px !important;
        border-radius: 8px !important;
        margin: 2px 0 !important;
        font-weight: 500 !important;
        font-size: 14px !important;
        transition: all 0.2s ease;
        background: transparent !important;
    }
    section[data-testid="stSidebar"] .stRadio label[data-checked="true"] {
        background: rgba(255,255,255,0.2) !important;
        box-shadow: 0 0 0 1px rgba(255,255,255,0.3) !important;
    }
    section[data-testid="stSidebar"] .stRadio label:hover {
        background: rgba(255,255,255,0.1) !important;
    }

    /* === Card Styles === */
    .talvex-card {
        background: #FFFFFF;
        border: 1px solid #E5E7EB;
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.06);
        transition: box-shadow 0.2s ease;
    }
    .talvex-card:hover {
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    }

    /* === Stat Cards === */
    .stat-card {
        background: #FFFFFF;
        border: 1px solid #E5E7EB;
        border-radius: 12px;
        padding: 20px 24px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        text-align: center;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .stat-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 24px rgba(0,0,0,0.08);
    }
    .stat-value {
        font-size: 32px;
        font-weight: 700;
        color: #7C3AED;
        line-height: 1.2;
    }
    .stat-label {
        font-size: 13px;
        font-weight: 500;
        color: #6B7280;
        margin-top: 4px;
        text-transform: none;
        letter-spacing: 0.01em;
    }

    /* === Page Title === */
    .page-title {
        font-size: 28px;
        font-weight: 700;
        color: #111827;
        margin-bottom: 4px;
    }
    .page-subtitle {
        font-size: 14px;
        color: #6B7280;
        font-weight: 400;
    }

    /* === Section Headers === */
    .section-header {
        font-size: 18px;
        font-weight: 600;
        color: #1F2937;
        padding-bottom: 10px;
        border-bottom: 2px solid #E5E7EB;
        margin-bottom: 16px;
    }

    /* === Status Badges === */
    .status-badge {
        display: inline-flex;
        align-items: center;
        padding: 3px 10px;
        border-radius: 9999px;
        font-size: 12px;
        font-weight: 600;
        letter-spacing: 0.02em;
    }

    /* === Platform Badges === */
    .platform-badge {
        display: inline-flex;
        align-items: center;
        gap: 5px;
        padding: 3px 10px;
        border-radius: 6px;
        font-size: 12px;
        font-weight: 500;
        color: #374151;
        background: #F3F4F6;
    }
    .platform-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        display: inline-block;
    }

    /* === Skill Badges === */
    .skill-badge {
        display: inline-flex;
        align-items: center;
        padding: 2px 10px;
        border-radius: 9999px;
        font-size: 12px;
        font-weight: 500;
        background: #EDE9FE;
        color: #6D28D9;
        margin: 2px;
    }

    /* === Action Buttons === */
    .talvex-btn {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 8px 16px;
        border-radius: 8px;
        font-size: 14px;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.2s ease;
        border: none;
        text-decoration: none;
    }
    .talvex-btn-primary {
        background: #7C3AED;
        color: #FFFFFF;
    }
    .talvex-btn-primary:hover {
        background: #6D28D9;
        box-shadow: 0 4px 12px rgba(124, 58, 237, 0.3);
    }
    .talvex-btn-secondary {
        background: #F3F4F6;
        color: #374151;
        border: 1px solid #D1D5DB;
    }
    .talvex-btn-secondary:hover {
        background: #E5E7EB;
    }
    .talvex-btn-danger {
        background: #FEE2E2;
        color: #DC2626;
    }
    .talvex-btn-danger:hover {
        background: #FECACA;
    }
    .talvex-btn-success {
        background: #D1FAE5;
        color: #059669;
    }
    .talvex-btn-success:hover {
        background: #A7F3D0;
    }

    /* === Kanban Column === */
    .kanban-column {
        background: #F9FAFB;
        border: 1px solid #E5E7EB;
        border-radius: 10px;
        padding: 12px;
        min-height: 300px;
    }
    .kanban-column-header {
        font-size: 13px;
        font-weight: 600;
        color: #374151;
        padding: 8px 12px;
        border-radius: 6px;
        margin-bottom: 8px;
        text-align: center;
    }
    .kanban-card {
        background: #FFFFFF;
        border: 1px solid #E5E7EB;
        border-radius: 8px;
        padding: 12px;
        margin-bottom: 8px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04);
        transition: box-shadow 0.2s ease;
    }
    .kanban-card:hover {
        box-shadow: 0 4px 8px rgba(0,0,0,0.08);
    }

    /* === Empty State === */
    .empty-state {
        text-align: center;
        padding: 40px 20px;
        color: #9CA3AF;
    }
    .empty-state-icon {
        font-size: 48px;
        margin-bottom: 12px;
    }
    .empty-state-text {
        font-size: 14px;
        color: #9CA3AF;
    }

    /* === Alert / Toast Styles === */
    .talvex-alert {
        padding: 12px 16px;
        border-radius: 8px;
        font-size: 14px;
        margin-bottom: 12px;
    }
    .talvex-alert-success {
        background: #D1FAE5;
        color: #065F46;
        border: 1px solid #6EE7B7;
    }
    .talvex-alert-error {
        background: #FEE2E2;
        color: #991B1B;
        border: 1px solid #FCA5A5;
    }
    .talvex-alert-warning {
        background: #FEF3C7;
        color: #92400E;
        border: 1px solid #FCD34D;
    }
    .talvex-alert-info {
        background: #DBEAFE;
        color: #1E40AF;
        border: 1px solid #93C5FD;
    }

    /* === Score Circle === */
    .score-circle {
        width: 80px;
        height: 80px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 24px;
        font-weight: 700;
        margin: 0 auto;
    }

    /* === Table Styles === */
    .dataframe {
        font-size: 13px !important;
    }
    .dataframe th {
        background: #F9FAFB !important;
        font-weight: 600 !important;
        color: #374151 !important;
        text-transform: none !important;
        font-size: 13px !important;
        padding: 10px 14px !important;
    }
    .dataframe td {
        padding: 8px 14px !important;
        color: #4B5563 !important;
    }

    /* === Streamlit overrides === */
    .stButton > button {
        border-radius: 8px !important;
        font-weight: 500 !important;
        transition: all 0.2s ease !important;
    }
    .stSelectbox > div > div {
        border-radius: 8px !important;
    }
    .stTextInput > div > div > input {
        border-radius: 8px !important;
    }
    .stTextArea > div > div > textarea {
        border-radius: 8px !important;
    }

    /* === Scrollable Container === */
    .scroll-container {
        max-height: 500px;
        overflow-y: auto;
        padding-right: 4px;
    }
    .scroll-container::-webkit-scrollbar {
        width: 6px;
    }
    .scroll-container::-webkit-scrollbar-track {
        background: #F3F4F6;
        border-radius: 3px;
    }
    .scroll-container::-webkit-scrollbar-thumb {
        background: #D1D5DB;
        border-radius: 3px;
    }
    .scroll-container::-webkit-scrollbar-thumb:hover {
        background: #9CA3AF;
    }

    /* === Progress Bar Custom === */
    .score-bar {
        height: 8px;
        border-radius: 4px;
        background: #E5E7EB;
        overflow: hidden;
    }
    .score-bar-fill {
        height: 100%;
        border-radius: 4px;
        transition: width 0.5s ease;
    }

    /* === Divider === */
    .talvex-divider {
        height: 1px;
        background: #E5E7EB;
        margin: 16px 0;
    }
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ============================================================
# Shared Constants
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

# ============================================================
# Session State Initialization
# ============================================================

if "API_BASE" not in st.session_state:
    st.session_state.API_BASE = "http://localhost:8000/api"

if "page" not in st.session_state:
    st.session_state.page = "Dashboard"

# Cache invalidation keys
if "refresh_key" not in st.session_state:
    st.session_state.refresh_key = 0

# ============================================================
# Sidebar Navigation
# ============================================================

with st.sidebar:
    st.markdown(
        """
        <div style="text-align:center; padding: 24px 0 8px 0;">
            <div style="font-size: 28px; font-weight: 800; letter-spacing: -0.02em;">
                🎯 TALVEX
            </div>
            <div style="font-size: 11px; font-weight: 400; opacity: 0.75; margin-top: 2px; letter-spacing: 0.08em; text-transform: uppercase;">
                Job Application Command Center
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)

    page_options = {
        "Dashboard": "📊",
        "Job Search": "🔍",
        "Pipeline": "📋",
        "Personas": "👤",
        "Resume": "📄",
        "Interview Prep": "🎯",
        "Privacy": "🛡️",
        "Analytics": "📈",
    }

    selected_page = st.radio(
        "Navigation",
        options=list(page_options.keys()),
        format_func=lambda x: f"{page_options[x]}  {x}",
        key="page",
        label_visibility="collapsed",
    )

    st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)

    st.markdown(
        """
        <div style="padding: 12px; background: rgba(255,255,255,0.1); border-radius: 8px; font-size: 11px; opacity: 0.7; text-align: center;">
            TALVEX v1.0.0<br>
            Built with ❤️
        </div>
        """,
        unsafe_allow_html=True,
    )

# ============================================================
# Page Router
# ============================================================

page_map = {
    "Dashboard": "pages.Dashboard",
    "Job Search": "pages.Job_Search",
    "Pipeline": "pages.Pipeline",
    "Personas": "pages.Personas",
    "Resume": "pages.Resume",
    "Interview Prep": "pages.Interview_Prep",
    "Privacy": "pages.Privacy",
    "Analytics": "pages.Analytics",
}

module_path = page_map.get(selected_page, "pages.Dashboard")

try:
    module = __import__(module_path, fromlist=["render"])
    module.render()
except ImportError as e:
    st.error(f"Failed to load page '{selected_page}': {e}")
    st.info("Make sure all page files exist in the `pages/` directory.")
except Exception as e:
    st.error(f"An error occurred while rendering '{selected_page}': {e}")
