"""
User Preferences UI Component
Provides settings interface for user preferences.
"""

import streamlit as st

from solar_platform.services.user_preferences import UserPreferences, get_preferences


def render_preferences_page():
    """Render the full preferences/settings page."""
    st.title("⚙️ Settings & Preferences")
    
    prefs = get_preferences()
    
    # Create tabs for different settings categories
    tabs = st.tabs([
        "General", 
        "Dashboard", 
        "Charts & Visualization", 
        "Data Sources",
        "Notifications",
        "Advanced"
    ])
    
    with tabs[0]:  # General
        _render_general_settings(prefs)
    
    with tabs[1]:  # Dashboard
        _render_dashboard_settings(prefs)
    
    with tabs[2]:  # Charts
        _render_chart_settings(prefs)
    
    with tabs[3]:  # Data Sources
        _render_data_source_settings(prefs)
    
    with tabs[4]:  # Notifications
        _render_notification_settings(prefs)
    
    with tabs[5]:  # Advanced
        _render_advanced_settings(prefs)
    
    # Export/Import/Reset section
    st.divider()
    _render_preferences_actions(prefs)


def _render_general_settings(prefs: UserPreferences):
    """Render general settings."""
    st.subheader("General Settings")
    
    col1, col2 = st.columns(2)
    
    with col1:
        default_page = st.selectbox(
            "Default Landing Page",
            options=["Dashboard", "Data Explorer", "Monthly Reporting", "Database Viewer"],
            index=["Dashboard", "Data Explorer", "Monthly Reporting", "Database Viewer"].index(
                prefs.get("default_page", "Dashboard")
            ),
            help="The page you'll see when opening the app"
        )
        if default_page != prefs.get("default_page"):
            prefs.set("default_page", default_page)
            st.success("✓ Default page updated")
        
        show_tooltips = st.checkbox(
            "Show Tooltips",
            value=prefs.get("show_tooltips", True),
            help="Display helpful tooltips throughout the app"
        )
        if show_tooltips != prefs.get("show_tooltips"):
            prefs.set("show_tooltips", show_tooltips)
            st.rerun()
        
        theme_mode = st.selectbox(
            "Theme Mode",
            options=["light", "dark", "auto"],
            index=["light", "dark", "auto"].index(prefs.get("theme_mode", "light")),
            help="Color scheme for the application"
        )
        if theme_mode != prefs.get("theme_mode"):
            prefs.set("theme_mode", theme_mode)
            st.info("Theme changes may require page refresh")
    
    with col2:
        fiscal_month = st.slider(
            "Default Fiscal Year Start Month",
            min_value=1,
            max_value=12,
            value=prefs.get("default_fiscal_month", 4),
            help="Month when your fiscal year begins (1=January, 4=April, etc.)"
        )
        if fiscal_month != prefs.get("default_fiscal_month"):
            prefs.set("default_fiscal_month", fiscal_month)
        
        date_format = st.selectbox(
            "Date Format",
            options=["YYYY-MM-DD", "DD/MM/YYYY", "MM/DD/YYYY", "DD.MM.YYYY"],
            index=["YYYY-MM-DD", "DD/MM/YYYY", "MM/DD/YYYY", "DD.MM.YYYY"].index(
                prefs.get("date_format", "YYYY-MM-DD")
            )
        )
        if date_format != prefs.get("date_format"):
            prefs.set("date_format", date_format)
        
        timezone = st.text_input(
            "Timezone",
            value=prefs.get("timezone", "UTC"),
            help="Your local timezone (e.g., Europe/London, America/New_York)"
        )
        if timezone != prefs.get("timezone"):
            prefs.set("timezone", timezone)


def _render_dashboard_settings(prefs: UserPreferences):
    """Render dashboard-specific settings."""
    st.subheader("Dashboard Settings")
    
    col1, col2 = st.columns(2)
    
    with col1:
        layout = st.radio(
            "Dashboard Layout",
            options=["compact", "expanded"],
            index=["compact", "expanded"].index(prefs.get("dashboard_layout", "compact")),
            help="Compact shows more widgets, expanded gives more breathing room"
        )
        if layout != prefs.get("dashboard_layout"):
            prefs.set("dashboard_layout", layout)
        
        sidebar_collapsed = st.checkbox(
            "Start with Sidebar Collapsed",
            value=prefs.get("sidebar_collapsed", False)
        )
        if sidebar_collapsed != prefs.get("sidebar_collapsed"):
            prefs.set("sidebar_collapsed", sidebar_collapsed)
    
    with col2:
        default_date_range = st.slider(
            "Default Date Range (days)",
            min_value=7,
            max_value=365,
            value=prefs.get("default_date_range_days", 90),
            help="Number of days to show by default in date pickers"
        )
        if default_date_range != prefs.get("default_date_range_days"):
            prefs.set("default_date_range_days", default_date_range)
        
        show_advanced = st.checkbox(
            "Show Advanced Options by Default",
            value=prefs.get("show_advanced_options", False),
            help="Display advanced filtering and analysis options automatically"
        )
        if show_advanced != prefs.get("show_advanced_options"):
            prefs.set("show_advanced_options", show_advanced)
    
    # Auto-refresh settings
    st.divider()
    st.subheader("Auto-Refresh")
    
    auto_refresh = st.checkbox(
        "Enable Auto-Refresh",
        value=prefs.get("auto_refresh_enabled", False),
        help="Automatically refresh data at regular intervals"
    )
    prefs.set("auto_refresh_enabled", auto_refresh)
    
    if auto_refresh:
        refresh_interval = st.slider(
            "Refresh Interval (seconds)",
            min_value=60,
            max_value=3600,
            value=prefs.get("auto_refresh_interval", 300),
            step=60
        )
        if refresh_interval != prefs.get("auto_refresh_interval"):
            prefs.set("auto_refresh_interval", refresh_interval)


def _render_chart_settings(prefs: UserPreferences):
    """Render chart and visualization settings."""
    st.subheader("Charts & Visualization")
    
    col1, col2 = st.columns(2)
    
    with col1:
        chart_theme = st.selectbox(
            "Chart Theme",
            options=["ampyr", "plotly_dark", "plotly_white", "ggplot2", "seaborn"],
            index=["ampyr", "plotly_dark", "plotly_white", "ggplot2", "seaborn"].index(
                prefs.get("chart_theme", "ampyr")
            ),
            help="Color scheme for all charts and graphs"
        )
        if chart_theme != prefs.get("chart_theme"):
            prefs.set("chart_theme", chart_theme)
            st.success("✓ Chart theme updated")
    
    with col2:
        number_format = st.selectbox(
            "Number Format",
            options=["1,234.56", "1.234,56", "1 234.56", "1234.56"],
            index=["1,234.56", "1.234,56", "1 234.56", "1234.56"].index(
                prefs.get("number_format", "1,234.56")
            ),
            help="How numbers are displayed in charts and tables"
        )
        if number_format != prefs.get("number_format"):
            prefs.set("number_format", number_format)
        
        currency = st.text_input(
            "Default Currency",
            value=prefs.get("currency", "GBP"),
            help="Currency code for financial displays (e.g., GBP, USD, EUR)"
        )
        if currency != prefs.get("currency"):
            prefs.set("currency", currency)


def _render_data_source_settings(prefs: UserPreferences):
    """Render data source preferences."""
    st.subheader("Data Sources")
    
    data_source = st.radio(
        "Preferred Data Source",
        options=["Both", "Solar Toolkit Only", "Monthly Reporting Only"],
        index=["Both", "Solar Toolkit Only", "Monthly Reporting Only"].index(
            prefs.get("data_source_preference", "Both")
        ),
        help="Which data sources to query by default"
    )
    if data_source != prefs.get("data_source_preference"):
        prefs.set("data_source_preference", data_source)
        st.success("✓ Data source preference updated")
    
    # Favorite Plants
    st.divider()
    st.subheader("Favorite Plants")
    
    favorites = prefs.get("favorite_plants", [])
    
    if favorites:
        st.write("Your favorite plants:")
        cols = st.columns(3)
        for idx, plant_id in enumerate(favorites):
            with cols[idx % 3]:
                if st.button(f"🗑️ {plant_id}", key=f"remove_fav_{plant_id}"):
                    prefs.remove_favorite_plant(plant_id)
                    st.rerun()
    else:
        st.info("You haven't marked any plants as favorites yet.")
    
    # Recent Plants
    st.divider()
    st.subheader("Recently Accessed Plants")
    
    recent = prefs.get_recent_plants()
    if recent:
        st.write(f"Recently viewed: {', '.join(recent[:5])}")
        if st.button("Clear Recent"):
            prefs.set("recent_plants", [])
            st.rerun()
    else:
        st.info("No recent plants.")


def _render_notification_settings(prefs: UserPreferences):
    """Render notification settings."""
    st.subheader("Notifications")
    
    notifications_enabled = st.checkbox(
        "Enable Notifications",
        value=prefs.get("notifications_enabled", True),
        help="Show alerts and notifications for important events"
    )
    prefs.set("notifications_enabled", notifications_enabled)
    
    if notifications_enabled:
        st.info("📧 Notification preferences for alerts and reports")
        
        # Future: email notifications, alert thresholds, etc.
        st.markdown("""
        **Coming Soon:**
        - Email notifications for critical alerts
        - Custom alert thresholds
        - Scheduled report delivery
        - Data quality alerts
        """)


def _render_advanced_settings(prefs: UserPreferences):
    """Render advanced settings."""
    st.subheader("Advanced Settings")
    
    st.markdown("""
    ⚠️ **Caution**: These settings can affect app performance and behavior.
    """)
    
    # Saved Filters
    st.divider()
    st.subheader("Saved Filters")
    
    saved_filters = prefs.get_saved_filters()
    
    if saved_filters:
        for filter_name in list(saved_filters.keys()):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(f"📁 {filter_name}")
            with col2:
                if st.button("Delete", key=f"del_filter_{filter_name}"):
                    prefs.delete_saved_filter(filter_name)
                    st.rerun()
    else:
        st.info("No saved filters yet.")
    
    # Recent Searches
    st.divider()
    st.subheader("Search History")
    
    recent_searches = prefs.get_recent_searches()
    
    if recent_searches:
        st.write(f"Recent searches: {', '.join(recent_searches[:10])}")
        if st.button("Clear Search History"):
            prefs.set("recent_searches", [])
            st.rerun()
    else:
        st.info("No search history.")


def _render_preferences_actions(prefs: UserPreferences):
    """Render export/import/reset actions."""
    st.subheader("Preferences Management")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("📤 Export Preferences"):
            json_str = prefs.export_preferences()
            st.download_button(
                label="Download as JSON",
                data=json_str,
                file_name="user_preferences.json",
                mime="application/json"
            )
    
    with col2:
        uploaded_file = st.file_uploader("📥 Import Preferences", type=["json"])
        if uploaded_file is not None:
            json_str = uploaded_file.read().decode("utf-8")
            try:
                prefs.import_preferences(json_str)
                st.success("✓ Preferences imported successfully!")
                st.rerun()
            except Exception as e:
                st.error(f"Failed to import: {e}")
    
    with col3:
        if st.button("🔄 Reset to Defaults", type="primary"):
            if st.button("⚠️ Confirm Reset"):
                prefs.reset()
                st.success("✓ All preferences reset to defaults")
                st.rerun()


def render_quick_preferences_sidebar():
    """Render quick access preferences in sidebar."""
    with st.sidebar:
        with st.expander("⚙️ Quick Settings"):
            prefs = get_preferences()
            
            # Quick toggles
            show_tooltips = st.checkbox(
                "Show Tooltips",
                value=prefs.get("show_tooltips", True),
                key="quick_tooltips"
            )
            if show_tooltips != prefs.get("show_tooltips"):
                prefs.set("show_tooltips", show_tooltips)
            
            show_advanced = st.checkbox(
                "Advanced Options",
                value=prefs.get("show_advanced_options", False),
                key="quick_advanced"
            )
            if show_advanced != prefs.get("show_advanced_options"):
                prefs.set("show_advanced_options", show_advanced)
            
            st.divider()
            if st.button("Full Settings", use_container_width=True):
                st.switch_page("pages/settings.py")  # Future navigation


def show_favorite_button(plant_id: str) -> bool:
    """
    Show a favorite/unfavorite button for a plant.
    
    Args:
        plant_id: The plant identifier
        
    Returns:
        True if plant is currently favorited
    """
    prefs = get_preferences()
    is_fav = prefs.is_favorite_plant(plant_id)
    
    if st.button("⭐" if is_fav else "☆", key=f"fav_{plant_id}", help="Toggle favorite"):
        if is_fav:
            prefs.remove_favorite_plant(plant_id)
        else:
            prefs.add_favorite_plant(plant_id)
        st.rerun()
    
    return is_fav
