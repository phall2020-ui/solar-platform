"""
Simplified Calculations Tab - Filter-first KPI Dashboard
Replaces the overly complex render_calculations_tab function
"""

from io import BytesIO
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from analysis import (
    SolarDataAnalyzer,
    aggregate_flexible,
    weighted_average,
)
from config import Config


# KPI definitions with display names, format, and aggregation method
KPI_DEFINITIONS = {
    # Energy metrics (sum)
    "Actual Gen (kWh)": {"display": "Actual Generation", "format": "{:,.0f} kWh", "agg": "sum"},
    "Forecast Gen (kWh)": {"display": "Budget Generation", "format": "{:,.0f} kWh", "agg": "sum"},
    "Irradiance-based generation": {"display": "Weather-Adjusted Budget", "format": "{:,.0f} kWh", "agg": "sum"},
    "Loss_Total_Tech_kWh": {"display": "Total Technical Loss", "format": "{:,.0f} kWh", "agg": "sum"},
    "Loss_PR_kWh": {"display": "PR Loss", "format": "{:,.0f} kWh", "agg": "sum"},
    "Loss_Avail_kWh": {"display": "Availability Loss", "format": "{:,.0f} kWh", "agg": "sum"},
    "Var_Weather_kWh": {"display": "Weather Variance", "format": "{:,.0f} kWh", "agg": "sum"},
    "Var_Total_Budget_kWh": {"display": "Budget Variance", "format": "{:,.0f} kWh", "agg": "sum"},
    # Ratio metrics (weighted average)
    "Actual PR (%)": {"display": "Actual PR", "format": "{:.1f}%", "agg": "weighted_avg"},
    "Forecast PR (%)": {"display": "Budget PR", "format": "{:.1f}%", "agg": "weighted_avg"},
    "Availability (%)": {"display": "Availability", "format": "{:.1f}%", "agg": "weighted_avg"},
    "Var_PR_pp": {"display": "PR Variance", "format": "{:+.2f} pp", "agg": "weighted_avg"},
    "Var_Availability_pp": {"display": "Availability Variance", "format": "{:+.2f} pp", "agg": "weighted_avg"},
    "Yield_kWh_per_kWp": {"display": "Yield", "format": "{:.1f} kWh/kWp", "agg": "weighted_avg"},
}


def parse_dates(series: pd.Series) -> pd.Series:
    """Try multiple date formats to parse a date column."""
    date_formats = ["%b-%y", "%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%b-%y", "%B %Y"]
    for fmt in date_formats:
        try:
            return pd.to_datetime(series, format=fmt, errors="raise")
        except Exception:
            continue
    return pd.to_datetime(series, errors="coerce")


def clean_numeric_column(series: pd.Series) -> pd.Series:
    """Clean a numeric column by removing formatting characters."""
    if series.dtype == "object":
        cleaned = series.astype(str).str.replace(",", "").str.replace("%", "").str.strip()
        return pd.to_numeric(cleaned, errors="coerce")
    return pd.to_numeric(series, errors="coerce")


def calculate_kpis(
    df: pd.DataFrame,
    kpi_columns: List[str],
    weight_col: Optional[str] = None,
) -> Dict[str, float]:
    """
    Calculate KPIs with appropriate aggregation (sum vs weighted average).
    """
    results = {}

    for col in kpi_columns:
        if col not in df.columns:
            continue

        values = clean_numeric_column(df[col])
        kpi_def = KPI_DEFINITIONS.get(col, {"agg": "sum"})

        if kpi_def["agg"] == "sum":
            results[col] = values.sum()
        elif kpi_def["agg"] == "weighted_avg" and weight_col and weight_col in df.columns:
            weights = clean_numeric_column(df[weight_col])
            mask = values.notna() & weights.notna() & (weights > 0)
            if mask.any():
                results[col] = (values[mask] * weights[mask]).sum() / weights[mask].sum()
            else:
                results[col] = values.mean()
        else:
            results[col] = values.mean()

    return results


def format_kpi_value(col: str, value: float) -> str:
    """Format a KPI value for display."""
    if pd.isna(value):
        return "—"
    kpi_def = KPI_DEFINITIONS.get(col, {"format": "{:.2f}"})
    try:
        return kpi_def["format"].format(value)
    except Exception:
        return f"{value:,.2f}"


def render_calculations_tab_simple(tab, extractor):
    """
    Simplified calculations tab with filter-first approach.
    """
    with tab:
        st.header("📊 KPI Analysis")

        tables = extractor.list_tables()
        if not tables:
            st.warning("No data available. Please upload data first.")
            return

        # ─────────────────────────────────────────────────────────────
        # STEP 1: Data Source Selection
        # ─────────────────────────────────────────────────────────────
        source_table = st.selectbox(
            "Select Data Source",
            list(tables),
            key="calc_source_table",
            help="Choose the table containing your solar performance data",
        )

        ok, df_raw = extractor.query_data(f"SELECT * FROM {source_table}")
        if not ok or isinstance(df_raw, str) or df_raw.empty:
            st.error("Could not load data from selected table.")
            return

        # Clean numeric columns
        for col in df_raw.columns:
            if any(x in col for x in ["kWh", "Gen", "PR", "Avail", "%", "kWp", "Yield"]):
                df_raw[col] = clean_numeric_column(df_raw[col])

        # Run calculations if not already done
        colmap = st.session_state.get("colmap", {})
        if colmap and st.session_state.get("colmap_confirmed"):
            try:
                analyzer = SolarDataAnalyzer(df_raw, colmap)
                df = analyzer.compute_losses()
            except Exception:
                df = df_raw.copy()
        else:
            df = df_raw.copy()

        st.success(f"Loaded {len(df):,} records")

        # ─────────────────────────────────────────────────────────────
        # STEP 2: Filters (in a clean horizontal layout)
        # ─────────────────────────────────────────────────────────────
        st.subheader("🔍 Filters")

        filter_col1, filter_col2, filter_col3 = st.columns(3)

        # Site filter
        site_col = colmap.get("site") or next((c for c in df.columns if "site" in c.lower()), None)
        selected_sites = None

        with filter_col1:
            if site_col and site_col in df.columns:
                all_sites = df[site_col].dropna().unique().tolist()
                selected_sites = st.multiselect(
                    "📍 Sites",
                    options=all_sites,
                    default=None,
                    placeholder="All sites",
                    help="Select one or more sites (leave empty for all)",
                )

        # Date filter
        date_col = colmap.get("date") or next((c for c in df.columns if "date" in c.lower()), None)
        date_range = None

        with filter_col2:
            if date_col and date_col in df.columns:
                df["_parsed_date"] = parse_dates(df[date_col])
                valid_dates = df["_parsed_date"].dropna()

                if not valid_dates.empty:
                    min_date = valid_dates.min().date()
                    max_date = valid_dates.max().date()

                    date_range = st.date_input(
                        "📅 Date Range",
                        value=(min_date, max_date),
                        min_value=min_date,
                        max_value=max_date,
                        help="Filter data by date range",
                    )

        # Asset type filter (look for common type columns)
        type_col = next(
            (c for c in df.columns if any(x in c.lower() for x in ["type", "technology", "category", "class"])), None
        )
        selected_types = None

        with filter_col3:
            if type_col and type_col in df.columns:
                all_types = df[type_col].dropna().unique().tolist()
                selected_types = st.multiselect(
                    "🏭 Asset Type",
                    options=all_types,
                    default=None,
                    placeholder="All types",
                    help="Filter by asset type (rooftop, ground-mount, etc.)",
                )
            else:
                st.info("No asset type column detected")

        # ─────────────────────────────────────────────────────────────
        # STEP 3: Apply Filters
        # ─────────────────────────────────────────────────────────────
        df_filtered = df.copy()

        if selected_sites:
            df_filtered = df_filtered[df_filtered[site_col].isin(selected_sites)]

        if date_range and len(date_range) == 2 and "_parsed_date" in df_filtered.columns:
            start_date, end_date = date_range
            df_filtered = df_filtered[
                (df_filtered["_parsed_date"] >= pd.Timestamp(start_date))
                & (df_filtered["_parsed_date"] <= pd.Timestamp(end_date))
            ]

        if selected_types:
            df_filtered = df_filtered[df_filtered[type_col].isin(selected_types)]

        # Show filter summary
        filter_summary = []
        if selected_sites:
            filter_summary.append(f"{len(selected_sites)} site(s)")
        if date_range and len(date_range) == 2:
            filter_summary.append(f"{date_range[0]} to {date_range[1]}")
        if selected_types:
            filter_summary.append(f"{len(selected_types)} type(s)")

        if filter_summary:
            st.caption(f"Filtering: {' | '.join(filter_summary)} → **{len(df_filtered):,} records**")

        if df_filtered.empty:
            st.warning("No data matches your filters. Please adjust your selection.")
            return

        st.divider()

        # ─────────────────────────────────────────────────────────────
        # STEP 4: KPI Selection
        # ─────────────────────────────────────────────────────────────
        st.subheader("📈 Select KPIs")

        # Find available KPIs in the data
        available_kpis = [col for col in df_filtered.columns if col in KPI_DEFINITIONS]

        # Add common column variations
        for col in df_filtered.columns:
            if col not in available_kpis:
                col_lower = col.lower()
                if any(x in col_lower for x in ["gen", "loss", "var_", "pr", "avail", "yield"]):
                    if pd.api.types.is_numeric_dtype(df_filtered[col]) or df_filtered[col].dtype == "object":
                        available_kpis.append(col)

        # Default selection - key metrics
        default_kpis = [
            col
            for col in available_kpis
            if any(x in col for x in ["Actual Gen", "Loss_Total", "Actual PR", "Availability", "Yield"])
        ][:5]

        selected_kpis = st.multiselect(
            "Choose metrics to display",
            options=available_kpis,
            default=default_kpis if default_kpis else available_kpis[:5],
            help="Select the KPIs you want to analyze",
        )

        if not selected_kpis:
            st.info("Please select at least one KPI to display.")
            return

        st.divider()

        # ─────────────────────────────────────────────────────────────
        # STEP 5: View Options
        # ─────────────────────────────────────────────────────────────
        view_col1, view_col2 = st.columns(2)

        with view_col1:
            view_mode = st.radio(
                "View by",
                ["Summary (Total)", "By Site", "By Period", "By Site & Period"],
                horizontal=True,
                help="Choose how to group the results",
            )

        with view_col2:
            if "Period" in view_mode:
                period_type = st.selectbox(
                    "Period granularity", ["Monthly", "Quarterly", "Annual"], help="Time period for grouping"
                )
            else:
                period_type = None

        # ─────────────────────────────────────────────────────────────
        # STEP 6: Calculate & Display Results
        # ─────────────────────────────────────────────────────────────
        st.divider()
        st.subheader("📊 Results")

        # Determine weight column for weighted averages
        weight_col = colmap.get("actual_gen") or next(
            (c for c in df_filtered.columns if "actual" in c.lower() and "gen" in c.lower()), None
        )

        if view_mode == "Summary (Total)":
            # Single row summary
            kpi_values = calculate_kpis(df_filtered, selected_kpis, weight_col)

            # Display as metric cards
            cols = st.columns(min(len(kpi_values), 4))
            for i, (col, value) in enumerate(kpi_values.items()):
                with cols[i % len(cols)]:
                    display_name = KPI_DEFINITIONS.get(col, {}).get("display", col)
                    formatted_value = format_kpi_value(col, value)
                    st.metric(display_name, formatted_value)

            # Also show as table
            with st.expander("View as table"):
                results_df = pd.DataFrame(
                    [
                        {
                            "Metric": KPI_DEFINITIONS.get(k, {}).get("display", k),
                            "Value": format_kpi_value(k, v),
                            "Aggregation": KPI_DEFINITIONS.get(k, {}).get("agg", "sum").replace("_", " ").title(),
                        }
                        for k, v in kpi_values.items()
                    ]
                )
                st.dataframe(results_df, hide_index=True, use_container_width=True)

        else:
            # Grouped view
            group_cols = []

            if "Site" in view_mode and site_col:
                group_cols.append(site_col)

            fiscal_start = st.session_state.get("fiscal_year_start", 4)

            if "Period" in view_mode and date_col and "_parsed_date" in df_filtered.columns:
                # Add period column
                dates = df_filtered["_parsed_date"]

                if period_type == "Monthly":
                    df_filtered["Period"] = dates.dt.to_period("M").astype(str)
                elif period_type == "Quarterly":
                    month = dates.dt.month
                    year = dates.dt.year
                    fiscal_quarter = ((month - fiscal_start) % 12) // 3 + 1
                    fiscal_year = np.where(month < fiscal_start, year, year + 1)
                    df_filtered["Period"] = "FY" + fiscal_year.astype(str) + "-Q" + fiscal_quarter.astype(str)
                elif period_type == "Annual":
                    month = dates.dt.month
                    year = dates.dt.year
                    fiscal_year = np.where(month < fiscal_start, year, year + 1)
                    df_filtered["Period"] = "FY" + fiscal_year.astype(str)

                group_cols.append("Period")

            if not group_cols:
                st.warning("Cannot group data - required columns not found.")
                return

            # Build aggregated results
            results_list = []

            for group_values, group_df in df_filtered.groupby(group_cols):
                if not isinstance(group_values, tuple):
                    group_values = (group_values,)

                row = dict(zip(group_cols, group_values))
                row["Records"] = len(group_df)

                kpi_values = calculate_kpis(group_df, selected_kpis, weight_col)
                row.update(kpi_values)

                results_list.append(row)

            results_df = pd.DataFrame(results_list)

            # Sort by period if available
            if "Period" in results_df.columns:
                results_df = results_df.sort_values("Period")

            # Format display columns
            display_df = results_df.copy()
            for col in selected_kpis:
                if col in display_df.columns:
                    display_df[col] = display_df[col].apply(lambda x: format_kpi_value(col, x))

            # Rename columns for display
            rename_map = {col: KPI_DEFINITIONS.get(col, {}).get("display", col) for col in selected_kpis}
            display_df = display_df.rename(columns=rename_map)

            st.dataframe(display_df, hide_index=True, use_container_width=True)

            # ─────────────────────────────────────────────────────────
            # STEP 7: Quick Chart
            # ─────────────────────────────────────────────────────────
            st.divider()
            st.subheader("📈 Quick Chart")

            chart_col1, chart_col2 = st.columns([2, 1])

            with chart_col1:
                chart_metric = st.selectbox(
                    "Metric to chart", selected_kpis, format_func=lambda x: KPI_DEFINITIONS.get(x, {}).get("display", x)
                )

            with chart_col2:
                chart_type = st.selectbox("Chart type", ["Bar", "Line"])

            if chart_metric and chart_metric in results_df.columns:
                x_col = "Period" if "Period" in results_df.columns else group_cols[0]
                color_col = site_col if site_col in group_cols and x_col != site_col else None

                metric_name = KPI_DEFINITIONS.get(chart_metric, {}).get("display", chart_metric)

                if chart_type == "Bar":
                    fig = px.bar(
                        results_df,
                        x=x_col,
                        y=chart_metric,
                        color=color_col,
                        title=f"{metric_name} by {x_col}",
                        barmode="group",
                    )
                else:
                    fig = px.line(
                        results_df, x=x_col, y=chart_metric, color=color_col, title=f"{metric_name} Trend", markers=True
                    )

                fig.update_layout(yaxis_title=metric_name, xaxis_title=x_col, height=400)
                st.plotly_chart(fig, use_container_width=True)

        # ─────────────────────────────────────────────────────────────
        # STEP 8: Export
        # ─────────────────────────────────────────────────────────────
        st.divider()

        export_col1, export_col2 = st.columns(2)

        with export_col1:
            if view_mode == "Summary (Total)":
                export_df = pd.DataFrame(
                    [
                        {
                            "Metric": KPI_DEFINITIONS.get(k, {}).get("display", k),
                            "Value": v,
                            "Formatted": format_kpi_value(k, v),
                        }
                        for k, v in kpi_values.items()
                    ]
                )
            else:
                export_df = results_df

            csv = export_df.to_csv(index=False)
            st.download_button(
                "📥 Download CSV",
                csv,
                f"kpi_analysis_{view_mode.lower().replace(' ', '_')}.csv",
                "text/csv",
                use_container_width=True,
            )

        with export_col2:
            try:
                output = BytesIO()
                with pd.ExcelWriter(output, engine="openpyxl") as writer:
                    export_df.to_excel(writer, index=False, sheet_name="KPI Analysis")
                st.download_button(
                    "📥 Download Excel",
                    output.getvalue(),
                    f"kpi_analysis_{view_mode.lower().replace(' ', '_')}.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
            except ImportError:
                st.info("Install openpyxl for Excel export")
