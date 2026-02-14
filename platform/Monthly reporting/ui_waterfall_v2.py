"""
Waterfall Chart Tab Module (Version 2)

This module provides an interactive waterfall chart visualization for solar
loss analysis. Features include:
- Dynamic filtering by site, type, and date range
- Multiple period views (Monthly, Quarterly, YTD, Annual)
- Breakdown from Budget → Weather Variance → WAB → Technical Losses → Actual
- Efficiency loss calculations
- Export capabilities

The waterfall chart helps identify where generation deviates from budget
and quantifies weather vs. technical performance impacts.
"""

from io import BytesIO
from typing import Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

from analysis import SolarDataAnalyzer, weighted_average

# Optional report button (injected when running inside unified app)
add_to_report_button = None
try:
    from components.report_button import add_to_report_button  # type: ignore
except ImportError:
    import sys
    from pathlib import Path

    unified_app_path = Path(__file__).parent.parent / "unified_app"
    if unified_app_path.exists() and str(unified_app_path) not in sys.path:
        sys.path.insert(0, str(unified_app_path))
        try:
            from components.report_button import add_to_report_button  # type: ignore
        except ImportError:
            add_to_report_button = None


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


def create_waterfall_figure(budget, weather_var, wab, efficiency_loss, actual, title=""):
    """Create a waterfall chart figure."""
    labels = ["Budget Gen", "Weather Δ", "WAB", "Efficiency Loss", "Actual Gen"]
    measures = ["absolute", "relative", "total", "relative", "total"]
    values = [budget, weather_var, wab, -efficiency_loss, actual]

    fig = go.Figure(
        go.Waterfall(
            name="Loss Waterfall",
            orientation="v",
            measure=measures,
            x=labels,
            y=values,
            text=[f"{v:,.0f}" for v in values],
            textposition="outside",
            connector={"line": {"color": "rgb(63, 63, 63)"}},
            increasing={"marker": {"color": "#28A745"}},
            decreasing={"marker": {"color": "#DC3545"}},
            totals={"marker": {"color": "#2E86AB"}},
        )
    )

    fig.update_layout(
        title=title or "Solar Loss Waterfall: Budget to Actual Energy",
        yaxis_title="Energy (kWh)",
        showlegend=False,
        height=450,
        margin=dict(l=20, r=20, t=60, b=20),
    )

    return fig


def render_waterfall_tab_v2(tab, extractor):
    """
    Improved waterfall tab with filtering and period views.
    """
    with tab:
        st.header("🌊 Portfolio Loss Waterfall")

        tables = extractor.list_tables()
        if not tables:
            st.warning("Upload data first.")
            return

        source_tbl = st.selectbox("📁 Data Source", list(tables), key="wf_table")
        colmap = st.session_state.get("colmap", {})

        if not colmap or not st.session_state.get("colmap_confirmed"):
            st.error("Column mapping not confirmed. Go to Upload tab first.")
            return

        # Load data
        session_key = f"res_{source_tbl}"

        if session_key in st.session_state:
            df = st.session_state[session_key].copy()
        else:
            ok, df = extractor.query_data(f"SELECT * FROM {source_tbl}")
            if not ok or isinstance(df, str) or df.empty:
                st.error("Could not load data.")
                return

            # Auto-calculate losses
            try:
                analyzer = SolarDataAnalyzer(df, colmap)
                df = analyzer.compute_losses()
                st.session_state[session_key] = df
            except Exception as e:
                st.warning(f"Could not calculate losses: {e}")

        # Clean numeric columns
        budget_col = colmap.get("budget_gen")
        actual_col = colmap.get("actual_gen")
        wab_col = colmap.get("wab")

        for col in [budget_col, actual_col, wab_col]:
            if col and col in df.columns:
                df[col] = clean_numeric(df[col])

        st.success(f"✓ Loaded {len(df):,} rows from '{source_tbl}'")

        # ─────────────────────────────────────────────────────────────
        # FILTERS
        # ─────────────────────────────────────────────────────────────
        st.subheader("🔍 Filters")

        col1, col2, col3 = st.columns(3)

        # Site filter
        site_col = colmap.get("site")
        if not site_col:
            for c in df.columns:
                if "site" in c.lower():
                    site_col = c
                    break

        selected_sites = []
        with col1:
            if site_col and site_col in df.columns:
                all_sites = sorted(df[site_col].dropna().unique().tolist())
                site_mode = st.radio(
                    "📍 Site Selection", ["All Sites (Portfolio)", "Select Sites"], horizontal=True, key="wf_site_mode"
                )
                if site_mode == "Select Sites":
                    selected_sites = st.multiselect(
                        "Choose sites",
                        options=all_sites,
                        default=all_sites[:1] if all_sites else [],
                        key="wf_site_select",
                    )
            else:
                st.info("No site column found")

        # Date filter
        date_col = colmap.get("date")
        if not date_col:
            for c in df.columns:
                if "date" in c.lower():
                    date_col = c
                    break

        date_range = None
        with col2:
            if date_col and date_col in df.columns:
                df["_date"] = parse_dates(df[date_col])
                valid_dates = df["_date"].dropna()
                if not valid_dates.empty:
                    min_date = valid_dates.min().date()
                    max_date = valid_dates.max().date()
                    use_date_filter = st.checkbox("📅 Filter by Date", value=False, key="wf_use_date")
                    if use_date_filter:
                        date_range = st.date_input(
                            "Date Range",
                            value=(min_date, max_date),
                            min_value=min_date,
                            max_value=max_date,
                            key="wf_date_range",
                        )
            else:
                st.info("No date column found")

        # Type filter
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
                    "🏭 Asset Type", options=all_types, default=[], placeholder="All types", key="wf_type_select"
                )
            else:
                st.info("No type column found")

        # Apply filters
        df_filtered = df.copy()
        if selected_sites and site_col:
            df_filtered = df_filtered[df_filtered[site_col].isin(selected_sites)]
        if date_range and len(date_range) == 2 and "_date" in df_filtered.columns:
            start, end = date_range
            df_filtered = df_filtered[
                (df_filtered["_date"] >= pd.Timestamp(start)) & (df_filtered["_date"] <= pd.Timestamp(end))
            ]
        if selected_types and type_col:
            df_filtered = df_filtered[df_filtered[type_col].isin(selected_types)]

        st.caption(f"**{len(df_filtered):,} records** after filtering")

        if df_filtered.empty:
            st.warning("No data matches your filters.")
            return

        st.divider()

        # ─────────────────────────────────────────────────────────────
        # VIEW OPTIONS
        # ─────────────────────────────────────────────────────────────
        st.subheader("👁️ View Options")

        view_col1, view_col2 = st.columns(2)

        with view_col1:
            view_mode = st.selectbox(
                "Group by", ["Total (Summary)", "By Period", "By Site", "By Type"], key="wf_view_mode"
            )

        with view_col2:
            if view_mode == "By Period":
                period_type = st.selectbox(
                    "Period type", ["Monthly", "Quarterly", "YTD", "Annual"], key="wf_period_type"
                )
            else:
                period_type = "Monthly"

        st.divider()

        # ─────────────────────────────────────────────────────────────
        # ADD PERIOD COLUMN IF NEEDED
        # ─────────────────────────────────────────────────────────────
        if view_mode == "By Period" and "_date" in df_filtered.columns:
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
            elif period_type == "YTD":
                month = dates.dt.month
                year = dates.dt.year
                fy = np.where(month < fiscal_start, year, year + 1)
                df_filtered["Period"] = "YTD FY" + fy.astype(str)
            else:  # Annual
                month = dates.dt.month
                year = dates.dt.year
                fy = np.where(month < fiscal_start, year, year + 1)
                df_filtered["Period"] = "FY" + fy.astype(str)

        # ─────────────────────────────────────────────────────────────
        # CALCULATE AND DISPLAY
        # ─────────────────────────────────────────────────────────────

        def calc_waterfall_metrics(data):
            """Calculate waterfall metrics for a dataframe."""
            budget = data[budget_col].sum() if budget_col and budget_col in data.columns else 0
            actual = data[actual_col].sum() if actual_col and actual_col in data.columns else 0
            wab = data[wab_col].sum() if wab_col and wab_col in data.columns else 0

            weather_var = wab - budget
            efficiency_loss = wab - actual

            avail_loss = data["Loss_Avail_kWh"].sum() if "Loss_Avail_kWh" in data.columns else 0
            if pd.isna(avail_loss):
                avail_loss = 0

            return {
                "Budget": budget,
                "Actual": actual,
                "WAB": wab,
                "Weather Var": weather_var,
                "Efficiency Loss": efficiency_loss,
                "Avail Loss": avail_loss,
            }

        if view_mode == "Total (Summary)":
            # ─────────────────────────────────────────────────────────
            # SINGLE PORTFOLIO WATERFALL
            # ─────────────────────────────────────────────────────────
            metrics = calc_waterfall_metrics(df_filtered)

            # Summary metrics
            st.subheader("📊 Portfolio Summary")

            m1, m2, m3, m4 = st.columns(4)
            with m1:
                st.metric("Budget Gen", f"{metrics['Budget']:,.0f} kWh")
            with m2:
                st.metric("Actual Gen", f"{metrics['Actual']:,.0f} kWh")
            with m3:
                var_pct = (
                    ((metrics["Actual"] - metrics["Budget"]) / metrics["Budget"] * 100) if metrics["Budget"] else 0
                )
                st.metric("Variance", f"{metrics['Actual'] - metrics['Budget']:,.0f} kWh", delta=f"{var_pct:+.1f}%")
            with m4:
                st.metric("WAB", f"{metrics['WAB']:,.0f} kWh")

            st.divider()

            # Waterfall chart
            st.subheader("📉 Loss Waterfall")
            fig = create_waterfall_figure(
                metrics["Budget"],
                metrics["Weather Var"],
                metrics["WAB"],
                metrics["Efficiency Loss"],
                metrics["Actual"],
                "Portfolio Loss Waterfall",
            )
            st.plotly_chart(fig, use_container_width=True)
            if callable(add_to_report_button):
                add_to_report_button(
                    content=fig,
                    title="Portfolio Loss Waterfall",
                    item_type="chart",
                    description="Budget to Actual generation waterfall with weather and efficiency impacts",
                    source_page="Waterfall",
                    button_key="add_portfolio_loss_waterfall"
                )

            # Loss breakdown
            st.subheader("📋 Loss Breakdown")
            other_loss = metrics["Efficiency Loss"] - metrics["Avail Loss"]

            breakdown_df = pd.DataFrame(
                [
                    {
                        "Component": "Weather Variance",
                        "kWh": metrics["Weather Var"],
                        "% of Budget": metrics["Weather Var"] / metrics["Budget"] * 100 if metrics["Budget"] else 0,
                    },
                    {
                        "Component": "Availability Loss",
                        "kWh": -metrics["Avail Loss"],
                        "% of Budget": -metrics["Avail Loss"] / metrics["Budget"] * 100 if metrics["Budget"] else 0,
                    },
                    {
                        "Component": "Other Losses",
                        "kWh": -other_loss,
                        "% of Budget": -other_loss / metrics["Budget"] * 100 if metrics["Budget"] else 0,
                    },
                    {
                        "Component": "Total Efficiency Loss",
                        "kWh": -metrics["Efficiency Loss"],
                        "% of Budget": (
                            -metrics["Efficiency Loss"] / metrics["Budget"] * 100 if metrics["Budget"] else 0
                        ),
                    },
                ]
            )

            breakdown_df["kWh"] = breakdown_df["kWh"].apply(lambda x: f"{x:,.0f}")
            breakdown_df["% of Budget"] = breakdown_df["% of Budget"].apply(lambda x: f"{x:+.2f}%")
            st.dataframe(breakdown_df, hide_index=True, use_container_width=True)
            if callable(add_to_report_button):
                add_to_report_button(
                    content=breakdown_df,
                    title="Loss Breakdown Table",
                    item_type="table",
                    description="Breakdown of weather, availability, and efficiency losses",
                    source_page="Waterfall",
                    button_key="add_loss_breakdown_table"
                )

        else:
            # ─────────────────────────────────────────────────────────
            # GROUPED WATERFALL (By Period, Site, or Type)
            # ─────────────────────────────────────────────────────────

            # Determine grouping column
            if view_mode == "By Period":
                group_col = "Period"
            elif view_mode == "By Site":
                group_col = site_col
            else:  # By Type
                group_col = type_col

            if not group_col or group_col not in df_filtered.columns:
                st.warning(f"Cannot group by {view_mode} - column not found.")
                return

            # Calculate metrics for each group
            results = []
            for group_val, group_df in df_filtered.groupby(group_col):
                metrics = calc_waterfall_metrics(group_df)
                metrics[group_col] = group_val
                results.append(metrics)

            results_df = pd.DataFrame(results)

            # Sort
            if group_col == "Period":
                results_df = results_df.sort_values("Period")

            # Summary table
            st.subheader(f"📊 Summary by {view_mode.replace('By ', '')}")

            display_df = results_df.copy()
            display_df["Budget"] = display_df["Budget"].apply(lambda x: f"{x:,.0f}")
            display_df["Actual"] = display_df["Actual"].apply(lambda x: f"{x:,.0f}")
            display_df["WAB"] = display_df["WAB"].apply(lambda x: f"{x:,.0f}")
            display_df["Weather Var"] = display_df["Weather Var"].apply(lambda x: f"{x:+,.0f}")
            display_df["Efficiency Loss"] = display_df["Efficiency Loss"].apply(lambda x: f"{x:,.0f}")

            # Reorder columns
            cols = [group_col, "Budget", "WAB", "Weather Var", "Efficiency Loss", "Actual"]
            display_df = display_df[[c for c in cols if c in display_df.columns]]

            st.dataframe(display_df, hide_index=True, use_container_width=True)

            st.divider()

            # ─────────────────────────────────────────────────────────
            # CHART OPTIONS
            # ─────────────────────────────────────────────────────────
            st.subheader("📈 Visualization")

            chart_option = st.radio(
                "Chart Type",
                ["Stacked Bar (Budget vs Actual)", "Waterfall per Group", "Variance Trend"],
                horizontal=True,
                key="wf_chart_option",
            )

            if chart_option == "Stacked Bar (Budget vs Actual)":
                fig = go.Figure()

                fig.add_trace(
                    go.Bar(name="Budget", x=results_df[group_col], y=results_df["Budget"], marker_color="#2E86AB")
                )

                fig.add_trace(
                    go.Bar(name="Actual", x=results_df[group_col], y=results_df["Actual"], marker_color="#28A745")
                )

                fig.update_layout(
                    title=f"Budget vs Actual by {view_mode.replace('By ', '')}",
                    barmode="group",
                    yaxis_title="Energy (kWh)",
                    height=450,
                )

                st.plotly_chart(fig, use_container_width=True)

            elif chart_option == "Waterfall per Group":
                # Select which group to show waterfall for
                selected_group = st.selectbox(
                    f"Select {view_mode.replace('By ', '')}", results_df[group_col].tolist(), key="wf_select_group"
                )

                group_metrics = results_df[results_df[group_col] == selected_group].iloc[0]

                fig = create_waterfall_figure(
                    group_metrics["Budget"],
                    group_metrics["Weather Var"],
                    group_metrics["WAB"],
                    group_metrics["Efficiency Loss"],
                    group_metrics["Actual"],
                    f"Loss Waterfall: {selected_group}",
                )

                st.plotly_chart(fig, use_container_width=True)

            else:  # Variance Trend
                # Calculate variance percentage
                results_df["Variance %"] = (results_df["Actual"] - results_df["Budget"]) / results_df["Budget"] * 100
                results_df["Efficiency Loss %"] = results_df["Efficiency Loss"] / results_df["WAB"] * 100

                fig = go.Figure()

                fig.add_trace(
                    go.Scatter(
                        name="Budget Variance %",
                        x=results_df[group_col],
                        y=results_df["Variance %"],
                        mode="lines+markers",
                        line=dict(color="#2E86AB", width=2),
                        marker=dict(size=8),
                    )
                )

                fig.add_trace(
                    go.Scatter(
                        name="Efficiency Loss %",
                        x=results_df[group_col],
                        y=results_df["Efficiency Loss %"],
                        mode="lines+markers",
                        line=dict(color="#DC3545", width=2),
                        marker=dict(size=8),
                    )
                )

                fig.add_hline(y=0, line_dash="dash", line_color="gray")

                fig.update_layout(
                    title=f"Variance Trends by {view_mode.replace('By ', '')}", yaxis_title="Percentage (%)", height=450
                )

                st.plotly_chart(fig, use_container_width=True)

        # ─────────────────────────────────────────────────────────────
        # EXPORT
        # ─────────────────────────────────────────────────────────────
        st.divider()

        if view_mode != "Total (Summary)":
            col1, col2 = st.columns(2)
            with col1:
                csv = results_df.to_csv(index=False)
                st.download_button("📥 Download CSV", csv, "waterfall_data.csv", "text/csv", use_container_width=True)
            with col2:
                try:
                    output = BytesIO()
                    with pd.ExcelWriter(output, engine="openpyxl") as writer:
                        results_df.to_excel(writer, index=False, sheet_name="Waterfall")
                    st.download_button(
                        "📥 Download Excel",
                        output.getvalue(),
                        "waterfall_data.xlsx",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                    )
                except:
                    pass
