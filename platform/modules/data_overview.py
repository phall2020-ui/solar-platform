"""Data Overview (Legacy Wrapper)."""
import os
from datetime import datetime, timedelta

import streamlit as st

from components.report_button import add_to_report_button
from services import legacy_toolkit
from styles import render_alert, render_divider, render_section_header


def render():
    """Render the legacy Data Overview page."""
    orch = legacy_toolkit.get_orchestrator()
    if not orch:
        st.error("Orchestrator not available.")
        return

    render_section_header("Data Availability Overview", icon="📊")
    st.markdown("Heatmap of data availability per site and month. Select a row to take action on missing data.")

    # Fetch Data Summary
    with st.spinner("Loading data availability..."):
        # Check if the method exists (may not be implemented in all Solar Toolkit versions)
        if not hasattr(orch, 'get_data_availability_summary'):
            render_alert(
                "The `get_data_availability_summary` method is not available in this version of Solar Toolkit. "
                "Please use the Data Explorer or Plant Management pages instead.",
                "warning"
            )
            return
        
        try:
            df_summary = orch.get_data_availability_summary()
        except Exception as e:
            render_alert(f"Error loading data availability: {e}", "error")
            return
    
    if df_summary.empty:
        render_alert("No data found in the database.", "info")
    else:
        # --- Interactive Heatmap (Table) ---
        def make_status_col(val):
            return "✅" if val else "❌"

        df_display = df_summary.copy()
        df_display['API'] = df_display['API Data'].apply(make_status_col)
        df_display['POA'] = df_display['POA Data'].apply(make_status_col)
        
        # Display as interactive table
        df_table = df_display[['Plant', 'Month', 'API', 'POA', 'api_count', 'poa_count']]
        st.dataframe(
            df_table,
            use_container_width=True,
            selection_mode="single-row",
            on_select="rerun",
            key="data_overview_table"
        )

        # Add to report
        add_to_report_button(
            content=df_table,
            title="Data Availability Overview",
            item_type='table',
            description="Data availability status per site and month",
            source_page="Data Overview",
            button_key="add_data_overview_table"
        )

        # --- Action Panel ---
        selection_state = st.session_state.get("data_overview_table")
        
        if selection_state and selection_state.get("selection") and selection_state["selection"]["rows"]:
            selected_idx = selection_state["selection"]["rows"][0]
            selected_row = df_display.iloc[selected_idx]
            
            render_divider()
            render_section_header(f"Actions for {selected_row['Plant']} - {selected_row['Month']}", icon="🔧")
            
            # Action Tabs
            act_tab1, act_tab2 = st.tabs(["Force API Pull", "Manual POA Match"])
            
            plant_uid = selected_row['plant_uid']
            month_str = selected_row['Month'] # YYYY-MM
            
            # Helper to get start/end of month
            try:
                m_date = datetime.strptime(month_str, "%Y-%m")
                m_start = m_date
                if m_date.month == 12:
                    m_next = m_date.replace(year=m_date.year+1, month=1)
                else:
                    m_next = m_date.replace(month=m_date.month+1)
                m_end = m_next - timedelta(days=1)
            except (ValueError, TypeError):
                m_start = datetime.today()
                m_end = datetime.today()

            with act_tab1:
                st.markdown("**Missing API Data?** Force a refresh for this month.")
                c1, c2 = st.columns(2)
                f_start = c1.date_input("Start Date", value=m_start, key="force_start")
                f_end = c2.date_input("End Date", value=m_end, key="force_end")
                
                if st.button("📥 Fetch API Data", key="force_api_btn"):
                    try:
                        with st.spinner(f"Fetching data for {selected_row['Plant']}..."):
                            count = orch.fetch_data(plant_uid, f_start.strftime("%Y%m%d"), f_end.strftime("%Y%m%d"))
                            render_alert(f"Fetched {count} readings.", "success")
                            st.rerun()
                    except Exception as e:
                        render_alert(f"Error fetching data: {e}", "error")

            with act_tab2:
                st.markdown("**Missing POA Data?** Manually assign a file.")
                if selected_row['POA Data']:
                    render_alert("POA data is already present for this month.", "success")
                
                st.markdown("Select an unmatched file from the scanned SolarGIS folders (configure in POA Import tab).")
                
                root_folder_list = st.session_state.get('poa_folders', [])
                
                if root_folder_list:
                    # Quick scan for unmatched
                    files_info = orch.preview_bulk_poa_matches(root_folder_list, [])
                    unmatched_filenames = files_info.get('unmatched_files', [])
                    
                    if not unmatched_filenames:
                        render_alert("No unmatched files found in current scan folder.", "info")
                    else:
                        file_to_assign = st.selectbox("Select Unmatched File", options=["-- Select --"] + sorted([os.path.basename(f) for f in unmatched_filenames]))
                        
                        if file_to_assign != "-- Select --":
                            full_path = next((f for f in unmatched_filenames if os.path.basename(f) == file_to_assign), None)
                            if full_path:
                                st.markdown(f"Assigning **{file_to_assign}** to **{selected_row['Plant']}**")
                                if st.button("🚀 Import & Link File", key="manual_link_btn"):
                                    try:
                                        mapping = {full_path: {'alias': selected_row['Plant'], 'folder': os.path.dirname(full_path)}}
                                        with st.spinner("Importing..."):
                                            res = orch.bulk_import_poa(mapping, "20000101", "20301231")
                                            render_alert(f"Imported {res.get(full_path, 0)} readings.", "success")
                                            st.rerun()
                                    except Exception as e:
                                        render_alert(f"Import failed: {e}", "error")
                else:
                    render_alert("No POA folder selected. Go to 'POA Import' tab -> 'From Folder Path' and select a root folder first.", "warning")
