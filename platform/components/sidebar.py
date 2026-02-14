"""
Unified sidebar navigation component.

Generates navigation dynamically from the page registry.
Supports grouped sections, role-based visibility, and icons.

DESIGN NOTES FOR EXTRACTION:
- When moving to React, this becomes a <Sidebar> component
- Page groups map to collapsible navigation sections
- Role-based filtering maps to route guards
"""
import streamlit as st

from services.page_registry import PAGE_GROUPS, SPECIAL_PAGES, get_visible_pages
from unified_config import config

from .ux import render_onboarding_tour

# Try to import auth components
try:
    from components.auth_ui import render_user_menu
    from components.notifications_ui import render_notification_badge

    AUTH_AVAILABLE = True
except ImportError:
    AUTH_AVAILABLE = False


def render_sidebar():
    """Render the unified sidebar with navigation and settings."""

    # Initialize current_page if not set
    if "current_page" not in st.session_state:
        st.session_state["current_page"] = "Dashboard"

    current_page = st.session_state["current_page"]

    # Determine user role (default to admin until auth system is fully wired)
    user_role = st.session_state.get("user_role", "admin")

    with st.sidebar:
        # App title and logo
        st.markdown(
            """
        <div class="sidebar-logo">
            <div class="glyph"></div>
            <div class="wordmark">AMPYR</div>
        </div>
        """,
            unsafe_allow_html=True,
        )
        st.markdown(f"### {config.APP_NAME}")
        st.markdown(f"*v{config.APP_VERSION}*")
        st.markdown("---")

        # ── Dynamic Navigation from Page Registry ──────────────

        visible_groups = get_visible_pages(user_role)

        for group_name, group_pages in visible_groups.items():
            # Get group icon from PAGE_GROUPS
            group = PAGE_GROUPS.get(group_name)
            group_icon = group.icon if group else ""

            st.markdown(f"### {group_icon} {group_name.upper()}")

            for page_name, page_config in group_pages.items():
                if not page_config.show_in_nav:
                    continue

                active = current_page == page_name
                button_label = f"{page_config.icon} {page_name}"

                if st.button(
                    button_label,
                    key=f"nav_{page_name.replace(' ', '_').replace('/', '_')}",
                    type="primary" if active else "secondary",
                    use_container_width=True,
                    help=page_config.description or None,
                ):
                    st.session_state["current_page"] = page_name
                    st.rerun()

        # Plant Detail page (hidden from nav, accessible via Dashboard click)
        # This is handled by the page router directly

        st.markdown("---")

        # ── Settings & Preferences ─────────────────────────────

        st.markdown("### ⚙️ Settings")

        # Quick settings button
        if st.button("⚙️ Preferences", use_container_width=True):
            st.session_state["current_page"] = "Settings"
            st.rerun()

        # Dark mode toggle (Phase 2.8)
        theme = st.session_state.get("theme", "light")
        if st.toggle("🌙 Dark Mode", value=theme == "dark", key="dark_mode_toggle"):
            st.session_state["theme"] = "dark"
        else:
            st.session_state["theme"] = "light"

        # Fiscal year start month
        fiscal_months = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ]
        fiscal_start = st.selectbox(
            "Fiscal Year Start",
            options=fiscal_months,
            index=config.DEFAULT_FISCAL_START - 1,
            key="fiscal_year_start_select",
        )

        # Map string selection to integer (1-12) for legacy compatibility
        month_map = {m: i + 1 for i, m in enumerate(fiscal_months)}
        st.session_state["fiscal_year_start"] = month_map.get(fiscal_start, 4)

        # Data source filter
        _data_source = st.selectbox(
            "Data Source",
            options=["Both", "Solar Toolkit Only", "Monthly Reporting Only"],
            index=0,
            key="data_source_filter",
        )

        # Background job monitor
        try:
            from components.job_monitor import job_monitor_sidebar

            job_monitor_sidebar()
        except Exception:
            pass  # Silently skip if not available

        # Global search hint
        try:
            if st.button("🔍 Search (Ctrl+K)", use_container_width=True):
                st.session_state["show_search"] = True
                st.rerun()
        except Exception:
            pass

        # Quick onboarding tips for first-time visitors
        render_onboarding_tour(
            steps=[
                "Use the sidebar to switch modules.",
                "Add any chart or table to a report via the teal buttons.",
                "Undo/redo is available inside the Report Builder.",
                "Keyboard: Tab through form fields, Enter to confirm buttons.",
            ],
        )

        st.markdown("---")

        # User authentication and notifications
        if AUTH_AVAILABLE:
            try:
                render_user_menu()
                render_notification_badge()
            except Exception:
                pass

        # Footer with info
        st.markdown(
            """
        <div style="font-size: 0.75rem; color: #6B7C85; text-align: center;">
            AMPYR Solar Portfolio Manager<br/>
            Combining operational and financial analysis
        </div>
        """,
            unsafe_allow_html=True,
        )

    return st.session_state["current_page"]


def get_navigation_state():
    """Get the current navigation state from session state.

    Returns:
        Dict with selected page and settings
    """
    return {
        "page": st.session_state.get("current_page", "Dashboard"),
        "fiscal_start": st.session_state.get("fiscal_year_start", 4),
        "data_source": st.session_state.get("data_source_filter", "Both"),
    }
