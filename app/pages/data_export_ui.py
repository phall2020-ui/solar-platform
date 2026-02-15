"""
Data Export UI Module.
Provides interface for exporting data in various formats and managing exports.
"""
from datetime import datetime

import pandas as pd
import streamlit as st

from solar_platform.services.auth import get_current_user
from solar_platform.db.utils import execute_df
from solar_platform.services.export import ExportFormat, ExportService, TemplateExports
from app.config_compat import config


def render():
    """Render the data export page."""
    user = get_current_user()

    st.markdown("## 📤 Data Export")
    st.markdown("Export your solar portfolio data in multiple formats")

    # Check permissions
    if user and not user.has_permission("export"):
        st.warning("You need 'export' permission to use this feature")
        return

    # Initialize export service
    if "export_service" not in st.session_state:
        st.session_state.export_service = ExportService()

    export_service = st.session_state.export_service

    # Tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "Quick Export", "Custom Export", "Scheduled Exports", "Export History"
    ])

    with tab1:
        render_quick_export(export_service)

    with tab2:
        render_custom_export(export_service)

    with tab3:
        render_scheduled_exports(export_service)

    with tab4:
        render_export_history(export_service)


def render_quick_export(export_service: ExportService):
    """Render quick export templates."""
    st.markdown("### ⚡ Quick Export Templates")
    st.markdown("Pre-configured exports for common use cases")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Monthly Performance Report")
        st.markdown("Export monthly performance data for all plants")

        year = st.number_input("Year", min_value=2020, max_value=2030, value=datetime.now().year)
        month = st.number_input("Month", min_value=1, max_value=12, value=datetime.now().month)

        if st.button("Export Monthly Report", use_container_width=True):
            with st.spinner("Generating export..."):
                try:
                    sheets = TemplateExports.monthly_performance_report(
                        config.REPORTING_DB, year, month
                    )

                    if sheets:
                        data = export_service.export_multiple_sheets(
                            sheets, f"monthly_report_{year}_{month:02d}"
                        )

                        st.download_button(
                            label="Download Excel Report",
                            data=data,
                            file_name=f"monthly_report_{year}_{month:02d}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                        st.success("Export ready!")
                    else:
                        st.warning("No data available for the selected period")
                except Exception as e:
                    st.error(f"Export failed: {str(e)}")

    with col2:
        st.markdown("#### Plant Summary Report")
        st.markdown("Export comprehensive data for a specific plant")

        # Get available plants
        plants = get_available_plants()
        plant_id = st.selectbox("Select Plant", options=plants)

        if st.button("Export Plant Summary", use_container_width=True):
            with st.spinner("Generating export..."):
                try:
                    sheets = TemplateExports.plant_summary_report(
                        config.TOOLKIT_DB, plant_id
                    )

                    if sheets:
                        data = export_service.export_multiple_sheets(
                            sheets, f"plant_summary_{plant_id}"
                        )

                        st.download_button(
                            label="Download Excel Report",
                            data=data,
                            file_name=f"plant_summary_{plant_id}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                        st.success("Export ready!")
                    else:
                        st.warning("No data available for the selected plant")
                except Exception as e:
                    st.error(f"Export failed: {str(e)}")

    st.markdown("---")

    # Portfolio-wide exports
    st.markdown("#### Portfolio-Wide Exports")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("Export All Plants", use_container_width=True):
            export_all_plants(export_service)

    with col2:
        if st.button("Export Performance Metrics", use_container_width=True):
            export_performance_metrics(export_service)

    with col3:
        if st.button("Export Alert History", use_container_width=True):
            export_alert_history(export_service)


def render_custom_export(export_service: ExportService):
    """Render custom export builder."""
    st.markdown("### 🛠️ Custom Export Builder")
    st.markdown("Build a custom export with your specific requirements")

    with st.form("custom_export_form"):
        export_name = st.text_input("Export Name", placeholder="My Custom Export")

        # Data source selection
        st.markdown("#### Select Data Source")
        data_source = st.selectbox(
            "Database",
            options=["Solar Toolkit", "Monthly Reporting", "Notifications", "Custom Query"]
        )

        # Table/query selection
        if data_source == "Custom Query":
            query = st.text_area(
                "SQL Query",
                placeholder="SELECT * FROM plants WHERE capacity_mw > 10",
                height=150
            )
        else:
            table = st.selectbox(
                "Table",
                options=get_tables_for_source(data_source)
            )
            query = None

        # Filters
        st.markdown("#### Filters (Optional)")
        col1, col2 = st.columns(2)

        with col1:
            start_date = st.date_input("Start Date", value=None)
        with col2:
            end_date = st.date_input("End Date", value=None)

        # Format selection
        st.markdown("#### Export Format")
        format_option = st.selectbox(
            "Format",
            options=["Excel (.xlsx)", "CSV (.csv)", "JSON (.json)", "Parquet (.parquet)"]
        )

        format_map = {
            "Excel (.xlsx)": ExportFormat.EXCEL,
            "CSV (.csv)": ExportFormat.CSV,
            "JSON (.json)": ExportFormat.JSON,
            "Parquet (.parquet)": ExportFormat.PARQUET,
        }
        export_format = format_map[format_option]

        # Additional options
        st.markdown("#### Options")
        include_index = st.checkbox("Include row index")

        submit = st.form_submit_button("Generate Export")

        if submit:
            if not export_name:
                st.error("Please provide an export name")
            else:
                with st.spinner("Generating custom export..."):
                    try:
                        # Build the query
                        if data_source == "Custom Query":
                            final_query = query
                        else:
                            final_query = f"SELECT * FROM {table}"

                            # Add date filters if applicable
                            if start_date and end_date:
                                final_query += f" WHERE date BETWEEN '{start_date}' AND '{end_date}'"

                        # Execute export
                        db_path = get_db_for_source(data_source)
                        data = export_service.export_query_result(
                            db_path,
                            final_query,
                            export_name,
                            export_format,
                            index=include_index
                        )

                        # Provide download
                        extensions = {
                            ExportFormat.EXCEL: ".xlsx",
                            ExportFormat.CSV: ".csv",
                            ExportFormat.JSON: ".json",
                            ExportFormat.PARQUET: ".parquet",
                        }
                        ext = extensions[export_format]

                        st.download_button(
                            label=f"Download {export_name}{ext}",
                            data=data,
                            file_name=f"{export_name}{ext}",
                            mime=get_mime_type(export_format)
                        )
                        st.success("Export ready!")

                    except Exception as e:
                        st.error(f"Export failed: {str(e)}")


def render_scheduled_exports(export_service: ExportService):
    """Render scheduled exports interface."""
    st.markdown("### ⏰ Scheduled Exports")
    st.markdown("Set up automated exports to run on a schedule")

    st.info("Scheduled exports feature coming soon! This will allow you to automatically export data daily, weekly, or monthly.")

    # Placeholder UI
    with st.form("schedule_export_form"):
        _schedule_name = st.text_input("Schedule Name")
        _export_type = st.selectbox("Export Type", options=["Monthly Report", "Plant Summary", "Custom"])
        _frequency = st.selectbox("Frequency", options=["Daily", "Weekly", "Monthly"])
        _time = st.time_input("Time")
        _email = st.text_input("Email Recipients (comma-separated)")

        if st.form_submit_button("Create Schedule"):
            st.success("Scheduled export created! (Feature in development)")


def render_export_history(export_service: ExportService):
    """Render export history and management."""
    st.markdown("### 📜 Export History")

    # Get export history
    exports = export_service.list_exports()

    if not exports:
        st.info("No exports found in history")
        return

    # Display exports
    st.markdown(f"**Total Exports:** {len(exports)}")

    # Filters
    col1, col2 = st.columns(2)
    with col1:
        format_filter = st.multiselect(
            "Filter by Format",
            options=list(set([e['format'] for e in exports]))
        )
    with col2:
        sort_by = st.selectbox("Sort by", options=["Date (Newest)", "Date (Oldest)", "Size", "Name"])

    # Apply filters
    filtered_exports = exports
    if format_filter:
        filtered_exports = [e for e in exports if e['format'] in format_filter]

    # Sort
    if sort_by == "Date (Newest)":
        filtered_exports = sorted(filtered_exports, key=lambda x: x['modified'], reverse=True)
    elif sort_by == "Date (Oldest)":
        filtered_exports = sorted(filtered_exports, key=lambda x: x['modified'])
    elif sort_by == "Size":
        filtered_exports = sorted(filtered_exports, key=lambda x: x['size_bytes'], reverse=True)
    else:
        filtered_exports = sorted(filtered_exports, key=lambda x: x['filename'])

    # Display as table
    df = pd.DataFrame(filtered_exports)
    df['size_mb'] = (df['size_bytes'] / 1024 / 1024).round(2)
    df = df[['filename', 'format', 'size_mb', 'modified']]
    df.columns = ['Filename', 'Format', 'Size (MB)', 'Modified']

    st.dataframe(df, use_container_width=True, hide_index=True)

    # Cleanup old exports
    st.markdown("---")
    st.markdown("#### Cleanup")

    col1, col2 = st.columns([2, 1])
    with col1:
        days = st.slider("Delete exports older than (days)", min_value=7, max_value=365, value=30)
    with col2:
        if st.button("Delete Old Exports"):
            deleted = export_service.cleanup_old_exports(days)
            st.success(f"Deleted {deleted} old export(s)")
            st.rerun()


# Helper functions

def get_available_plants():
    """Get list of available plants."""
    try:
        df = execute_df(str(config.TOOLKIT_DB), "SELECT DISTINCT plant_id FROM plants")
        return df['plant_id'].tolist()
    except Exception:
        return []


def get_tables_for_source(source: str):
    """Get tables for a data source."""
    table_map = {
        "Solar Toolkit": ["plants", "plant_data", "inverters", "weather"],
        "Monthly Reporting": ["performance_metrics", "energy_data", "alerts"],
        "Notifications": ["notifications", "alerts", "alert_history"],
    }
    return table_map.get(source, [])


def get_db_for_source(source: str):
    """Get database path for a source."""
    db_map = {
        "Solar Toolkit": config.TOOLKIT_DB,
        "Monthly Reporting": config.REPORTING_DB,
        "Notifications": config.TOOLKIT_DB,
    }
    return db_map.get(source, config.TOOLKIT_DB)


def get_mime_type(format: str):
    """Get MIME type for export format."""
    mime_map = {
        ExportFormat.EXCEL: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ExportFormat.CSV: "text/csv",
        ExportFormat.JSON: "application/json",
        ExportFormat.PARQUET: "application/octet-stream",
    }
    return mime_map.get(format, "application/octet-stream")


def export_all_plants(export_service: ExportService):
    """Export all plants data."""
    try:
        df = execute_df(str(config.TOOLKIT_DB), "SELECT * FROM plants")

        data = export_service.export_dataframe(df, "all_plants", ExportFormat.EXCEL)

        st.download_button(
            label="Download All Plants",
            data=data,
            file_name="all_plants.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        st.error(f"Export failed: {str(e)}")


def export_performance_metrics(export_service: ExportService):
    """Export performance metrics."""
    try:
        df = execute_df(str(config.REPORTING_DB), "SELECT * FROM performance_metrics LIMIT 10000")

        data = export_service.export_dataframe(df, "performance_metrics", ExportFormat.EXCEL)

        st.download_button(
            label="Download Performance Metrics",
            data=data,
            file_name="performance_metrics.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        st.error(f"Export failed: {str(e)}")


def export_alert_history(export_service: ExportService):
    """Export alert history."""
    try:
        from solar_platform.services.notifications import NotificationService
        notif_service = NotificationService()

        history = notif_service.get_alert_history(limit=1000)
        df = pd.DataFrame(history)

        data = export_service.export_dataframe(df, "alert_history", ExportFormat.EXCEL)

        st.download_button(
            label="Download Alert History",
            data=data,
            file_name="alert_history.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        st.error(f"Export failed: {str(e)}")
