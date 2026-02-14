"""
Solar Asset Data Manager - Main Application Entry Point

This module serves as the main entry point for the Solar Asset Data Manager application,
a comprehensive Streamlit-based tool for solar portfolio performance analysis.
It handles navigation, page routing, and integration of various analysis modules.
"""

import streamlit as st

from config import init_session_state, setup_page
from data_access import SolarDataExtractor
from ui_tabs import (
    render_kpi_tab,
    render_query_tab,
    render_sidebar,
    render_tables_tab,
    render_upload_tab,
)
from ui_calculations_v2 import render_calculations_v2_tab
from ui_waterfall_v2 import render_waterfall_tab_v2
from ui_excom_report import render_excom_report_tab


def set_page(page_name: str) -> None:
    """
    Set the active page in the navigation system.

    This callback function updates the session state to change the currently
    selected page before Streamlit reruns the application.

    Args:
        page_name: Name of the page to navigate to (e.g., "Upload", "Query", "ExCom Report").
    """
    st.session_state.page_selector = page_name


def main() -> None:
    """
    Main application entry point.

    Initializes the Streamlit application, sets up session state, configures
    the page layout, and handles navigation between different analysis tabs.
    Routes user requests to appropriate rendering functions based on the
    selected page.
    """
    init_session_state()
    setup_page()

    extractor = SolarDataExtractor(st.session_state.db_name)

    # Sidebar navigation
    with st.sidebar:
        st.header("📊 Navigation")

        # All page options including Upload and Query
        all_pages = ["ExCom Report", "Tables", "KPI Dashboard", "Calculations", "Waterfall", "Upload", "Query"]

        # Determine the current index based on session state
        current_page = st.session_state.get("page_selector", "ExCom Report")
        if current_page in all_pages:
            current_index = all_pages.index(current_page)
        else:
            current_index = 0

        page = st.radio("Select Page", all_pages, index=current_index, key="page_selector")

        st.divider()
        st.write("### 📁 Data Management")

        col1, col2 = st.columns(2)
        with col1:
            st.button("📤\nUpload", use_container_width=True, key="btn_upload", on_click=set_page, args=("Upload",))
        with col2:
            st.button("🔍\nQuery", use_container_width=True, key="btn_query", on_click=set_page, args=("Query",))

        st.divider()
        render_sidebar(extractor)

    # Main content area
    if page == "Upload":
        render_upload_tab(st.container(), extractor)
    elif page == "Query":
        render_query_tab(st.container(), extractor)
    elif page == "Tables":
        render_tables_tab(st.container(), extractor)
    elif page == "KPI Dashboard":
        render_kpi_tab(st.container(), extractor)
    elif page == "Calculations":
        render_calculations_v2_tab(st.container(), extractor)
    elif page == "Waterfall":
        render_waterfall_tab_v2(st.container(), extractor)
    elif page == "ExCom Report":
        render_excom_report_tab(st.container(), extractor)


if __name__ == "__main__":
    main()
