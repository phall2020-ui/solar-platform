"""
Calculations Tab Module (Version 2)

This module provides the calculations tab interface for computing and displaying
solar performance metrics, losses, and variances. Features include:
- Loss calculations (weather, technical, PR, availability)
- Site-level and portfolio-level aggregations
- KPI visualizations with targets
- Time-series charts and data export
- Customizable date range and grouping options
"""

from io import BytesIO
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from analysis import SolarDataAnalyzer, weighted_average
from config import Config

# Try to import report button from unified app
REPORT_BUTTON_AVAILABLE = False
add_to_report_button = None

try:
    from components.report_button import add_to_report_button
    REPORT_BUTTON_AVAILABLE = True
except ImportError:
    # Try with absolute path for unified app
    import sys
    from pathlib import Path
    unified_app_path = Path(__file__).parent.parent / "unified_app"
    if unified_app_path.exists() and str(unified_app_path) not in sys.path:
        sys.path.insert(0, str(unified_app_path))
        try:
            from components.report_button import add_to_report_button
            REPORT_BUTTON_AVAILABLE = True
        except ImportError:
            pass


def clean_numeric(series: pd.Series) -> pd.Series:
    """
    Clean and convert a series to numeric values.

    Removes formatting like commas and percent signs before conversion.

    Args:
        series: Pandas Series to clean and convert.

    Returns:
        Series with numeric values (non-convertible values become NaN).
    """
    if series.dtype == "object":
        cleaned = series.astype(str).str.replace(",", "").str.replace("%", "").str.strip()
        return pd.to_numeric(cleaned, errors="coerce")
    return pd.to_numeric(series, errors="coerce")


def parse_dates(series: pd.Series) -> pd.Series:
    """
    Parse dates from a series trying multiple common formats.

    Args:
        series: Series containing date strings in various formats.

    Returns:
        Series with parsed datetime values.
    """
    formats = ["%b-%y", "%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%b-%y", "%b-%Y"]
    for fmt in formats:
        try:
            return pd.to_datetime(series, format=fmt, errors="raise")
        except:
            continue
    return pd.to_datetime(series, errors="coerce")


def _standard_plot(df, x_col, metrics, chart_type, color_col):
    # Get the report button function dynamically (may be injected at runtime)
    report_button_fn = globals().get('add_to_report_button')

    fig = go.Figure()
    for metric in metrics:
        if metric not in df.columns:
            continue

        # Only allow a literal color value; if the provided color_col looks like a column name, ignore it
        literal_color = None
        if isinstance(color_col, str):
            cc = color_col.strip()
            if cc.startswith("#") or cc.lower().startswith(("rgb(", "rgba(", "hsl(", "hsla(")):
                literal_color = cc

        if chart_type == "Bar":
            fig.add_trace(
                go.Bar(x=df[x_col], y=df[metric], name=metric, marker_color=literal_color if len(metrics) == 1 else None)
            )
        elif chart_type == "Stacked Bar":
            fig.add_trace(go.Bar(x=df[x_col], y=df[metric], name=metric))
        else:  # Line / Area variant
            color_primary = literal_color or "#2D8B9E"
            color_fill = "rgba(45,139,158,0.18)"
            fig.add_trace(
                go.Scatter(
                    x=df[x_col],
                    y=df[metric],
                    mode="lines+markers",
                    name=metric,
                    line=dict(color=color_primary, width=2.5, shape="spline"),
                    fill="tozeroy",
                    fillcolor=color_fill,
                    marker=dict(size=6, color=color_primary),
                    hovertemplate=f"{metric}: "+"%{y:.0f}<extra></extra>",
                )
            )

    if chart_type == "Bar":
        fig.update_layout(barmode="group")
    elif chart_type == "Stacked Bar":
        fig.update_layout(barmode="stack")

    # If single metric and x looks like period, apply area chart polish and annotations
    chart_title = f"{', '.join(metrics)} over {x_col}"
    if chart_type == "Line" and len(metrics) == 1 and x_col.lower().startswith("period"):
        metric = metrics[0]
        friendly_metric = metric.replace("_", " ").strip()
        chart_title = f"Cumulative Installed Solar Capacity (kWp)" if "kwp" in metric.lower() else chart_title

        # Format periods for display
        try:
            x_formatted = pd.to_datetime(df[x_col], errors="coerce").dt.strftime("%b '%y")
        except Exception:
            x_formatted = df[x_col]
        fig.update_traces(x=x_formatted)

        # Compute largest MoM jump
        try:
            y_vals = pd.to_numeric(df[metric], errors="coerce")
            deltas = y_vals.diff()
            max_idx = deltas.idxmax()
            max_delta = deltas.max()
            if pd.notna(max_idx) and pd.notna(max_delta) and max_delta != 0:
                fig.add_annotation(
                    x=x_formatted.iloc[max_idx],
                    y=y_vals.iloc[max_idx],
                    text=f"Major Capacity Addition: +{max_delta:,.0f} kWp",
                    showarrow=True,
                    arrowhead=2,
                    arrowsize=1,
                    arrowwidth=1,
                    ax=0,
                    ay=-40,
                    bgcolor="#f6fbff",
                    bordercolor="#2D8B9E",
                    borderwidth=1,
                )
        except Exception:
            pass

        # Axes styling
        fig.update_yaxes(
            title_text="Installed Capacity (kWp)",
            tickformat=",~s",
            gridcolor="rgba(0,0,0,0.08)",
            griddash="dash",
            zeroline=False,
        )
        fig.update_xaxes(
            title_text=None,
            showgrid=False,
            tickangle=-10,
        )
        fig.update_layout(
            title=dict(text=chart_title, x=0.0),
            hovermode="x unified",
            height=420,
            plot_bgcolor="#ffffff",
            paper_bgcolor="#ffffff",
            margin=dict(l=10, r=10, t=60, b=40),
        )
    else:
        fig.update_layout(title=chart_title, height=400, hovermode="x unified")

    st.plotly_chart(fig, use_container_width=True)

    # Add to report button
    if callable(report_button_fn):
        report_button_fn(
            content=fig,
            title=chart_title,
            item_type='chart',
            description=f"{chart_type} chart of {', '.join(metrics)}",
            source_page="KPI Analysis",
            button_key=f"add_chart_{'_'.join(metrics)}_{chart_type}".replace(' ', '_').replace('(', '').replace(')', '').replace('%', 'pct')
        )


def render_calculations_v2_tab(tab, extractor):
    """
    Simplified calculations tab with:
    - Site selection (single, multiple, or all)
    - Date filtering
    - All KPIs available (energy, PR, availability, yield, etc.)
    - Proper aggregation (sum for energy, weighted avg for ratios)
    """
    with tab:
        st.header("📊 KPI Analysis")

        # ─────────────────────────────────────────────────────────────
        # Load Data
        # ─────────────────────────────────────────────────────────────
        tables = extractor.list_tables()
        if not tables:
            st.warning("No data available. Please upload data first.")
            return

        source_table = st.selectbox("📁 Data Source", list(tables), key="calc_table")

        ok, df_raw = extractor.query_data(f"SELECT * FROM {source_table}")
        if not ok or isinstance(df_raw, str) or df_raw.empty:
            st.error("Could not load data.")
            return

        # Get column mapping
        colmap = st.session_state.get("colmap", {})

        # Run calculations if mapping exists
        if colmap and st.session_state.get("colmap_confirmed"):
            try:
                analyzer = SolarDataAnalyzer(df_raw, colmap)
                df = analyzer.compute_losses()
            except Exception as e:
                st.warning(f"Could not compute losses: {e}. Using raw data.")
                df = df_raw.copy()
        else:
            df = df_raw.copy()

        # Clean numeric columns
        for col in df.columns:
            if df[col].dtype == "object":
                # Try to convert to numeric if it looks like a number
                test_clean = df[col].astype(str).str.replace(",", "").str.replace("%", "")
                if pd.to_numeric(test_clean, errors="coerce").notna().mean() > 0.5:
                    df[col] = clean_numeric(df[col])

        st.success(f"✓ Loaded {len(df):,} records from '{source_table}'")

        # ─────────────────────────────────────────────────────────────
        # FILTERS SECTION
        # ─────────────────────────────────────────────────────────────
        st.subheader("🔍 Filters")

        col1, col2, col3 = st.columns(3)

        # --- Site Filter ---
        site_col = colmap.get("site")
        if not site_col:
            # Auto-detect site column
            for c in df.columns:
                if "site" in c.lower():
                    site_col = c
                    break

        selected_sites = []
        with col1:
            if site_col and site_col in df.columns:
                all_sites = sorted(df[site_col].dropna().unique().tolist())

                site_mode = st.radio(
                    "📍 Site Selection", ["All Sites (Portfolio)", "Select Sites"], horizontal=True, key="site_mode"
                )

                if site_mode == "Select Sites":
                    selected_sites = st.multiselect(
                        "Choose sites", options=all_sites, default=all_sites[:1] if all_sites else [], key="site_select"
                    )
            else:
                st.info("No site column found")

        # --- Date Filter ---
        date_col = colmap.get("date")
        if not date_col:
            for c in df.columns:
                if "date" in c.lower():
                    date_col = c
                    break

        selected_months = []
        with col2:
            if date_col and date_col in df.columns:
                df["_date"] = parse_dates(df[date_col])
                valid_dates = df["_date"].dropna()

                if not valid_dates.empty:
                    # Create Month-Year column for filtering
                    df["_month_str"] = df["_date"].dt.strftime("%b-%y")

                    # Get unique months sorted by date (newest first)
                    unique_dates = df["_date"].dt.to_period("M").unique()
                    # Sort PeriodIndex
                    unique_dates = sorted(unique_dates, reverse=True)
                    all_months = [d.strftime("%b-%y") for d in unique_dates]

                    selected_months = st.multiselect(
                        "📅 Select Months", options=all_months, default=[], placeholder="All months", key="month_select"
                    )
            else:
                st.info("No date column found")

        # --- Type Filter ---
        type_col = None
        for c in df.columns:
            if any(x in c.lower() for x in ["type", "technology", "category"]):
                type_col = c
                break

        selected_types = []
        with col3:
            if type_col and type_col in df.columns:
                all_types = sorted(df[type_col].dropna().unique().tolist())
                selected_types = st.multiselect(
                    "🏭 Asset Type", options=all_types, default=[], placeholder="All types", key="type_select"
                )
            else:
                st.info("No type column found")

        # ─────────────────────────────────────────────────────────────
        # APPLY FILTERS
        # ─────────────────────────────────────────────────────────────
        df_filtered = df.copy()

        # Apply site filter
        if selected_sites and site_col:
            df_filtered = df_filtered[df_filtered[site_col].isin(selected_sites)]

        # Apply date filter (by selected months)
        if selected_months and "_month_str" in df_filtered.columns:
            df_filtered = df_filtered[df_filtered["_month_str"].isin(selected_months)]

        # Apply type filter
        if selected_types and type_col:
            df_filtered = df_filtered[df_filtered[type_col].isin(selected_types)]

        # Show filter summary
        st.caption(f"**{len(df_filtered):,} records** after filtering")

        if df_filtered.empty:
            st.warning("No data matches your filters.")
            return

        st.divider()

        # ─────────────────────────────────────────────────────────────
        # KPI SELECTION
        # ─────────────────────────────────────────────────────────────
        st.subheader("📈 Select KPIs")

        # Categorize available columns
        energy_cols = []
        ratio_cols = []
        other_cols = []

        for col in df_filtered.columns:
            if col.startswith("_"):  # Skip internal columns
                continue
            if not pd.api.types.is_numeric_dtype(df_filtered[col]):
                continue

            col_lower = col.lower()

            # Check for yield/ratio metrics FIRST (before energy)
            # These contain "kwh" but should be averaged, not summed
            if "kwh/kwp" in col_lower or "kwhkwp" in col_lower or "yield" in col_lower:
                ratio_cols.append(col)
            # Other ratio metrics (to be averaged)
            elif any(x in col_lower for x in ["pr", "avail", "%", "ratio", "factor"]):
                ratio_cols.append(col)
            # Energy metrics (to be summed)
            elif any(x in col_lower for x in ["kwh", "mwh", "gen", "loss", "energy", "irrad"]) or any(
                x in col for x in ["Var_Weather", "Loss_", "Var_Total"]
            ):
                energy_cols.append(col)
            else:
                other_cols.append(col)

        # Display in organized tabs
        kpi_tab1, kpi_tab2, kpi_tab3 = st.tabs(["⚡ Energy (kWh)", "📊 Ratios (%)", "📋 Other"])

        with kpi_tab1:
            selected_energy = st.multiselect(
                "Energy metrics (will be summed)",
                energy_cols,
                default=[c for c in energy_cols if any(x in c for x in ["Actual Gen", "Loss_Total", "Var_Weather"])][
                    :3
                ],
                key="energy_kpis",
            )

        with kpi_tab2:
            selected_ratios = st.multiselect(
                "Ratio metrics (will be weighted averaged)",
                ratio_cols,
                default=[c for c in ratio_cols if any(x in c.lower() for x in ["actual pr", "avail", "yield"])][:3],
                key="ratio_kpis",
            )

        with kpi_tab3:
            selected_other = st.multiselect("Other metrics", other_cols, default=[], key="other_kpis")

        selected_kpis = selected_energy + selected_ratios + selected_other

        if not selected_kpis:
            st.warning("Please select at least one KPI.")
            return

        st.divider()

        # ─────────────────────────────────────────────────────────────
        # VIEW OPTIONS
        # ─────────────────────────────────────────────────────────────
        st.subheader("👁️ View Options")

        view_col1, view_col2 = st.columns(2)

        with view_col1:
            view_mode = st.selectbox(
                "Group results by", ["Total (Summary)", "By Period", "By Site", "By Site & Period"], key="view_mode"
            )

        with view_col2:
            if "Period" in view_mode:
                period_type = st.selectbox("Period type", ["Monthly", "Quarterly", "Annual"], key="period_type")
            else:
                period_type = "Monthly"

        st.divider()

        # ─────────────────────────────────────────────────────────────
        # CALCULATE RESULTS
        # ─────────────────────────────────────────────────────────────
        st.subheader("📊 Results")

        # Weight column for weighted averages
        weight_col = colmap.get("actual_gen")
        if not weight_col:
            for c in df_filtered.columns:
                if "actual" in c.lower() and "gen" in c.lower():
                    weight_col = c
                    break

        # Add period column if needed
        if "Period" in view_mode and "_date" in df_filtered.columns:
            fiscal_start = st.session_state.get("fiscal_year_start", 4)
            dates = df_filtered["_date"]

            if period_type == "Monthly":
                df_filtered["Period"] = dates.dt.strftime("%Y-%m")
            elif period_type == "Quarterly":
                month = dates.dt.month
                year = dates.dt.year
                fq = ((month - fiscal_start) % 12) // 3 + 1
                fy = np.where(month < fiscal_start, year, year + 1)
                df_filtered["Period"] = "FY" + fy.astype(str) + "-Q" + fq.astype(str)
            else:  # Annual
                month = dates.dt.month
                year = dates.dt.year
                fy = np.where(month < fiscal_start, year, year + 1)
                df_filtered["Period"] = "FY" + fy.astype(str)

        # Build grouping
        group_cols = []
        if "Site" in view_mode and site_col:
            group_cols.append(site_col)
        if "Period" in view_mode and "Period" in df_filtered.columns:
            group_cols.append("Period")

        # Calculate KPIs
        if view_mode == "Total (Summary)" or not group_cols:
            # Single summary row
            results = {"View": "Total Portfolio"}
            results["Records"] = len(df_filtered)

            for col in selected_energy:
                if col in df_filtered.columns:
                    results[col] = df_filtered[col].sum()

            for col in selected_ratios:
                if col in df_filtered.columns:
                    if weight_col and weight_col in df_filtered.columns:
                        results[col] = weighted_average(df_filtered, col, weight_col)
                    else:
                        results[col] = df_filtered[col].mean()

            for col in selected_other:
                if col in df_filtered.columns:
                    results[col] = df_filtered[col].sum()

            results_df = pd.DataFrame([results])

            # Display as metric cards
            st.write("**Portfolio Summary**")

            # Energy metrics
            if selected_energy:
                cols = st.columns(min(len(selected_energy), 4))
                for i, col in enumerate(selected_energy):
                    if col in results:
                        with cols[i % len(cols)]:
                            st.metric(col, f"{results[col]:,.0f} kWh")

            # Ratio metrics
            if selected_ratios:
                cols = st.columns(min(len(selected_ratios), 4))
                for i, col in enumerate(selected_ratios):
                    if col in results:
                        with cols[i % len(cols)]:
                            val = results[col]
                            if pd.notna(val):
                                # Yield metrics - show as kWh/kWp
                                if "kwh/kwp" in col.lower() or "kwhkwp" in col.lower() or "yield" in col.lower():
                                    st.metric(col, f"{val:,.1f} kWh/kWp")
                                # Percentage metrics
                                else:
                                    # If value looks like a decimal (0-1 range), multiply by 100
                                    if 0 < val <= 1 and "%" in col:
                                        val = val * 100
                                    st.metric(col, f"{val:.2f}%")

        else:
            # Grouped results
            results_list = []

            for group_key, group_df in df_filtered.groupby(group_cols):
                if not isinstance(group_key, tuple):
                    group_key = (group_key,)

                row = dict(zip(group_cols, group_key))
                row["Records"] = len(group_df)

                # Sum energy metrics
                for col in selected_energy:
                    if col in group_df.columns:
                        row[col] = group_df[col].sum()

                # Weighted average for ratios
                for col in selected_ratios:
                    if col in group_df.columns:
                        if weight_col and weight_col in group_df.columns:
                            row[col] = weighted_average(group_df, col, weight_col)
                        else:
                            row[col] = group_df[col].mean()

                # Sum other metrics
                for col in selected_other:
                    if col in group_df.columns:
                        row[col] = group_df[col].sum()

                results_list.append(row)

            results_df = pd.DataFrame(results_list)

            # Sort
            if "Period" in results_df.columns:
                results_df = results_df.sort_values("Period")
            elif site_col in results_df.columns:
                results_df = results_df.sort_values(site_col)

        # ─────────────────────────────────────────────────────────────
        # DISPLAY RESULTS TABLE
        # ─────────────────────────────────────────────────────────────
        if len(results_df) > 1 or view_mode != "Total (Summary)":
            st.write(f"**{len(results_df)} rows**")

            # Create display copy FIRST
            display_df = results_df.copy()

            # Add summary row if grouped
            if view_mode != "Total (Summary)":
                try:
                    # Calculate totals for numeric columns
                    totals = {}
                    # Try to set grouping columns to "Total"
                    if "Period" in results_df.columns:
                        totals["Period"] = "Total"
                    if site_col and site_col in results_df.columns:
                        totals[site_col] = "Total"

                    for col in results_df.columns:
                        if col in selected_energy:
                            totals[col] = results_df[col].sum()
                        elif col in selected_ratios:
                            # Simple average for ratios in summary row
                            totals[col] = results_df[col].mean()
                        elif col in selected_other:
                            if pd.api.types.is_numeric_dtype(results_df[col]):
                                totals[col] = results_df[col].sum()

                    # Append total row to DISPLAY_DF
                    display_df = pd.concat([display_df, pd.DataFrame([totals])], ignore_index=True)
                    # Fill NaN in grouping columns with "Total"
                    if "Period" in display_df.columns:
                        display_df["Period"] = display_df["Period"].fillna("Total")
                    if site_col and site_col in display_df.columns:
                        display_df[site_col] = display_df[site_col].fillna("Total")
                except Exception:
                    pass

            # Format the dataframe for display

            # Conditional formatting
            def highlight_variance(val):
                if pd.isna(val):
                    return ""
                if isinstance(val, (int, float)):
                    if val < 0.95:
                        return "background-color: #ffcccc"  # Red
                    if val > 1.05:
                        return "background-color: #d9ead3"  # Green
                return ""

            # Format numbers
            for col in display_df.columns:
                if col in selected_energy:
                    display_df[col] = display_df[col].apply(lambda x: f"{x:,.0f}" if pd.notna(x) else "")
                elif col in selected_ratios:
                    # Check if it's a yield metric
                    col_lower = col.lower()
                    if "kwh/kwp" in col_lower or "kwhkwp" in col_lower or "yield" in col_lower:
                        display_df[col] = display_df[col].apply(lambda x: f"{x:,.1f}" if pd.notna(x) else "")
                    else:

                        def format_ratio(x):
                            if pd.isna(x):
                                return ""
                            # If value looks like a decimal (0-1 range), multiply by 100
                            if 0 < x <= 1:
                                x = x * 100
                            return f"{x:.2f}%"

                        display_df[col] = display_df[col].apply(format_ratio)

            # Apply styling to variance columns
            variance_cols = [c for c in display_df.columns if "variance" in c.lower()]
            if variance_cols:
                st.dataframe(
                    display_df.style.applymap(highlight_variance, subset=variance_cols),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.dataframe(display_df, use_container_width=True, hide_index=True)

            # Add to report button for the results table
            report_button_fn = globals().get('add_to_report_button')
            if callable(report_button_fn):
                report_button_fn(
                    content=results_df,
                    title=f"KPI Results - {view_mode}",
                    item_type='table',
                    description=f"KPI analysis results with {len(results_df)} rows",
                    source_page="KPI Analysis",
                    button_key=f"add_kpi_table_{view_mode}".replace(' ', '_').replace('(', '').replace(')', '')
                )

        # ─────────────────────────────────────────────────────────────
        # CHART
        # ─────────────────────────────────────────────────────────────
        if len(results_df) > 1:
            st.divider()
            st.subheader("📈 Chart")

            chart_col1, chart_col2 = st.columns([3, 1])

            with chart_col1:
                chart_metrics = st.multiselect(
                    "Metrics to chart (max 4)",
                    selected_kpis,
                    default=[selected_kpis[0]] if selected_kpis else [],
                    max_selections=4,
                    key="chart_metrics",
                )

            with chart_col2:
                # Smart Chart Type Selection
                chart_options = ["Bar", "Line", "Stacked Bar"]
                default_index = 0

                if view_mode == "By Site & Period":
                    chart_options.append("Heatmap")
                    default_index = 3  # Default to Heatmap
                elif view_mode == "By Period":
                    default_index = 1  # Default to Line

                chart_type = st.selectbox("Type", chart_options, index=default_index, key="chart_type")

            if chart_metrics:
                # Determine x-axis
                if "Period" in results_df.columns:
                    x_col = "Period"
                    color_col = site_col if site_col in results_df.columns else None
                elif site_col and site_col in results_df.columns:
                    x_col = site_col
                    color_col = None
                else:
                    x_col = results_df.columns[0]
                    color_col = None

                # --- HEATMAP ---
                if chart_type == "Heatmap":
                    if len(chart_metrics) > 1:
                        st.caption("⚠️ Heatmap uses the first selected metric only.")

                    metric = chart_metrics[0]
                    if site_col and "Period" in results_df.columns:
                        # Pivot for heatmap
                        try:
                            friendly_metric = metric.replace("_", " ").strip()
                            pivot_df = results_df.pivot(index=site_col, columns="Period", values=metric)

                            # Order sites alphabetically (case-insensitive, trimmed)
                            pivot_df = pivot_df.sort_index(key=lambda s: s.str.strip().str.lower())

                            # Format period labels and sort chronologically when parsable
                            def _fmt_period(p):
                                dt = pd.to_datetime(p, errors="coerce")
                                return dt.strftime("%b '%y") if not pd.isna(dt) else str(p)

                            col_info = []
                            for c in pivot_df.columns:
                                dt = pd.to_datetime(c, errors="coerce")
                                col_info.append((dt if not pd.isna(dt) else None, c, _fmt_period(c)))

                            col_info.sort(key=lambda x: (x[0] is None, x[0] or pd.Timestamp.max))
                            pivot_df = pivot_df[[c[1] for c in col_info]]
                            pivot_df.columns = [c[2] for c in col_info]

                            # Robust scaling: clamp to 5th/95th percentiles to avoid outlier washout
                            vals = pivot_df.to_numpy().ravel()
                            vals = vals[~np.isnan(vals)]
                            if len(vals) > 0:
                                vmin = np.percentile(vals, 5)
                                vmax = np.percentile(vals, 95)
                                if vmin == vmax:
                                    pad = 1 if vmin == 0 else abs(vmin) * 0.1
                                    vmin, vmax = vmin - pad, vmax + pad
                            else:
                                vmin, vmax = -1, 1

                            # Make the scale symmetric around 0 so 0 is truly the midpoint
                            span = max(abs(vmin), abs(vmax), 1e-9)
                            vmin = -span
                            vmax = span

                            zero_tint = "#e3f5eb"  # light green at zero

                            metric_lower = friendly_metric.lower()
                            negative_is_good = any(
                                kw in metric_lower for kw in ["loss", "deficit", "gap"]
                            )
                            # Weather variance/diff: negative is bad
                            if "weather" in metric_lower and any(kw in metric_lower for kw in ["var", "variance", "diff"]):
                                negative_is_good = False
                            # Generic variance/diff defaults to negative bad
                            if not negative_is_good and any(kw in metric_lower for kw in ["var", "variance", "diff"]):
                                negative_is_good = False

                            if negative_is_good:
                                neg_color, pos_color = "#1b9e4b", "#c94a4a"  # green for savings, red for loss
                                colorbar_title = f"{friendly_metric} (neg = saved, pos = loss)"
                            else:
                                neg_color, pos_color = "#c94a4a", "#1b9e4b"  # red for deficit, green for gain
                                colorbar_title = f"{friendly_metric} (neg = worse, pos = better)"

                            colors = [
                                [0.0, neg_color],
                                [0.35, neg_color],
                                [0.5, zero_tint],
                                [0.65, zero_tint],
                                [1.0, pos_color],
                            ]

                            fig = go.Figure()
                            fig.add_trace(
                                go.Heatmap(
                                    z=pivot_df.values,
                                    x=pivot_df.columns,
                                    y=pivot_df.index,
                                    colorscale=colors,
                                    zmin=vmin,
                                    zmax=vmax,
                                    zmid=0,
                                    colorbar=dict(
                                        orientation="h",
                                        yanchor="bottom",
                                        y=1.08,
                                        x=0.5,
                                        xanchor="center",
                                        len=0.7,
                                        title=colorbar_title,
                                    ),
                                    xgap=1,
                                    ygap=1,
                                    hovertemplate="Site: %{y}<br>Period: %{x}<br>%{z:.0f} kWh<extra></extra>",
                                )
                            )

                            # Overlay a grey mask for NaNs so they stand out from true zeros
                            nan_mask = pivot_df.isna().astype(float)
                            if nan_mask.to_numpy().sum() > 0:
                                fig.add_trace(
                                    go.Heatmap(
                                        z=nan_mask.values,
                                        x=pivot_df.columns,
                                        y=pivot_df.index,
                                        colorscale=[[0, "rgba(0,0,0,0)"], [1, "#e8ecef"]],
                                        showscale=False,
                                        hoverinfo="skip",
                                        xgap=1,
                                        ygap=1,
                                    )
                                )

                            fig.update_xaxes(showgrid=False, title=None)
                            fig.update_yaxes(showgrid=False, title=None)
                            subtitle = "Green = Energy Saved (Negative) | Red = Energy Loss (Positive)" if negative_is_good else "Red = Deficit (Negative) | Green = Better (Positive)"

                            fig.update_layout(
                                margin=dict(l=10, r=10, t=60, b=10),
                                title=dict(
                                    text=f"<b>{friendly_metric} by Site</b><br><sup>{subtitle}</sup>",
                                    x=0.0,
                                ),
                                hovermode="closest",
                                paper_bgcolor="#ffffff",
                                plot_bgcolor="#ffffff",
                            )
                            st.plotly_chart(fig, use_container_width=True)
                            report_button_fn = globals().get('add_to_report_button')
                            if callable(report_button_fn):
                                report_button_fn(
                                    content=fig,
                                    title=f"{metric} Heatmap",
                                    item_type='chart',
                                    description=f"Heatmap of {metric} by site and period",
                                    source_page="KPI Analysis",
                                    button_key=f"add_heatmap_{metric}".replace(' ', '_').replace('(', '').replace(')', '')
                                )
                        except Exception as e:
                            st.error(f"Could not create heatmap: {e}")
                    else:
                        st.info("Heatmap requires grouping by both Site and Period.")

                # --- DUAL AXIS (Energy vs Ratio) ---
                elif len(chart_metrics) == 2 and chart_type in ["Line", "Bar"]:
                    # Check for mixed types
                    m1, m2 = chart_metrics[0], chart_metrics[1]
                    is_energy_1 = m1 in selected_energy
                    is_ratio_1 = m1 in selected_ratios
                    is_energy_2 = m2 in selected_energy
                    is_ratio_2 = m2 in selected_ratios

                    if (is_energy_1 and is_ratio_2) or (is_ratio_1 and is_energy_2):
                        fig = make_subplots(specs=[[{"secondary_y": True}]])

                        # Trace 1 (Left Axis)
                        if chart_type == "Bar":
                            fig.add_trace(go.Bar(x=results_df[x_col], y=results_df[m1], name=m1), secondary_y=False)
                        else:
                            fig.add_trace(
                                go.Scatter(x=results_df[x_col], y=results_df[m1], name=m1, mode="lines+markers"),
                                secondary_y=False,
                            )

                        # Trace 2 (Right Axis) - Always Line for clarity
                        fig.add_trace(
                            go.Scatter(x=results_df[x_col], y=results_df[m2], name=m2, mode="lines+markers"),
                            secondary_y=True,
                        )

                        chart_title = f"{m1} vs {m2}"
                        fig.update_layout(title=chart_title)
                        fig.update_yaxes(title_text=m1, secondary_y=False)
                        fig.update_yaxes(title_text=m2, secondary_y=True)
                        st.plotly_chart(fig, use_container_width=True)
                        report_button_fn = globals().get('add_to_report_button')
                        if callable(report_button_fn):
                            report_button_fn(
                                content=fig,
                                title=chart_title,
                                item_type='chart',
                                description=f"Dual-axis chart comparing {m1} and {m2}",
                                source_page="KPI Analysis",
                                button_key=f"add_dual_{m1}_{m2}".replace(' ', '_').replace('(', '').replace(')', '').replace('%', 'pct')
                            )
                    else:
                        # Standard plot for same types
                        _standard_plot(results_df, x_col, chart_metrics, chart_type, color_col)

                # --- STANDARD PLOT ---
                else:
                    _standard_plot(results_df, x_col, chart_metrics, chart_type, color_col)

        # ─────────────────────────────────────────────────────────────
        # EXPORT
        # ─────────────────────────────────────────────────────────────
        st.divider()

        col1, col2 = st.columns(2)

        with col1:
            csv = results_df.to_csv(index=False)
            st.download_button("📥 Download CSV", csv, "kpi_results.csv", "text/csv", use_container_width=True)

        with col2:
            try:
                output = BytesIO()
                with pd.ExcelWriter(output, engine="openpyxl") as writer:
                    results_df.to_excel(writer, index=False, sheet_name="KPIs")
                st.download_button(
                    "📥 Download Excel",
                    output.getvalue(),
                    "kpi_results.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
            except:
                pass
