"""
User Interface Tabs Module

This module contains the rendering functions for all main application tabs
in the Solar Asset Data Manager, including:
- Sidebar with settings and data management
- Upload tab for data import and column mapping
- Query tab for running custom SQL queries
- Tables tab for viewing database contents
- KPI Dashboard for key performance indicators

The module provides a comprehensive UI for data management and visualization.
"""

from io import BytesIO
from typing import List

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from analysis import (
    DataProcessor,
    SolarDataAnalyzer,
    aggregate_flexible,
    detect_column_candidates,
    plot_waterfall,
)
from config import Config, clear_saved_colmap, save_colmap
from data_access import SolarDataExtractor


def ensure_colmap_from_df(df: pd.DataFrame) -> None:
    """
    Auto-detect column mapping from a DataFrame if not yet confirmed.

    Attempts to detect standard solar data columns in the DataFrame
    and set up the column mapping in session state if successful.

    Args:
        df: DataFrame to analyze for column detection.
    """
    if st.session_state.get("colmap_confirmed"):
        return

    detected = detect_column_candidates(tuple(df.columns))
    required = ["actual_gen", "wab", "budget_gen"]
    if all(detected.get(k) and detected[k] in df.columns for k in required):
        st.session_state.colmap = detected
        st.session_state.colmap_confirmed = True
        st.session_state["colmap_source"] = "auto_detected"
        save_colmap(detected)
        st.info("Column mapping auto-detected from the selected table.")
    else:
        st.warning("Column mapping not confirmed. Go to Upload tab to map required fields.")


def format_percent_like(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert PR/availability columns to 0-100 percentage scale and round.

    Args:
        df: DataFrame with performance ratio and availability columns.

    Returns:
        DataFrame with percentage columns normalized to 0-100 scale and rounded to 2 decimal places.
    """
    df_fmt = df.copy()
    percent_cols = [c for c in df_fmt.columns if any(k in c.lower() for k in ["pr", "avail"])]
    for col in percent_cols:
        series = df_fmt[col]
        if not pd.api.types.is_numeric_dtype(series):
            continue
        scaled = np.where(series <= 1, series * 100, series)
        df_fmt[col] = pd.to_numeric(scaled, errors="coerce").round(2)
    return df_fmt


def render_sidebar(extractor: SolarDataExtractor) -> None:
    """
    Render the application sidebar with settings and utilities.

    Displays:
    - Database name configuration
    - Fiscal year settings
    - Column mapping reset button
    - Sample data generation

    Args:
        extractor: SolarDataExtractor instance for database operations.
    """
    st.header("⚙️ Settings")
    st.session_state.db_name = st.text_input("DB Name", st.session_state.db_name)

    st.divider()
    st.write("### 📅 Fiscal Year Settings")
    if "fiscal_year_start" not in st.session_state:
        st.session_state.fiscal_year_start = Config.DEFAULT_FISCAL_START

    fiscal_month_names = {
        1: "January",
        2: "February",
        3: "March",
        4: "April",
        5: "May",
        6: "June",
        7: "July",
        8: "August",
        9: "September",
        10: "October",
        11: "November",
        12: "December",
    }

    selected_month_name = st.selectbox(
        "Fiscal year starts in",
        list(fiscal_month_names.values()),
        index=3,
        help="YTD and Quarterly calculations will start from this month",
    )
    st.session_state.fiscal_year_start = list(fiscal_month_names.keys())[
        list(fiscal_month_names.values()).index(selected_month_name)
    ]

    st.info(
        f"📊 FY structure:\n- Q1: {fiscal_month_names[st.session_state.fiscal_year_start]}-{fiscal_month_names[(st.session_state.fiscal_year_start + 2) % 12 or 12]}\n- Q2: {fiscal_month_names[(st.session_state.fiscal_year_start + 3) % 12 or 12]}-{fiscal_month_names[(st.session_state.fiscal_year_start + 5) % 12 or 12]}\n- Q3: {fiscal_month_names[(st.session_state.fiscal_year_start + 6) % 12 or 12]}-{fiscal_month_names[(st.session_state.fiscal_year_start + 8) % 12 or 12]}\n- Q4: {fiscal_month_names[(st.session_state.fiscal_year_start + 9) % 12 or 12]}-{fiscal_month_names[(st.session_state.fiscal_year_start + 11) % 12 or 12]}"
    )

    st.divider()
    if st.button("Reset Column Mapping"):
        st.session_state.colmap_confirmed = False
        st.session_state.colmap = {}
        clear_saved_colmap()
        st.success("Mapping reset.")
        st.rerun()

    st.divider()
    st.write("### 🧪 Generate Sample Data")
    if st.button("Create Test Data", help="Generate realistic sample data matching your format"):
        np.random.seed(42)

        sites_data = [
            ("BAE Fylde", "409da202-a40f-4e35-b5a7-10fcb5cf0e5c", 9632),
            ("Blachford", "61776740-0653-4935-9812-41ba6439f9cf", 333),
            ("City Football Group Phase 1", "83758805-a993-4837-a9a5-74f8b16bb301", 2206),
            ("Solar Farm A", "12345678-1234-1234-1234-123456789abc", 5000),
            ("Industrial Park B", "87654321-4321-4321-4321-cba987654321", 1500),
        ]

        months = [
            "Jan-2025",
            "Feb-2025",
            "Mar-2025",
            "Apr-2025",
            "May-2025",
            "Jun-2025",
            "Jul-2025",
            "Aug-2025",
            "Sep-2025",
            "Oct-2025",
            "Nov-2025",
            "Dec-2025",
        ]

        data: List[dict] = []
        for site_name, site_id, kwp in sites_data:
            for i, month in enumerate(months):
                seasonal_factor = 0.6 + 0.4 * np.sin((i - 2) * np.pi / 6)
                kwh_per_kwp = 25 + 60 * seasonal_factor
                forecast_gen = kwp * kwh_per_kwp * np.random.uniform(0.95, 1.05)
                forecast_pr = np.random.uniform(80, 85)
                actual_irr = np.random.uniform(2.5, 5.5) * seasonal_factor
                irradiance_gen = forecast_gen * np.random.uniform(0.90, 1.10)
                actual_pr = forecast_pr - np.random.uniform(0.5, 5)
                availability = np.random.uniform(95, 100)
                actual_gen = irradiance_gen * (actual_pr / forecast_pr) * (availability / 100)
                gen_dev_pct = ((actual_gen / forecast_gen) - 1) * 100
                irr_losses = irradiance_gen - forecast_gen
                pr_dev_pct = actual_pr - forecast_pr
                net_usage = actual_gen * np.random.uniform(0.97, 0.99)
                calculated_exp = actual_gen

                data.append(
                    {
                        "Site": site_name,
                        "SiteID": site_id,
                        "kWp": kwp,
                        "Date": month,
                        "Actual Gen (kWh)": f"{actual_gen:,.2f}",
                        "Forecast Gen (kWh)": f"{forecast_gen:,.2f}",
                        "Gen Dev. (%)": f"{gen_dev_pct:.2f}%",
                        "kWh/kWp": f"{actual_gen/kwp:.0f}",
                        "Calculated Exp (kWh)": f"{calculated_exp:,.2f}",
                        "Net Usage (kWh)": f"{net_usage:,.2f}",
                        "Actual Irr (kWh/m2)": f"{actual_irr:.2f}",
                        "Irradiance-based generation": f"{irradiance_gen:,.2f}",
                        "Irr Losses (kWh)": f"{irr_losses:,.0f}",
                        "Actual PR (%)": f"{actual_pr:.1f}",
                        "Forecast PR (%)": f"{forecast_pr:.1f}",
                        "PR Dev. (%)": f"{pr_dev_pct:.1f}%",
                        "PR Gen Loss (kWh)": "",
                        "Availability (%)": f"{availability:.1f}",
                    }
                )

        df_sample = pd.DataFrame(data)
        ok, msg = extractor.extract_from_df(df_sample, "sample_solar_data", "replace")

        if ok:
            st.success("? Sample data created!\nTable: 'sample_solar_data'\n60 rows (5 sites  12 months)")
            st.info(
                " Format matches your data structure:\n- Sites with SiteIDs\n- Monthly data with Date\n- Actual, Forecast, Irradiance-based generation\n- PR and Availability metrics"
            )
        else:
            st.error(msg)

    st.divider()
    st.write("###  Tables")
    tables = extractor.list_tables()
    if tables:
        for t in tables:
            st.write(f" {t}")
    else:
        st.write("*No tables yet*")


def render_upload_tab(tab, extractor: SolarDataExtractor):
    with tab:
        st.header("📤 Upload Data")
        show_debug = st.checkbox(" Show Debug Info", value=False, help="Display detailed debugging information")

        tables = extractor.list_tables()
        with st.expander("Current Database Status", expanded=False):
            st.write(f"**Database:** `{st.session_state.db_name}`")
            st.write(f"**Database Path:** `{extractor.db_name}`")
            st.write(f"**Connection:** `{extractor._conn}`")
            st.write(f"**Tables:** {len(tables)}")
            if tables:
                for tbl in tables:
                    ok, df_count = extractor.query_data(f"SELECT COUNT(*) as count FROM {tbl}")
                    if ok and not isinstance(df_count, str) and not df_count.empty:
                        count = df_count.iloc[0]["count"]
                        st.write(f"  - `{tbl}`: {count:,} rows")
            else:
                st.write("*No tables in database yet*")

        st.info(" **Quick Start:** Click 'Create Test Data' in the sidebar to generate sample data instantly!")

        uploaded = st.file_uploader("Choose a file (CSV, Excel):", type=["csv", "xlsx", "xls"])
        with st.expander("Download Excel Template"):
            template_df = pd.DataFrame(
                {
                    "Actual Gen (kWh)": [100],
                    "Irradiance-based generation": [110],
                    "Forecast Gen (kWh)": [120],
                    "Actual PR (%)": [90],
                    "Forecast PR (%)": [92],
                    "Availability (%)": [99],
                    "kWp": [10],
                    "Site": ["Site A"],
                    "Date": ["2025-01-01"],
                }
            )
            st.dataframe(template_df, width="stretch")
            template_xlsx = template_df.to_csv(index=False)
            st.download_button("Download CSV Template", template_xlsx, "solar_template.csv", "text/csv")

        st.divider()
        st.subheader("Or Load from Database")
        existing_tables = extractor.list_tables()
        if existing_tables:
            load_table = st.selectbox("Select existing table", [""] + list(existing_tables), key="load_tbl")
            if load_table and st.button("Load Table"):
                ok, df_upload = extractor.query_data(f"SELECT * FROM {load_table}")
                if ok and not isinstance(df_upload, str):
                    st.session_state["loaded_df"] = df_upload
                    st.success(f"Loaded {len(df_upload):,} rows from '{load_table}'")
                    st.rerun()

        df_upload = st.session_state.get("loaded_df", None)

        if uploaded:
            current_file_name = uploaded.name
            last_file_name = st.session_state.get("last_uploaded_file", None)

            if current_file_name != last_file_name:
                st.session_state.colmap_confirmed = False
                st.session_state["last_uploaded_file"] = current_file_name
                for key in ["last_save_status", "last_save_message", "last_save_table"]:
                    st.session_state.pop(key, None)

            if show_debug:
                st.write("** DEBUG: File Upload**")
                st.write(f"- File name: `{uploaded.name}`")
                st.write(f"- File type: `{uploaded.type}`")
                st.write(f"- File size: `{uploaded.size:,} bytes`")
                st.write(f"- Is new file: `{current_file_name != last_file_name}`")

            try:
                if uploaded.name.endswith(".csv"):
                    df_upload = pd.read_csv(uploaded)
                    if show_debug:
                        st.write(f"- Loaded as CSV")
                else:
                    df_upload = pd.read_excel(uploaded)
                    if show_debug:
                        st.write(f"- Loaded as Excel")

                if show_debug:
                    st.write(f"- Raw shape: `{df_upload.shape}` (rows  columns)")
                    st.write(f"- Raw columns: `{list(df_upload.columns)}`")

                df_upload = DataProcessor.clean_uploaded_data(df_upload)

                if show_debug:
                    st.write(f"- Cleaned columns: `{list(df_upload.columns)}`")
                    st.write(f"- Data types: `{df_upload.dtypes.to_dict()}`")

                required_cols = [
                    "Actual Gen (kWh)",
                    "Irradiance-based generation",
                    "Forecast Gen (kWh)",
                    "Actual PR (%)",
                    "Forecast PR (%)",
                    "Availability (%)",
                    "kWp",
                    "Site",
                    "Date",
                ]
                missing_cols = [col for col in required_cols if col not in df_upload.columns]
                if missing_cols:
                    st.warning(
                        f"Missing columns in uploaded file: {', '.join(missing_cols)}. Please use the template format."
                    )
                    if show_debug:
                        st.write(f"- Missing required columns: `{missing_cols}`")

                st.session_state["loaded_df"] = df_upload
                st.session_state["df_ready"] = df_upload

                if show_debug:
                    st.write(f"- Stored in session state: `loaded_df`, `df_ready`")

                st.success(
                    f"? File '{uploaded.name}' loaded ({len(df_upload):,} rows). Please confirm column mapping below."
                )
            except Exception as e:
                st.error(f"Error loading file: {e}")
                st.exception(e)
                if show_debug:
                    import traceback

                    st.write("** DEBUG: Exception Details**")
                    st.code(traceback.format_exc())

        if df_upload is not None:
            df_upload = DataProcessor.clean_uploaded_data(df_upload)
            st.session_state["df_ready"] = df_upload

            st.dataframe(df_upload.head(), width="stretch")

            mapping_error = None
            if not st.session_state.get("colmap_confirmed", False):
                st.divider()
                st.subheader("Column Mapping")
                st.info(
                    """
            **Your Data Format Detected:** Standard solar monitoring export
            - Actual Gen (kWh) = Metered generation
            - Irradiance-based generation = Weather-adjusted expectation (WAB)
            - Forecast Gen (kWh) = Original budget/forecast
            - Actual PR (%) and Forecast PR (%) = Performance ratios
            - Availability (%) = System uptime
            """
                )
                detected = detect_column_candidates(tuple(df_upload.columns))

                if show_debug:
                    st.write("** DEBUG: Column Detection**")
                    st.write(f"- Available columns: `{list(df_upload.columns)}`")
                    st.write(f"- Detected mappings: `{detected}`")

                cols_list = list(df_upload.columns)

                def safe_idx(name):
                    try:
                        idx = cols_list.index(name) + 1 if name else 0
                        if show_debug and name:
                            st.write(f"  - Mapping '{name}' to index {idx}")
                        return idx
                    except ValueError:
                        if show_debug:
                            st.write(f"  - Column '{name}' not found, using index 0")
                        return 0

                col1, col2 = st.columns(2)
                with col1:
                    st.session_state.colmap["actual_gen"] = st.selectbox(
                        "Actual Generation (Metered)",
                        [None] + cols_list,
                        index=safe_idx(detected.get("actual_gen")),
                        help="Actual metered generation in kWh",
                    )
                    st.session_state.colmap["wab"] = st.selectbox(
                        "Weather-Adjusted Budget (Irradiance-based)",
                        [None] + cols_list,
                        index=safe_idx(detected.get("wab")),
                        help="Expected generation based on actual irradiance",
                    )
                    st.session_state.colmap["budget_gen"] = st.selectbox(
                        "Budget/Forecast Generation",
                        [None] + cols_list,
                        index=safe_idx(detected.get("budget_gen")),
                        help="Original P50/forecast generation",
                    )
                    st.session_state.colmap["date"] = st.selectbox(
                        "Date Column", [None] + cols_list, index=safe_idx(detected.get("date"))
                    )
                    st.session_state.colmap["site"] = st.selectbox(
                        "Site Column", [None] + cols_list, index=safe_idx(detected.get("site"))
                    )
                with col2:
                    st.session_state.colmap["pr_actual"] = st.selectbox(
                        "Actual PR (%)", [None] + cols_list, index=safe_idx(detected.get("pr_actual"))
                    )
                    st.session_state.colmap["pr_budget"] = st.selectbox(
                        "Budget/Forecast PR (%)", [None] + cols_list, index=safe_idx(detected.get("pr_budget"))
                    )
                    st.session_state.colmap["availability"] = st.selectbox(
                        "Availability (%)", [None] + cols_list, index=safe_idx(detected.get("availability"))
                    )
                    st.session_state.colmap["capacity"] = st.selectbox(
                        "Capacity (kWp)",
                        [None] + cols_list,
                        index=safe_idx(detected.get("capacity")),
                        help="Installed capacity for yield calculation",
                    )

                if show_debug:
                    st.write("** DEBUG: Before Confirm Mapping Button**")
                    st.write(f"- About to show Confirm Mapping button")
                    st.write(f"- Current colmap: `{st.session_state.colmap}`")

                st.divider()

                if not st.session_state.get("show_mapping_summary", False):
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button(
                            " Review Mapping",
                            help="Review your column mappings before saving",
                            use_container_width=True,
                        ):
                            st.session_state["show_mapping_summary"] = True
                            st.rerun()
                    with col2:
                        if st.button(
                            "? Confirm & Save",
                            type="primary",
                            help="Confirm mappings and save to database immediately",
                            use_container_width=True,
                        ):
                            st.session_state["show_mapping_summary"] = False
                            st.session_state["proceed_with_save"] = True
                            st.rerun()
                if st.session_state.get("show_mapping_summary", False):
                    st.divider()
                    st.write("**Mapping Summary:**")
                    mapping_df = pd.DataFrame(
                        [
                            {
                                "Field": "Actual Generation",
                                "Mapped To": st.session_state.colmap.get("actual_gen", "Not set"),
                            },
                            {
                                "Field": "Weather-Adjusted Budget",
                                "Mapped To": st.session_state.colmap.get("wab", "Not set"),
                            },
                            {
                                "Field": "Budget Generation",
                                "Mapped To": st.session_state.colmap.get("budget_gen", "Not set"),
                            },
                            {"Field": "Actual PR", "Mapped To": st.session_state.colmap.get("pr_actual", "Not set")},
                            {"Field": "Budget PR", "Mapped To": st.session_state.colmap.get("pr_budget", "Not set")},
                            {
                                "Field": "Availability",
                                "Mapped To": st.session_state.colmap.get("availability", "Not set"),
                            },
                            {
                                "Field": "Capacity (kWp)",
                                "Mapped To": st.session_state.colmap.get("capacity", "Not set"),
                            },
                            {"Field": "Site", "Mapped To": st.session_state.colmap.get("site", "Not set")},
                            {"Field": "Date", "Mapped To": st.session_state.colmap.get("date", "Not set")},
                        ]
                    )
                    st.dataframe(mapping_df, width="stretch", hide_index=True)

                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button(" Back to Edit", use_container_width=True):
                            st.session_state["show_mapping_summary"] = False
                            st.rerun()
                    with col2:
                        if st.button("? Confirm & Save", type="primary", use_container_width=True):
                            st.session_state["show_mapping_summary"] = False
                            st.session_state["proceed_with_save"] = True
                            st.rerun()

                if st.session_state.get("proceed_with_save", False):
                    st.session_state["proceed_with_save"] = False

                    if show_debug:
                        st.write("** DEBUG: Mapping Confirmation**")
                        st.write(f"- Current colmap: `{st.session_state.colmap}`")

                    required = ["actual_gen", "wab", "budget_gen"]
                    missing = [k for k in required if not st.session_state.colmap.get(k)]

                    if show_debug:
                        st.write(f"- Required fields: `{required}`")
                        st.write(f"- Missing fields: `{missing}`")

                    if missing:
                        st.error(f"Please map required fields: {', '.join(missing)}")
                        mapping_error = True
                    else:
                        st.session_state.colmap_confirmed = True
                        st.session_state["df_ready"] = df_upload

                        if show_debug:
                            st.write(f"- Mapping confirmed: `True`")
                            st.write(f"- df_ready shape: `{df_upload.shape}`")
                            st.write(f"- df_ready columns: `{list(df_upload.columns)}`")

                        table_name = "solar_data"
                        mode = "replace"

                        if show_debug:
                            st.write(f"- Attempting to save to table: `{table_name}`")
                            st.write(f"- Save mode: `{mode}`")
                            st.write(f"- Database: `{st.session_state.db_name}`")
                            st.write(f"- extractor object: `{extractor}`")
                            st.write(f"- extractor.db_name: `{extractor.db_name}`")
                            st.write(f"- extractor._conn: `{extractor._conn}`")

                        try:
                            ok, msg = extractor.extract_from_df(df_upload, table_name, mode, debug=show_debug)

                            if show_debug:
                                st.write(f"- Save result: `ok={ok}`")
                                st.write(f"- Save message: `{msg}`")
                                tables_after = extractor.list_tables()
                                st.write(f"- Tables after save: `{list(tables_after)}`")

                            if ok:
                                st.session_state["last_save_status"] = "success"
                                st.session_state["last_save_message"] = msg
                                st.session_state["last_save_table"] = table_name
                                st.success(f"? Mapping confirmed and data saved! {msg}")
                            else:
                                st.session_state["last_save_status"] = "error"
                                st.session_state["last_save_message"] = msg
                                st.error(f"Mapping confirmed but save failed: {msg}")
                        except Exception as e:
                            st.session_state["last_save_status"] = "error"
                            st.session_state["last_save_message"] = str(e)
                            st.error(f"Mapping confirmed but error saving to database: {e}")
                            if show_debug:
                                import traceback

                                st.write("** DEBUG: Save Exception**")
                                st.code(traceback.format_exc())

                        st.rerun()

            show_save_ui = st.session_state.get("colmap_confirmed", False)

            if show_debug:
                st.write("** DEBUG: Save UI Logic**")
                st.write(f"- colmap_confirmed: `{st.session_state.get('colmap_confirmed', False)}`")
                st.write(f"- show_save_ui: `{show_save_ui}`")

            if not show_save_ui:
                if st.button(
                    "Show Save UI (manual override)", help="If you have mapped columns and want to save, click here."
                ):
                    show_save_ui = True
            if show_save_ui:
                st.divider()

                if st.session_state.get("last_save_status") == "success":
                    st.success(f"? **Data Successfully Saved!** {st.session_state.get('last_save_message', '')}")

                    saved_table = st.session_state.get("last_save_table", "solar_data")
                    ok, df_verify = extractor.query_data(f"SELECT COUNT(*) as row_count FROM {saved_table}")
                    if ok and not isinstance(df_verify, str) and not df_verify.empty:
                        row_count = df_verify.iloc[0]["row_count"]
                        st.info(f" **Verification:** Table '{saved_table}' contains {row_count:,} rows in database")

                        if show_debug:
                            st.write("** DEBUG: Database Verification**")
                            st.write(f"- Query result: `{df_verify.to_dict()}`")
                            st.write(f"- Tables in database: `{list(extractor.list_tables())}`")

                    if st.button("Clear Status Message"):
                        for key in ["last_save_status", "last_save_message", "last_save_table"]:
                            st.session_state.pop(key, None)
                        st.rerun()

                elif st.session_state.get("last_save_status") == "error":
                    st.error(f"? **Save Failed:** {st.session_state.get('last_save_message', 'Unknown error')}")
                    if st.button("Clear Error Message"):
                        for key in ["last_save_status", "last_save_message"]:
                            st.session_state.pop(key, None)
                        st.rerun()

                st.info(" Use the options below to save again with a different table name or mode.")
                table_name = st.text_input("Table Name", "solar_data")
                mode = st.radio("Save Mode", ["replace", "append"], horizontal=True)
                df_to_save = st.session_state.get("df_ready", df_upload)
                required_cols = [
                    st.session_state.colmap.get("actual_gen"),
                    st.session_state.colmap.get("wab"),
                    st.session_state.colmap.get("budget_gen"),
                ]
                missing_cols = [col for col in required_cols if col not in df_to_save.columns]
                if missing_cols:
                    st.warning(
                        f"Warning: The following mapped columns are missing in your data and may cause errors: {', '.join([str(c) for c in missing_cols])}"
                    )
                if st.button(" Save to Database", type="primary"):
                    if show_debug:
                        st.write("** DEBUG: Manual Save**")
                        st.write(f"- Table name: `{table_name}`")
                        st.write(f"- Mode: `{mode}`")
                        st.write(f"- df_to_save shape: `{df_to_save.shape if df_to_save is not None else 'None'}`")

                    if df_to_save is None or df_to_save.empty:
                        st.error("No data available to save. Please upload or load a table first.")
                    else:
                        try:
                            ok, msg = extractor.extract_from_df(df_to_save, table_name, mode, debug=show_debug)
                            if ok:
                                st.success(msg)
                            else:
                                st.error(msg)
                        except Exception as e:
                            st.error(f"Error saving to database: {e}")
                            if show_debug:
                                import traceback

                                st.write("** DEBUG: Save Exception**")
                                st.code(traceback.format_exc())


def render_query_tab(tab, extractor: SolarDataExtractor):
    with tab:
        st.header("🔍 SQL Query")

        tables = extractor.list_tables()
        if not tables:
            st.warning("No tables available. Upload data first.")
        else:
            quick_table = st.selectbox("Quick select table", [""] + list(tables))
            if quick_table:
                st.code(f"SELECT * FROM {quick_table} LIMIT 100", language="sql")

            query = st.text_area("SQL Query", height=150, value="SELECT * FROM solar_data LIMIT 100")

            if st.button(" Run Query", type="primary"):
                ok, result = extractor.query_data(query)
                if ok and not isinstance(result, str):
                    st.success(f"Query returned {len(result):,} rows")
                    st.dataframe(result, width="stretch")

                    csv = result.to_csv(index=False)
                    st.download_button(" Download CSV", csv, "query_result.csv", "text/csv")
                else:
                    st.error(f"Query error: {result}")


def render_tables_tab(tab, extractor: SolarDataExtractor):
    with tab:
        st.header("📊 Manage Tables")

        tables = extractor.list_tables()
        if not tables:
            st.info("No tables in database yet.")
        else:
            selected_table = st.selectbox("Select table to manage", list(tables), key="tab3_table_select")

            if selected_table:
                ok, df_table = extractor.query_data(f"SELECT * FROM {selected_table}")

                if ok and not isinstance(df_table, str) and not df_table.empty:
                    table_tab1, table_tab2, table_tab3, table_tab4 = st.tabs(["? View", " Pivot", " Edit", "? Delete"])

                    with table_tab1:
                        st.subheader(f"📋 {selected_table}")
                        st.write(f"**Rows:** {len(df_table):,} | **Columns:** {len(df_table.columns)}")

                        with st.expander(" Search & Filter"):
                            search_col = st.selectbox(
                                "Search in column", ["All"] + list(df_table.columns), key="search_col"
                            )
                            search_term = st.text_input("Search term", key="search_term")

                            if search_term:
                                if search_col == "All":
                                    mask = (
                                        df_table.astype(str)
                                        .apply(lambda x: x.str.contains(search_term, case=False, na=False))
                                        .any(axis=1)
                                    )
                                else:
                                    mask = (
                                        df_table[search_col].astype(str).str.contains(search_term, case=False, na=False)
                                    )
                                df_table = df_table[mask]
                                st.info(f"Found {len(df_table)} matching rows")

                        st.dataframe(df_table, width="stretch", height=400)

                        csv = df_table.to_csv(index=False)
                        st.download_button(" Download CSV", csv, f"{selected_table}.csv", "text/csv")

                    with table_tab2:
                        st.subheader("🔄 Pivot Table")

                        col_pivot1, col_pivot2, col_pivot3 = st.columns(3)

                        with col_pivot1:
                            st.write("**Rows**")
                            pivot_rows = st.multiselect(
                                "Group by (rows)",
                                df_table.columns.tolist(),
                                key="pivot_rows",
                                help="Categories to show as rows",
                            )

                        with col_pivot2:
                            st.write("**Columns**")
                            pivot_cols = st.multiselect(
                                "Split by (columns)",
                                [c for c in df_table.columns if c not in pivot_rows],
                                key="pivot_cols",
                                help="Categories to show as columns",
                            )

                        with col_pivot3:
                            st.write("**Values**")
                            numeric_cols = df_table.select_dtypes(include=[np.number]).columns.tolist()
                            pivot_values = st.multiselect("Aggregate (values)", numeric_cols, key="pivot_values")
                            pivot_agg = st.selectbox(
                                "Aggregation", ["sum", "mean", "count", "min", "max", "std"], key="pivot_agg"
                            )

                        if st.button(" Generate Pivot", key="generate_pivot"):
                            if not pivot_rows:
                                st.warning("Please select at least one row grouping")
                            elif not pivot_values:
                                st.warning("Please select at least one value to aggregate")
                            else:
                                try:
                                    if pivot_cols:
                                        pivot_result = pd.pivot_table(
                                            df_table,
                                            values=pivot_values,
                                            index=pivot_rows,
                                            columns=pivot_cols,
                                            aggfunc=pivot_agg,
                                            fill_value=0,
                                        )
                                    else:
                                        pivot_result = df_table.groupby(pivot_rows)[pivot_values].agg(pivot_agg)

                                    st.session_state["pivot_result"] = pivot_result
                                    st.success(
                                        f"Pivot table created: {pivot_result.shape[0]} rows  {pivot_result.shape[1]} columns"
                                    )
                                except Exception as e:
                                    st.error(f"Pivot error: {e}")

                        if "pivot_result" in st.session_state:
                            pivot_result = st.session_state["pivot_result"]

                            st.divider()

                            if len(pivot_values) == 1:
                                styled_pivot = pivot_result.style.background_gradient(cmap="RdYlGn", axis=None)
                                st.dataframe(styled_pivot, width="stretch")
                            else:
                                st.dataframe(pivot_result, width="stretch")

                            col_piv1, col_piv2 = st.columns(2)
                            with col_piv1:
                                csv_pivot = pivot_result.to_csv()
                                st.download_button(
                                    " Download Pivot CSV", csv_pivot, f"{selected_table}_pivot.csv", "text/csv"
                                )

                            with col_piv2:
                                save_pivot_name = st.text_input(
                                    "Save pivot as", f"{selected_table}_pivot", key="save_pivot_name"
                                )
                                if st.button(" Save Pivot to DB", key="save_pivot_btn"):
                                    pivot_flat = pivot_result.reset_index()
                                    ok, msg = extractor.extract_from_df(pivot_flat, save_pivot_name, "replace")
                                    if ok:
                                        st.success(msg)
                                    else:
                                        st.error(msg)
                    with table_tab3:
                        st.subheader("✏️ Edit Table Data")

                        st.warning(" Changes are permanent and cannot be undone. Use with caution!")

                        edit_mode = st.radio(
                            "Edit mode", ["Add Row", "Update Rows", "Delete Rows"], horizontal=True, key="edit_mode"
                        )

                        if edit_mode == "Add Row":
                            st.write("**Add New Row**")
                            new_row = {}

                            num_cols = 3
                            cols = st.columns(num_cols)
                            for idx, col in enumerate(df_table.columns):
                                with cols[idx % num_cols]:
                                    dtype = df_table[col].dtype
                                    if dtype in ["int64", "float64"]:
                                        new_row[col] = st.number_input(f"{col}", key=f"add_{col}")
                                    elif dtype == "bool":
                                        new_row[col] = st.checkbox(f"{col}", key=f"add_{col}")
                                    else:
                                        new_row[col] = st.text_input(f"{col}", key=f"add_{col}")

                            if st.button("? Add Row", type="primary", key="btn_add_row"):
                                new_df = pd.concat([df_table, pd.DataFrame([new_row])], ignore_index=True)
                                ok, msg = extractor.extract_from_df(new_df, selected_table, "replace")
                                if ok:
                                    st.success("Row added successfully!")
                                    st.rerun()
                                else:
                                    st.error(msg)

                        elif edit_mode == "Update Rows":
                            st.write("**Update Existing Rows**")

                            if len(df_table) > 0:
                                row_index = st.number_input(
                                    "Row number to edit", min_value=0, max_value=len(df_table) - 1, key="update_row_idx"
                                )

                                st.write(f"**Current values for row {row_index}:**")
                                current_row = df_table.iloc[row_index]
                                st.json(current_row.to_dict())

                                st.write("**New values:**")
                                updated_row = {}
                                num_cols = 3
                                cols = st.columns(num_cols)

                                for idx, col in enumerate(df_table.columns):
                                    with cols[idx % num_cols]:
                                        dtype = df_table[col].dtype
                                        current_val = current_row[col]

                                        if dtype in ["int64", "float64"]:
                                            updated_row[col] = st.number_input(
                                                f"{col}", value=float(current_val), key=f"upd_{col}"
                                            )
                                        elif dtype == "bool":
                                            updated_row[col] = st.checkbox(
                                                f"{col}", value=bool(current_val), key=f"upd_{col}"
                                            )
                                        else:
                                            updated_row[col] = st.text_input(
                                                f"{col}", value=str(current_val), key=f"upd_{col}"
                                            )

                                if st.button(" Update Row", type="primary", key="btn_update_row"):
                                    df_table.iloc[row_index] = pd.Series(updated_row)
                                    ok, msg = extractor.extract_from_df(df_table, selected_table, "replace")
                                    if ok:
                                        st.success("Row updated successfully!")
                                        st.rerun()
                                    else:
                                        st.error(msg)

                        elif edit_mode == "Delete Rows":
                            st.write("**Delete Rows by Condition**")

                            del_col = st.selectbox("Column to filter", df_table.columns, key="del_col")
                            del_condition = st.selectbox(
                                "Condition", ["equals", "contains", "greater than", "less than"], key="del_cond"
                            )
                            del_value = st.text_input("Value", key="del_value")

                            if st.button(" Preview Rows to Delete", key="preview_delete"):
                                try:
                                    if del_condition == "equals":
                                        mask = df_table[del_col].astype(str) == del_value
                                    elif del_condition == "contains":
                                        mask = (
                                            df_table[del_col].astype(str).str.contains(del_value, case=False, na=False)
                                        )
                                    elif del_condition == "greater than":
                                        mask = df_table[del_col] > float(del_value)
                                    else:
                                        mask = df_table[del_col] < float(del_value)

                                    rows_to_delete = df_table[mask]
                                    st.session_state["rows_to_delete"] = rows_to_delete
                                    st.session_state["delete_mask"] = mask

                                    st.warning(f" {len(rows_to_delete)} rows will be deleted:")
                                    st.dataframe(rows_to_delete, width="stretch")
                                except Exception as e:
                                    st.error(f"Filter error: {e}")

                            if "rows_to_delete" in st.session_state and len(st.session_state["rows_to_delete"]) > 0:
                                st.divider()
                                confirm = st.checkbox("I understand this action cannot be undone", key="confirm_delete")
                                if confirm and st.button("? Delete Rows", type="primary", key="btn_delete_rows"):
                                    df_remaining = df_table[~st.session_state["delete_mask"]]
                                    ok, msg = extractor.extract_from_df(df_remaining, selected_table, "replace")
                                    if ok:
                                        st.success(f"Deleted {len(st.session_state['rows_to_delete'])} rows!")
                                        st.session_state.pop("rows_to_delete", None)
                                        st.session_state.pop("delete_mask", None)
                                        st.rerun()
                                    else:
                                        st.error(msg)

                    with table_tab4:
                        st.subheader("🗑️ Delete Table")
                        st.error(f" This will permanently delete the entire table: **{selected_table}**")

                        confirm_table_name = st.text_input(
                            "Type table name to confirm deletion:", key="confirm_table_del"
                        )

                        if confirm_table_name == selected_table:
                            if st.button("? Delete Table Permanently", type="primary", key="btn_delete_table"):
                                ok, msg = extractor.delete_table(selected_table)
                                if ok:
                                    st.success(msg)
                                    st.rerun()
                                else:
                                    st.error(msg)
                        elif confirm_table_name:
                            st.warning("Table name doesn't match. Please type the exact name.")
                else:
                    st.error("Could not load table data.")

        st.divider()
        st.write("###  Database Statistics")
        if tables:
            stats_data = []
            for tbl in tables:
                ok, df_stat = extractor.query_data(f"SELECT COUNT(*) as count FROM {tbl}")
                if ok and not isinstance(df_stat, str):
                    count = df_stat["count"].iloc[0]
                    stats_data.append({"Table": tbl, "Rows": f"{count:,}"})

            st.dataframe(pd.DataFrame(stats_data), width="stretch", hide_index=True)


def render_kpi_tab(tab, extractor: SolarDataExtractor):
    with tab:
        st.header("📈 KPI Dashboard: Monthly, QTD, YTD, Total")
        tables = extractor.list_tables()
        if not tables:
            st.warning("No tables available. Upload or create data first.")
        else:
            kpi_tbl = st.selectbox("Select Table for KPIs", tables, key="kpi_tbl")
            ok, df_kpi = extractor.query_data(f"SELECT * FROM {kpi_tbl}")
            if not ok or isinstance(df_kpi, str) or df_kpi.empty:
                st.error("Could not load data or table is empty.")
            else:
                date_cols = [c for c in df_kpi.columns if "date" in c.lower() or "period" in c.lower()]
                if not date_cols:
                    st.warning("No date/period column found for period aggregation.")
                else:
                    date_col = st.selectbox("Date/Period Column", date_cols, key="kpi_date_col")
                    period_type = st.selectbox(
                        "Aggregate by", ["Monthly", "Quarterly (QTD)", "YTD", "Total"], key="kpi_period"
                    )
                    period_map = {"Monthly": "Monthly", "Quarterly (QTD)": "Quarterly", "YTD": "YTD", "Total": None}
                    time_period = period_map[period_type]
                    metrics = [c for c in df_kpi.columns if pd.api.types.is_numeric_dtype(df_kpi[c])]
                    colmap = st.session_state.get("colmap", {})
                    kpi_df = aggregate_flexible(df_kpi, date_col, [], time_period, metrics, colmap)
                    kpi_df = format_percent_like(kpi_df)
                    for col in kpi_df.columns:
                        if col.lower() in ["period", "month"] or (
                            kpi_df[col].dtype == "O"
                            and kpi_df[col].astype(str).str.match(r"\d{4}-\d{2}(-\d{2})?$").any()
                        ):
                            try:
                                kpi_df[col] = pd.to_datetime(kpi_df[col], errors="coerce").dt.strftime("%b-%y")
                            except Exception:
                                pass
                    num_cols = kpi_df.select_dtypes(include=[float, int]).columns
                    non_pct_cols = [c for c in num_cols if "pr" not in c.lower() and "avail" not in c.lower()]
                    kpi_df[non_pct_cols] = kpi_df[non_pct_cols].round(2)

                    st.subheader(f"📈 KPIs by {period_type}")
                    st.dataframe(kpi_df, width="stretch")
                    st.download_button(
                        "Download KPIs (CSV)", kpi_df.to_csv(index=False), f"kpi_{period_type.lower()}.csv", "text/csv"
                    )


def render_calculations_tab(tab, extractor: SolarDataExtractor):
    with tab:
        st.header("🧮 Budget Variance & Technical Losses")

        tables = extractor.list_tables()
        if not tables:
            st.warning("Upload data first.")
        else:
            calc_tbl = st.selectbox("Source Table", list(tables), key="t5_sel")
            ok, df_raw = extractor.query_data(f"SELECT * FROM {calc_tbl}")

            if ok and not isinstance(df_raw, str) and not df_raw.empty:
                ensure_colmap_from_df(df_raw)

            if ok and not isinstance(df_raw, str) and not df_raw.empty and st.session_state.colmap_confirmed:
                st.write("**Active Mapping:**", st.session_state.colmap)

                session_key = f"res_{calc_tbl}"

                if st.button(" Run Calculations", type="primary"):
                    with st.spinner("Computing losses and variances..."):
                        try:
                            analyzer = SolarDataAnalyzer(df_raw, st.session_state.colmap)
                            res = analyzer.compute_losses()
                            # Round numeric results to 2 decimal places for display/saving
                            res = format_percent_like(res)
                            num_cols = res.select_dtypes(include=["float", "int"]).columns
                            non_pr_cols = [c for c in num_cols if "pr" not in c.lower() and "avail" not in c.lower()]
                            res[non_pr_cols] = res[non_pr_cols].round(2)
                            st.session_state[session_key] = res
                            extractor.clear_cache()
                            st.success(f"? Calculations complete! {len(res):,} rows processed.")
                        except ValueError as ve:
                            st.error(f"Validation Error: {ve}")
                        except Exception as e:
                            st.error(f"Calculation Error: {e}")

                if session_key in st.session_state:
                    df_res = st.session_state[session_key]

                    st.divider()
                    st.subheader("📊 Results Preview")

                    show_cols = [
                        "Var_Weather_kWh",
                        "Loss_Total_Tech_kWh",
                        "Loss_PR_kWh",
                        "Loss_Avail_kWh",
                        "Var_PR_pp",
                        "Var_Availability_pp",
                        "Yield_kWh_per_kWp",
                    ]
                    show_cols = [c for c in show_cols if c in df_res.columns]

                    if show_cols:
                        preview_df = df_res[show_cols].head(20).copy()
                        preview_df = format_percent_like(preview_df)
                        num_cols = preview_df.select_dtypes(include=["float", "int"]).columns
                        non_pr_cols = [c for c in num_cols if "pr" not in c.lower() and "avail" not in c.lower()]
                        preview_df[non_pr_cols] = preview_df[non_pr_cols].round(2)
                        st.dataframe(preview_df, width="stretch")

                        st.divider()
                        st.subheader("📈 Flexible Aggregation & Analysis")

                        date_cols = [c for c in df_res.columns if "date" in c.lower() or "time" in c.lower()]
                        if date_cols:
                            with st.expander(" Date Range Filter (Optional)", expanded=False):
                                col_filter1, col_filter2 = st.columns(2)
                                with col_filter1:
                                    use_date_filter = st.checkbox("Enable date filtering", key="use_date_filter")
                                if use_date_filter:
                                    date_col_filter = st.selectbox("Date column", date_cols, key="date_filter_col")
                                    with col_filter1:
                                        start_date = st.date_input("Start date", key="start_date_filter")
                                    with col_filter2:
                                        end_date = st.date_input("End date", key="end_date_filter")

                                    if start_date and end_date:
                                        df_res[date_col_filter] = pd.to_datetime(
                                            df_res[date_col_filter], errors="coerce"
                                        )
                                        mask = (df_res[date_col_filter] >= pd.Timestamp(start_date)) & (
                                            df_res[date_col_filter] <= pd.Timestamp(end_date)
                                        )
                                        df_res = df_res[mask].copy()
                                        st.info(f"Filtered to {len(df_res)} rows between {start_date} and {end_date}")

                        col1, col2, col3 = st.columns(3)

                        with col1:
                            st.write("**Time Period**")
                            time_period = st.selectbox(
                                "Aggregate by",
                                ["None", "Daily", "Weekly", "Monthly", "Quarterly", "YTD", "Annual"],
                                index=3,
                                key="time_agg",
                            )

                            date_cols = [c for c in df_res.columns if "date" in c.lower() or "time" in c.lower()]
                            date_col = None
                            if time_period != "None" and date_cols:
                                date_col = st.selectbox("Date Column", date_cols, key="flex_date")

                        with col2:
                            st.write("**Dimensions**")
                            exclude_patterns = ["loss", "var_", "kwh", "date", "time", "gen", "pr", "avail"]
                            potential_groups = [
                                c
                                for c in df_res.columns
                                if not any(p in c.lower() for p in exclude_patterns) and df_res[c].dtype == "object"
                            ]

                            groupby_cols = st.multiselect(
                                "Group by (select multiple)",
                                potential_groups,
                                help="e.g., Site, Technology, Region, Asset Type",
                                key="flex_groups",
                            )

                        with col3:
                            st.write("**Metrics**")
                            available_metrics = [
                                c for c in df_res.columns if any(x in c for x in ["Loss", "Var_", "gen", "kWh"])
                            ]
                            selected_metrics = st.multiselect(
                                "Select Metrics",
                                available_metrics,
                                default=show_cols[:4] if len(show_cols) >= 4 else show_cols,
                                key="flex_metrics",
                            )
                        if st.button(" Run Aggregation", type="primary", key="run_agg"):
                            if not selected_metrics:
                                st.warning("Please select at least one metric.")
                            else:
                                try:
                                    fiscal_year_start = st.session_state.get(
                                        "fiscal_year_start", Config.DEFAULT_FISCAL_START
                                    )
                                    agg_df = aggregate_flexible(
                                        df_res,
                                        date_col,
                                        groupby_cols,
                                        time_period,
                                        selected_metrics,
                                        st.session_state.colmap,
                                        fiscal_year_start,
                                    )
                                    st.session_state["agg_result"] = agg_df
                                    st.success(f"Aggregated to {len(agg_df)} rows!")
                                except Exception as e:
                                    st.error(f"Aggregation error: {e}")

                        if "agg_result" in st.session_state:
                            st.divider()
                            agg_result = st.session_state["agg_result"]

                            with st.expander(" Filter Aggregated Results", expanded=False):
                                filter_col1, filter_col2 = st.columns(2)
                                with filter_col1:
                                    numeric_cols = agg_result.select_dtypes(include=[np.number]).columns.tolist()
                                    if numeric_cols:
                                        filter_metric = st.selectbox(
                                            "Filter by metric", ["None"] + numeric_cols, key="filter_metric"
                                        )
                                        if filter_metric != "None":
                                            filter_condition = st.selectbox(
                                                "Condition", ["Greater than", "Less than", "Between"], key="filter_cond"
                                            )
                                            if filter_condition == "Between":
                                                col_a, col_b = st.columns(2)
                                                with col_a:
                                                    min_val = st.number_input(
                                                        "Min value",
                                                        value=float(agg_result[filter_metric].min()),
                                                        key="filter_min",
                                                    )
                                                with col_b:
                                                    max_val = st.number_input(
                                                        "Max value",
                                                        value=float(agg_result[filter_metric].max()),
                                                        key="filter_max",
                                                    )
                                                agg_result = agg_result[
                                                    (agg_result[filter_metric] >= min_val)
                                                    & (agg_result[filter_metric] <= max_val)
                                                ]
                                            else:
                                                threshold = st.number_input(
                                                    "Threshold",
                                                    value=float(agg_result[filter_metric].mean()),
                                                    key="filter_thresh",
                                                )
                                                if filter_condition == "Greater than":
                                                    agg_result = agg_result[agg_result[filter_metric] > threshold]
                                                else:
                                                    agg_result = agg_result[agg_result[filter_metric] < threshold]
                                            st.info(f"Filtered to {len(agg_result)} rows")

                                with filter_col2:
                                    if numeric_cols:
                                        topn_metric = st.selectbox(
                                            "Rank by", ["None"] + numeric_cols, key="topn_metric"
                                        )
                                        if topn_metric != "None":
                                            topn_type = st.radio(
                                                "Show", ["Top N", "Bottom N"], horizontal=True, key="topn_type"
                                            )
                                            n_value = st.number_input(
                                                "N",
                                                min_value=1,
                                                max_value=len(agg_result),
                                                value=min(5, len(agg_result)),
                                                key="topn_n",
                                            )
                                            if topn_type == "Top N":
                                                agg_result = agg_result.nlargest(n_value, topn_metric)
                                            else:
                                                agg_result = agg_result.nsmallest(n_value, topn_metric)

                            agg_display = format_percent_like(agg_result)
                            num_cols = agg_display.select_dtypes(include=["float", "int"]).columns
                            non_pr_cols = [c for c in num_cols if "pr" not in c.lower() and "avail" not in c.lower()]
                            agg_display[non_pr_cols] = agg_display[non_pr_cols].round(2)
                            st.dataframe(
                                agg_display.style.background_gradient(
                                    subset=[c for c in agg_display.columns if "Var_" in c or "Loss_" in c],
                                    cmap="RdYlGn_r",
                                ),
                                width="stretch",
                            )

                            if len(agg_result) > 0:
                                st.subheader("🎯 Key Performance Indicators")

                                metric_cols = st.columns(5)

                                with metric_cols[0]:
                                    if "Var_PR_pp" in agg_result.columns:
                                        avg_pr_var = agg_result["Var_PR_pp"].mean()
                                        st.metric(
                                            "Avg PR Variance",
                                            f"{avg_pr_var:.2f} pp",
                                            delta=(
                                                f"{-avg_pr_var:.2f} pp"
                                                if avg_pr_var > 0
                                                else f"+{abs(avg_pr_var):.2f} pp"
                                            ),
                                            delta_color="inverse",
                                            help="Positive = Underperformance",
                                        )

                                with metric_cols[1]:
                                    if "Var_Availability_pp" in agg_result.columns:
                                        avg_avail_var = agg_result["Var_Availability_pp"].mean()
                                        st.metric(
                                            "Avg Avail Variance",
                                            f"{avg_avail_var:.2f} pp",
                                            delta=(
                                                f"{-avg_avail_var:.2f} pp"
                                                if avg_avail_var > 0
                                                else f"+{abs(avg_avail_var):.2f} pp"
                                            ),
                                            delta_color="inverse",
                                            help="99% target - Positive = Below target",
                                        )

                                with metric_cols[2]:
                                    if "Loss_Total_Tech_kWh" in agg_result.columns:
                                        total_tech_loss = agg_result["Loss_Total_Tech_kWh"].sum()
                                        st.metric(
                                            "Total Tech Loss",
                                            f"{total_tech_loss:,.0f} kWh",
                                            help="WAB - Actual Generation",
                                        )

                                with metric_cols[3]:
                                    if "Yield_kWh_per_kWp" in agg_result.columns:
                                        avg_yield = agg_result["Yield_kWh_per_kWp"].mean()
                                        st.metric(
                                            "Avg Yield",
                                            f"{avg_yield:.1f} kWh/kWp",
                                            help="Average specific yield across portfolio",
                                        )

                                with metric_cols[4]:
                                    if "Var_Weather_kWh" in agg_result.columns:
                                        total_weather = agg_result["Var_Weather_kWh"].sum()
                                        st.metric(
                                            "Weather Variance",
                                            f"{total_weather:,.0f} kWh",
                                            delta="favorable" if total_weather > 0 else "unfavorable",
                                            help="WAB - Budget (Positive = Better weather)",
                                        )

                            st.divider()
                            st.subheader("📊 Visualization")

                            viz_col1, viz_col2 = st.columns(2)

                            with viz_col1:
                                if len(groupby_cols) > 0 or (date_col and time_period != "None"):
                                    chart_metric = st.selectbox(
                                        "Primary metric",
                                        [c for c in agg_result.columns if c not in groupby_cols and c != "Period"],
                                        key="viz_metric",
                                    )

                                    add_second_metric = st.checkbox("Add comparison metric", key="add_second_metric")
                                    chart_metric2 = None
                                    if add_second_metric:
                                        chart_metric2 = st.selectbox(
                                            "Secondary metric",
                                            [
                                                c
                                                for c in agg_result.columns
                                                if c not in groupby_cols and c != "Period" and c != chart_metric
                                            ],
                                            key="viz_metric2",
                                        )

                            with viz_col2:
                                chart_type = st.selectbox(
                                    "Chart type", ["Bar", "Line", "Area", "Scatter", "Stacked Bar"], key="chart_type"
                                )

                            if chart_metric:
                                if "Period" in agg_result.columns:
                                    x_axis = "Period"
                                elif groupby_cols:
                                    x_axis = groupby_cols[0]
                                else:
                                    x_axis = agg_result.columns[0]

                                if chart_type == "Bar":
                                    if chart_metric2:
                                        fig = go.Figure()
                                        fig.add_trace(
                                            go.Bar(x=agg_result[x_axis], y=agg_result[chart_metric], name=chart_metric)
                                        )
                                        fig.add_trace(
                                            go.Bar(
                                                x=agg_result[x_axis], y=agg_result[chart_metric2], name=chart_metric2
                                            )
                                        )
                                        fig.update_layout(barmode="group", title=f"{chart_metric} vs {chart_metric2}")
                                    else:
                                        fig = px.bar(
                                            agg_result, x=x_axis, y=chart_metric, title=f"{chart_metric} by {x_axis}"
                                        )
                                elif chart_type == "Stacked Bar":
                                    if chart_metric2:
                                        fig = go.Figure()
                                        fig.add_trace(
                                            go.Bar(x=agg_result[x_axis], y=agg_result[chart_metric], name=chart_metric)
                                        )
                                        fig.add_trace(
                                            go.Bar(
                                                x=agg_result[x_axis], y=agg_result[chart_metric2], name=chart_metric2
                                            )
                                        )
                                        fig.update_layout(
                                            barmode="stack", title=f"{chart_metric} + {chart_metric2} (Stacked)"
                                        )
                                    else:
                                        fig = px.bar(
                                            agg_result, x=x_axis, y=chart_metric, title=f"{chart_metric} (Stacked)"
                                        )
                                elif chart_type == "Line":
                                    if chart_metric2:
                                        fig = go.Figure()
                                        fig.add_trace(
                                            go.Scatter(
                                                x=agg_result[x_axis],
                                                y=agg_result[chart_metric],
                                                mode="lines+markers",
                                                name=chart_metric,
                                            )
                                        )
                                        fig.add_trace(
                                            go.Scatter(
                                                x=agg_result[x_axis],
                                                y=agg_result[chart_metric2],
                                                mode="lines+markers",
                                                name=chart_metric2,
                                            )
                                        )
                                        fig.update_layout(title=f"{chart_metric} vs {chart_metric2}")
                                    else:
                                        fig = px.line(
                                            agg_result,
                                            x=x_axis,
                                            y=chart_metric,
                                            title=f"{chart_metric} Trend",
                                            markers=True,
                                        )
                                elif chart_type == "Scatter":
                                    if chart_metric2:
                                        fig = px.scatter(
                                            agg_result,
                                            x=chart_metric,
                                            y=chart_metric2,
                                            title=f"{chart_metric} vs {chart_metric2}",
                                            hover_data=[x_axis],
                                        )
                                    else:
                                        fig = px.scatter(
                                            agg_result, x=x_axis, y=chart_metric, title=f"{chart_metric} Distribution"
                                        )
                                else:
                                    fig = px.area(
                                        agg_result, x=x_axis, y=chart_metric, title=f"{chart_metric} Over Time"
                                    )

                                st.plotly_chart(fig, width="stretch")

                            st.divider()
                            st.subheader("📥 Export Options")

                            col_exp1, col_exp2, col_exp3 = st.columns(3)

                            with col_exp1:
                                csv = agg_result.to_csv(index=False)
                                st.download_button(
                                    " Download CSV",
                                    csv,
                                    f"aggregated_results_{time_period}.csv",
                                    "text/csv",
                                    width="stretch",
                                )

                            with col_exp2:
                                try:
                                    output = BytesIO()
                                    with pd.ExcelWriter(output, engine="openpyxl") as writer:
                                        agg_result.to_excel(writer, index=False, sheet_name="Analysis")
                                    excel_data = output.getvalue()
                                    st.download_button(
                                        " Download Excel",
                                        excel_data,
                                        f"aggregated_results_{time_period}.xlsx",
                                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                        width="stretch",
                                    )
                                except Exception:
                                    st.info("Excel export requires openpyxl")

                            with col_exp3:
                                save_agg_name = st.text_input(
                                    "Table name", f"{calc_tbl}_agg_{time_period}", key="save_agg"
                                )
                                if st.button(" Save to DB", key="save_agg_btn", width="stretch"):
                                    ok, msg = extractor.extract_from_df(agg_result, save_agg_name, "replace")
                                    if ok:
                                        st.success(msg)
                                    else:
                                        st.error(msg)

                        st.divider()
                        save_name = st.text_input("Save calculated data as", f"{calc_tbl}_calculated")
                        if st.button(" Save to Database", type="secondary"):
                            ok, msg = extractor.extract_from_df(df_res, save_name, "replace")
                            if ok:
                                st.success(msg)
                            else:
                                st.error(msg)
                    else:
                        st.warning("No calculated columns found. Check your column mapping.")
            else:
                st.warning("Confirm column mapping in the Upload tab first, or selected table is empty.")


def render_waterfall_tab(tab, extractor: SolarDataExtractor):
    with tab:
        st.header("?? Portfolio Loss Waterfall")

        tables = extractor.list_tables()
        if not tables:
            st.warning("Upload data and run calculations in the Calculations tab first.")
            return

        source_tbl = st.selectbox("Select Data Table", list(tables), key="t6_sel_tbl")
        colmap = st.session_state.get("colmap", {})
        session_key = f"res_{source_tbl}"

        if not colmap or not st.session_state.colmap_confirmed:
            st.error("Column mapping not confirmed. Go to Upload tab first.")
            return

        if session_key in st.session_state:
            df_full = st.session_state[session_key]
            st.success("? Loaded calculated data from session memory.")
        else:
            ok, df_full = extractor.query_data(f"SELECT * FROM {source_tbl}")
            if ok and not isinstance(df_full, str) and not df_full.empty:
                try:
                    analyzer = SolarDataAnalyzer(df_full, colmap)
                    df_full = analyzer.compute_losses()
                    st.session_state[session_key] = df_full
                    st.info(f"? Auto-calculated losses for {len(df_full):,} rows")
                except Exception as e:
                    st.warning(f"Could not auto-calculate losses: {e}")
            else:
                st.error("Could not load data. Run calculations in Tab 5 first.")
                st.stop()

        st.markdown("### Total Portfolio Performance")

        df_final = df_full.sum(numeric_only=True).to_frame().T
        if df_final.empty:
            st.warning("Dataframe is empty after aggregation.")
            return

        col1, col2, col3, col4 = st.columns(4)
        budget_col = colmap.get("budget_gen")
        actual_col = colmap.get("actual_gen")

        if budget_col and actual_col and budget_col in df_final.columns and actual_col in df_final.columns:
            with col1:
                st.metric("Budget Gen (kWh)", f"{df_final[budget_col].iloc[0]:,.0f}")
            with col2:
                st.metric("Actual Gen (kWh)", f"{df_final[actual_col].iloc[0]:,.0f}")
            with col3:
                if "Var_Weather_kWh" in df_final.columns:
                    st.metric("Weather Variance", f"{df_final['Var_Weather_kWh'].iloc[0]:,.0f}")
            with col4:
                if "Loss_Total_Tech_kWh" in df_final.columns:
                    st.metric("Technical Loss", f"{df_final['Loss_Total_Tech_kWh'].iloc[0]:,.0f}")

        st.divider()

        fig = plot_waterfall(df_final, colmap)
        if fig:
            st.plotly_chart(fig, width="stretch")
            st.markdown(
                """
                    **Chart Interpretation:**
                    - **Budget Gen:** Original P50/budget forecast
                    - **Weather ?:** Actual weather vs forecast (positive = better than expected)
                    - **WAB:** Weather-Adjusted Budget (what we should have produced given actual weather)
                    - **PR Loss:** Performance ratio underperformance
                    - **Avail Loss:** Lost generation due to downtime
                    - **Actual Gen:** Final metered production
                    """
            )
