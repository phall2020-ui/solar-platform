"""
Contextual Help & Tooltips System
Provides inline help, tooltips, and guided tours for better UX.
"""
from typing import Literal

import streamlit as st

from solar_platform.services.user_preferences import get_pref

# Help content repository
HELP_CONTENT = {
    "dashboard": {
        "title": "Dashboard Overview",
        "description": "Your central hub for monitoring solar portfolio performance.",
        "tips": [
            "Use the date picker to adjust the time range for all metrics",
            "Favorite plants appear at the top for quick access",
            "Click any metric card for detailed analysis"
        ]
    },
    "data_explorer": {
        "title": "Data Explorer",
        "description": "Upload, validate, and manage your solar data.",
        "tips": [
            "Drag and drop CSV files for quick upload",
            "Check the Data Health tab after uploads",
            "Use background jobs for large datasets"
        ]
    },
    "monthly_reporting": {
        "title": "Monthly Reporting",
        "description": "Generate comprehensive monthly performance reports.",
        "tips": [
            "Select fiscal month in settings for accurate yearly views",
            "Reports can be generated in background for large portfolios",
            "Exported PDFs include all charts and analysis"
        ]
    },
    "cache_management": {
        "title": "Cache Management",
        "description": "Monitor and control the application cache for better performance.",
        "tips": [
            "Clear cache if you see stale data",
            "Cache warm-up runs automatically on startup",
            "Check hit rate to optimize performance"
        ]
    },
    "background_jobs": {
        "title": "Background Jobs",
        "description": "Long-running tasks execute without blocking the UI.",
        "tips": [
            "Check job status in the sidebar monitor",
            "Failed jobs can be retried from the jobs tab",
            "Maximum 2 concurrent jobs to preserve performance"
        ]
    },
    "data_health": {
        "title": "Data Health Dashboard",
        "description": "Monitor data quality with automated validation checks.",
        "tips": [
            "Red badges indicate critical data issues",
            "Validation runs automatically on upload",
            "Check the detailed report for specific problems"
        ]
    },
    "global_search": {
        "title": "Global Search",
        "description": "Find plants, reports, and features quickly.",
        "tips": [
            "Press Ctrl+K (Cmd+K on Mac) to open search anytime",
            "Search works across all databases",
            "Recent searches are saved for quick access"
        ]
    },
    "user_preferences": {
        "title": "Settings & Preferences",
        "description": "Customize your experience.",
        "tips": [
            "Set your default fiscal month for accurate reporting",
            "Favorite plants for quick access",
            "Export preferences to backup your settings"
        ]
    },
    "keyboard_shortcuts": {
        "title": "Keyboard Shortcuts",
        "description": "Navigate faster with keyboard shortcuts.",
        "tips": [
            "Press Shift+? to see all available shortcuts",
            "Ctrl+K opens global search",
            "Ctrl+R refreshes the current view"
        ]
    }
}

# Field-level help
FIELD_HELP = {
    "fiscal_month": "The month when your fiscal year begins (e.g., 4 for April). Used for yearly reporting calculations.",
    "plant_id": "Unique identifier for a solar plant in your portfolio.",
    "date_range": "Select the time period for analysis. Use presets or custom dates.",
    "chart_theme": "Visual style for all charts and graphs. Choose one that matches your brand.",
    "auto_refresh": "Automatically reload data at specified intervals. Useful for monitoring dashboards.",
    "cache_ttl": "How long cached data remains valid (in seconds). Lower values mean fresher data but more database queries.",
    "job_priority": "Higher priority jobs execute first. Use for time-sensitive reports.",
    "validation_threshold": "Minimum data quality score (0-100). Data below this triggers warnings.",
    "export_format": "Choose output format for reports (PDF, Excel, CSV).",
    "data_source": "Which database to query. 'Both' combines Solar Toolkit and Monthly Reporting data."
}


class HelpTooltip:
    """Represents a help tooltip."""
    
    def __init__(
        self,
        content: str,
        title: str | None = None,
        icon: str = "ℹ️",
        placement: Literal["top", "bottom", "left", "right"] = "top"
    ):
        self.content = content
        self.title = title
        self.icon = icon
        self.placement = placement


def show_tooltip(
    label: str,
    help_text: str,
    icon: str = "ℹ️"
) -> None:
    """
    Show a tooltip next to a label.
    
    Args:
        label: The label text
        help_text: The help content
        icon: Icon to show (default info icon)
    """
    # Check if tooltips are enabled
    if not get_pref("show_tooltips", True):
        st.write(label)
        return
    
    # Display with help icon
    col1, col2 = st.columns([0.95, 0.05])
    with col1:
        st.write(label)
    with col2:
        st.markdown(f"<span title='{help_text}'>{icon}</span>", unsafe_allow_html=True)


def render_help_section(section_key: str):
    """
    Render a help section with expandable content.
    
    Args:
        section_key: Key from HELP_CONTENT
    """
    if section_key not in HELP_CONTENT:
        return
    
    help_data = HELP_CONTENT[section_key]
    
    with st.expander(f"❓ {help_data['title']} - Help"):
        st.markdown(f"**{help_data['description']}**")
        
        if help_data.get("tips"):
            st.markdown("**Tips:**")
            for tip in help_data["tips"]:
                st.markdown(f"• {tip}")


def render_inline_help(field_key: str) -> None:
    """
    Render inline help for a field.
    
    Args:
        field_key: Key from FIELD_HELP
    """
    if field_key in FIELD_HELP:
        st.caption(f"ℹ️ {FIELD_HELP[field_key]}")


def show_help_icon(help_text: str, key: str | None = None) -> None:
    """
    Show a clickable help icon that displays a tooltip.
    
    Args:
        help_text: The help content to display
        key: Unique key for the help icon
    """
    if not get_pref("show_tooltips", True):
        return
    
    if st.button("ℹ️", key=key, help=help_text):
        st.info(help_text)


def render_contextual_help_sidebar():
    """Render contextual help in the sidebar based on current page."""
    with st.sidebar:
        with st.expander("❓ Help & Tips"):
            # Detect current page from session state
            current_page = st.session_state.get("current_page", "dashboard")
            
            # Show relevant help
            page_key = current_page.lower().replace(" ", "_")
            if page_key in HELP_CONTENT:
                help_data = HELP_CONTENT[page_key]
                st.markdown(f"**{help_data['title']}**")
                st.caption(help_data["description"])
                
                if help_data.get("tips"):
                    st.markdown("**Quick Tips:**")
                    for tip in help_data["tips"]:
                        st.markdown(f"• {tip}")
            
            st.divider()
            
            # Link to full help
            if st.button("📚 View All Help", use_container_width=True):
                st.session_state["show_help_center"] = True


def render_help_center():
    """Render the full help center with all documentation."""
    st.title("📚 Help Center")
    
    # Search help
    _search_query = st.text_input("🔍 Search help articles...", placeholder="e.g., how to upload data")
    
    # Categories
    tabs = st.tabs(["Getting Started", "Features", "Settings", "Troubleshooting"])
    
    with tabs[0]:  # Getting Started
        st.header("Getting Started")
        
        st.subheader("Quick Start Guide")
        st.markdown("""
        1. **Connect Your Data**: Upload solar performance data via Data Explorer
        2. **Review Data Quality**: Check the Data Health dashboard for any issues
        3. **Explore Dashboard**: View portfolio-wide metrics and KPIs
        4. **Generate Reports**: Create monthly performance reports
        5. **Customize Settings**: Set preferences for fiscal year, themes, and more
        """)
        
        st.subheader("System Requirements")
        st.markdown("""
        - **Browser**: Chrome, Firefox, Safari, or Edge (latest version)
        - **Data Format**: CSV files with columns: timestamp, value, plant_id
        - **File Size**: Up to 100MB per upload (use background jobs for larger files)
        """)
    
    with tabs[1]:  # Features
        st.header("Features")
        
        for section_key, help_data in HELP_CONTENT.items():
            with st.expander(help_data["title"]):
                st.markdown(f"**{help_data['description']}**")
                
                if help_data.get("tips"):
                    st.markdown("**Tips:**")
                    for tip in help_data["tips"]:
                        st.markdown(f"• {tip}")
    
    with tabs[2]:  # Settings
        st.header("Settings Guide")
        
        st.subheader("General Settings")
        for field_key, help_text in FIELD_HELP.items():
            st.markdown(f"**{field_key}**: {help_text}")
    
    with tabs[3]:  # Troubleshooting
        st.header("Troubleshooting")
        
        st.subheader("Common Issues")
        
        with st.expander("Data not appearing after upload"):
            st.markdown("""
            **Possible causes:**
            - Upload still in progress (check Background Jobs)
            - Data validation failed (check Data Health)
            - Cache is stale (clear cache in Data Explorer)
            
            **Solutions:**
            1. Check the Background Jobs tab for upload status
            2. Review Data Health report for validation errors
            3. Try clearing the cache and refreshing
            """)
        
        with st.expander("Charts not loading"):
            st.markdown("""
            **Possible causes:**
            - No data in selected date range
            - Filter too restrictive
            - Browser compatibility issue
            
            **Solutions:**
            1. Expand date range
            2. Reset filters to defaults
            3. Try a different browser or clear browser cache
            """)
        
        with st.expander("Slow performance"):
            st.markdown("""
            **Possible causes:**
            - Large dataset selected
            - Cache is disabled or expired
            - Multiple background jobs running
            
            **Solutions:**
            1. Enable cache in settings
            2. Use smaller date ranges
            3. Wait for background jobs to complete
            4. Check cache hit rate in Cache Management
            """)


def show_guided_tour():
    """Show an interactive guided tour for new users."""
    if "tour_completed" not in st.session_state:
        st.session_state["tour_completed"] = False
    
    if not st.session_state["tour_completed"]:
        with st.sidebar:
            with st.container():
                st.info("👋 Welcome! Would you like a quick tour?")
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Start Tour", key="start_tour"):
                        st.session_state["tour_step"] = 0
                with col2:
                    if st.button("Skip", key="skip_tour"):
                        st.session_state["tour_completed"] = True
                        st.rerun()


def render_tour_step(step: int):
    """Render a specific tour step."""
    tours = [
        {
            "title": "Welcome to Solar Portfolio Manager",
            "content": "This app helps you manage and analyze your solar portfolio performance.",
            "target": "sidebar"
        },
        {
            "title": "Navigation",
            "content": "Use the sidebar to navigate between different modules and features.",
            "target": "sidebar"
        },
        {
            "title": "Dashboard",
            "content": "Your central hub for monitoring portfolio KPIs and metrics.",
            "target": "main"
        },
        {
            "title": "Data Explorer",
            "content": "Upload and manage your solar data with built-in validation.",
            "target": "main"
        },
        {
            "title": "Keyboard Shortcuts",
            "content": "Press Shift+? anytime to see available keyboard shortcuts. Try Ctrl+K for search!",
            "target": "main"
        }
    ]
    
    if step < len(tours):
        tour_data = tours[step]
        
        st.info(f"""
        **Step {step + 1} of {len(tours)}: {tour_data['title']}**
        
        {tour_data['content']}
        """)
        
        col1, col2 = st.columns(2)
        with col1:
            if step > 0:
                if st.button("← Previous"):
                    st.session_state["tour_step"] = step - 1
                    st.rerun()
        with col2:
            if step < len(tours) - 1:
                if st.button("Next →"):
                    st.session_state["tour_step"] = step + 1
                    st.rerun()
            else:
                if st.button("Finish Tour"):
                    st.session_state["tour_completed"] = True
                    del st.session_state["tour_step"]
                    st.rerun()


def add_help_to_component(
    component_name: str,
    help_text: str | None = None,
    help_key: str | None = None
):
    """
    Add contextual help to any Streamlit component.
    
    Args:
        component_name: Name of the component
        help_text: Direct help text (overrides help_key)
        help_key: Key to look up in FIELD_HELP
    """
    if not get_pref("show_tooltips", True):
        return
    
    # Get help text
    if help_text is None and help_key:
        help_text = FIELD_HELP.get(help_key, "")
    
    if help_text:
        st.caption(f"ℹ️ {help_text}")


# Example: Enhanced input with automatic help
def input_with_help(
    label: str,
    help_key: str | None = None,
    help_text: str | None = None,
    **kwargs
):
    """
    Text input with automatic contextual help.
    
    Args:
        label: Input label
        help_key: Key from FIELD_HELP
        help_text: Direct help text
        **kwargs: Additional args for st.text_input
    """
    # Get help text
    if help_text is None and help_key:
        help_text = FIELD_HELP.get(help_key, "")
    
    # Use native Streamlit help parameter
    return st.text_input(label, help=help_text, **kwargs)


def selectbox_with_help(
    label: str,
    options: list,
    help_key: str | None = None,
    help_text: str | None = None,
    **kwargs
):
    """
    Selectbox with automatic contextual help.
    
    Args:
        label: Select label
        options: Select options
        help_key: Key from FIELD_HELP
        help_text: Direct help text
        **kwargs: Additional args for st.selectbox
    """
    if help_text is None and help_key:
        help_text = FIELD_HELP.get(help_key, "")
    
    return st.selectbox(label, options, help=help_text, **kwargs)
