"""
ExCom Operational Report Module
===============================
Replicates the AMPYR ExCom operational performance report format.
Includes monthly and YTD waterfalls, KPI cards, and portfolio summary table.

Uses calculations from analysis.py:
- Loss_Total_Tech_kWh = WAB - Actual
- Var_Weather_kWh = WAB - Budget
- Loss_PR_kWh = WAB * (PR_budget - PR_actual)
- Loss_Avail_kWh = WAB * (0.99 - Availability)

Waterfall presentation rules (ExCom style):
- Visual steps: Budget → Irradiance → Availability → Efficiency → Actual
- Negative loss is a positive bar in the waterfall (a “good” loss).
- Efficiency is the balancing item after WAB and Availability have been considered:
    Budget + Irradiance + Availability + Efficiency = Actual
"""

from io import BytesIO
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from config import Config

try:
    from analysis import SolarDataAnalyzer, weighted_average
except ImportError:
    SolarDataAnalyzer = None
    weighted_average = None

# Try to import report button from unified app (may be injected at runtime)
add_to_report_button = None
try:
    from components.report_button import add_to_report_button
except ImportError:
    import sys
    from pathlib import Path
    unified_app_path = Path(__file__).parent.parent / "unified_app"
    if unified_app_path.exists() and str(unified_app_path) not in sys.path:
        sys.path.insert(0, str(unified_app_path))
        try:
            from components.report_button import add_to_report_button
        except ImportError:
            pass

# Try to import brand colours, fall back to defaults
try:
    from brand_theme import BRAND_COLOURS, CHART_COLORWAY
except ImportError:
    BRAND_COLOURS = {
        "primary": "#1B4D5C",
        "secondary": "#2D8B9E",
        "positive": "#2D8B5F",
        "negative": "#C94A4A",
        "accent": "#D4A84B",
        "surface": "#FFFFFF",
        "border": "#DCE4E8",
        "text": "#1B4D5C",
        "text_secondary": "#5A7A85",
        "muted_text": "#8DA4AD",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# WATERFALL CHART HELPERS - EXCOM STYLE
# ═══════════════════════════════════════════════════════════════════════════════


def build_excom_waterfall_steps(
    budget: float,
    weather_var: float,
    avail_loss: float,
    actual: float,
) -> Dict[str, float]:
    """
    Build the visible ExCom steps from the underlying components.

    Inputs (analysis space):
      budget      : Budget generation (MWh)
      weather_var : Var_Weather_kWh = WAB - Budget   (irradiance impact)
      avail_loss  : Loss_Avail_kWh = WAB * (0.99 - Availability)
      actual      : Actual generation (MWh)

    Outputs (chart space):
      budget        : Budget
      irradiance    : Irradiance step (can be +/-)
      availability  : Availability step (negative loss = positive bar)
      efficiency    : Balancing item after availability so that we land on actual
      actual        : Actual

    Rules:
    - Negative availability loss = positive availability bar.
    - Efficiency is balancing:
        Budget + Irradiance + Availability + Efficiency = Actual
    """

    # Normalise None / NaN
    budget = 0.0 if budget is None or pd.isna(budget) else float(budget)
    weather_var = 0.0 if weather_var is None or pd.isna(weather_var) else float(weather_var)
    actual = 0.0 if actual is None or pd.isna(actual) else float(actual)

    # Irradiance step is just the weather variance (can be positive or negative)
    irradiance = weather_var

    # Availability step: negative loss => positive bar (good),
    # positive loss => negative bar (bad)
    if avail_loss is None or pd.isna(avail_loss):
        avail_loss = 0.0
    else:
        avail_loss = float(avail_loss)

    availability_step = -avail_loss

    # After applying availability to WAB (Budget + Irradiance)
    after_availability = budget + irradiance + availability_step

    # Efficiency is whatever is needed to land exactly on Actual
    efficiency_step = actual - after_availability

    return {
        "budget": budget,
        "irradiance": irradiance,
        "availability": availability_step,
        "efficiency": efficiency_step,
        "actual": actual,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# WATERFALL CHART - EXCOM STYLE
# ═══════════════════════════════════════════════════════════════════════════════


def create_excom_waterfall(
    budget: float,
    weather_var: float,
    wab: float,
    pr_loss: float,
    avail_loss: float,
    actual: float,
    title: str = "Performance",
    height: int = 400,
) -> go.Figure:
    """
    Create ExCom-style waterfall chart.

    Visual structure (matching ExCom report):
        Budget → Irradiance → Availability → Efficiency → Actual

    Args:
        budget: Budget generation (MWh)
        weather_var: Var_Weather_kWh = WAB - Budget  (irradiance impact)
        wab: Weather-adjusted budget (not shown directly; used for consistency with analysis)
        pr_loss: Loss_PR_kWh = WAB * (PR_budget - PR_actual)  (used implicitly; residual goes into Efficiency)
        avail_loss: Loss_Avail_kWh = WAB * (0.99 - Availability)
        actual: Actual generation (MWh)
        title: Chart title
        height: Chart height in pixels

    Rules:
    - A negative loss is a positive bar in the waterfall.
    - Efficiency is a balancing item after WAB and Availability have been considered.
    """

    # Map underlying components into visible steps
    steps = build_excom_waterfall_steps(
        budget=budget,
        weather_var=weather_var,
        avail_loss=avail_loss,
        actual=actual,
    )

    labels = ["Budget", "Irradiance", "Availability", "Efficiency", "Actual"]
    measures = ["absolute", "relative", "relative", "relative", "total"]
    values = [
        steps["budget"],
        steps["irradiance"],
        steps["availability"],
        steps["efficiency"],
        steps["actual"],
    ]

    fig = go.Figure()

    fig.add_trace(
        go.Waterfall(
            name="Performance",
            orientation="v",
            measure=measures,
            x=labels,
            y=values,
            text=[f"{v:,.0f}" for v in values],
            textposition="outside",
            textfont=dict(size=11, color=BRAND_COLOURS["text"]),
            connector=dict(line=dict(color=BRAND_COLOURS["border"], width=1, dash="dot")),
            increasing=dict(marker=dict(color=BRAND_COLOURS["positive"])),
            decreasing=dict(marker=dict(color=BRAND_COLOURS["negative"])),
            totals=dict(marker=dict(color=BRAND_COLOURS["primary"])),
        )
    )

    fig.update_layout(
        title=dict(text=title, font=dict(size=16, color=BRAND_COLOURS["primary"]), x=0.5, xanchor="center"),
        showlegend=False,
        height=height,
        paper_bgcolor=BRAND_COLOURS["surface"],
        plot_bgcolor=BRAND_COLOURS["surface"],
        yaxis=dict(
            title="Generation (MWh)",
            gridcolor=BRAND_COLOURS["border"],
            tickformat=",",
        ),
        xaxis=dict(
            tickfont=dict(size=11),
        ),
        margin=dict(l=60, r=40, t=60, b=40),
    )

    return fig


def create_dual_waterfall(
    monthly_components: Dict[str, float],
    ytd_components: Dict[str, float],
    month_name: str = "October 2025",
) -> go.Figure:
    """
    Create side-by-side monthly and YTD ExCom-style waterfall charts.

    Inputs are the *analysis-space* components, typically the output of
    calculate_waterfall_components():

        {
            "budget": ...,
            "weather_var": ...,
            "wab": ...,
            "pr_loss": ...,
            "avail_loss": ...,
            "total_tech_loss": ...,
            "actual": ...
        }

    This function then applies the ExCom presentation rules:
    - Visual steps: Budget → Irradiance → Availability → Efficiency → Actual
    - Negative loss is a positive bar.
    - Efficiency is the balancing item after WAB & Availability.
    """

    # Build visible steps for Monthly and YTD
    m_steps = build_excom_waterfall_steps(
        budget=monthly_components.get("budget", 0.0),
        weather_var=monthly_components.get("weather_var", 0.0),
        avail_loss=monthly_components.get("avail_loss", 0.0),
        actual=monthly_components.get("actual", 0.0),
    )

    y_steps = build_excom_waterfall_steps(
        budget=ytd_components.get("budget", 0.0),
        weather_var=ytd_components.get("weather_var", 0.0),
        avail_loss=ytd_components.get("avail_loss", 0.0),
        actual=ytd_components.get("actual", 0.0),
    )

    fig = make_subplots(
        rows=1,
        cols=2,
        subplot_titles=[f"Performance {month_name}", "Performance YTD"],
        horizontal_spacing=0.1,
    )

    labels = ["Budget", "Irradiance", "Availability", "Efficiency", "Actual"]
    measures = ["absolute", "relative", "relative", "relative", "total"]

    monthly_values = [
        m_steps["budget"],
        m_steps["irradiance"],
        m_steps["availability"],
        m_steps["efficiency"],
        m_steps["actual"],
    ]

    ytd_values = [
        y_steps["budget"],
        y_steps["irradiance"],
        y_steps["availability"],
        y_steps["efficiency"],
        y_steps["actual"],
    ]

    # Monthly waterfall
    fig.add_trace(
        go.Waterfall(
            name="Monthly",
            orientation="v",
            measure=measures,
            x=labels,
            y=monthly_values,
            text=[f"{v:,.0f}" for v in monthly_values],
            textposition="outside",
            connector=dict(line=dict(color=BRAND_COLOURS["border"], width=1)),
            increasing=dict(marker=dict(color=BRAND_COLOURS["positive"])),
            decreasing=dict(marker=dict(color=BRAND_COLOURS["negative"])),
            totals=dict(marker=dict(color=BRAND_COLOURS["secondary"])),
        ),
        row=1,
        col=1,
    )

    # YTD waterfall
    fig.add_trace(
        go.Waterfall(
            name="YTD",
            orientation="v",
            measure=measures,
            x=labels,
            y=ytd_values,
            text=[f"{v:,.0f}" for v in ytd_values],
            textposition="outside",
            connector=dict(line=dict(color=BRAND_COLOURS["border"], width=1)),
            increasing=dict(marker=dict(color=BRAND_COLOURS["positive"])),
            decreasing=dict(marker=dict(color=BRAND_COLOURS["negative"])),
            totals=dict(marker=dict(color=BRAND_COLOURS["secondary"])),
        ),
        row=1,
        col=2,
    )

    fig.update_layout(
        showlegend=False,
        height=450,
        paper_bgcolor=BRAND_COLOURS["surface"],
        plot_bgcolor=BRAND_COLOURS["surface"],
        margin=dict(l=60, r=40, t=80, b=40),
    )

    fig.update_yaxes(gridcolor=BRAND_COLOURS["border"], tickformat=",")

    return fig


# ═══════════════════════════════════════════════════════════════════════════════
# KPI GAUGE CARDS
# ═══════════════════════════════════════════════════════════════════════════════


def create_kpi_gauge(
    value: float,
    target: float,
    title: str,
    suffix: str = "%",
    min_val: float = 0,
    max_val: float = 100,
) -> go.Figure:
    """Create a gauge chart for KPI display."""

    # Determine color based on performance vs target
    if value >= target:
        bar_color = BRAND_COLOURS["positive"]
    else:
        bar_color = BRAND_COLOURS["negative"]

    fig = go.Figure(
        go.Indicator(
            mode="gauge+number+delta",
            value=value,
            number=dict(suffix=suffix, font=dict(size=28, color=BRAND_COLOURS["primary"])),
            delta=dict(
                reference=target,
                relative=False,
                valueformat=".1f",
                increasing=dict(color=BRAND_COLOURS["positive"]),
                decreasing=dict(color=BRAND_COLOURS["negative"]),
            ),
            title=dict(text=title, font=dict(size=14, color=BRAND_COLOURS["text_secondary"])),
            gauge=dict(
                axis=dict(range=[min_val, max_val], ticksuffix=suffix),
                bar=dict(color=bar_color),
                bgcolor=BRAND_COLOURS["border"],
                borderwidth=0,
                threshold=dict(line=dict(color=BRAND_COLOURS["primary"], width=2), thickness=0.75, value=target),
            ),
        )
    )

    fig.update_layout(
        height=200,
        margin=dict(l=20, r=20, t=50, b=20),
        paper_bgcolor=BRAND_COLOURS["surface"],
    )

    return fig


def display_kpi_cards(
    pr_actual: float,
    pr_forecast: float,
    avail_actual: float,
    avail_forecast: float,
    pr_ytd: float,
    pr_ytd_forecast: float,
    avail_ytd: float,
    avail_ytd_forecast: float,
):
    """Display KPIs as bar charts in ExCom style."""
    # Get the report button function dynamically (may be injected at runtime)
    report_button_fn = globals().get('add_to_report_button')

    st.subheader("Technical KPIs")

    col1, col2 = st.columns(2)

    # Monthly KPIs
    with col1:
        kpi_data = {
            "Metric": ["PR", "Availability"],
            "Actual": [pr_actual, avail_actual],
            "Forecast": [pr_forecast, avail_forecast],
        }
        kpi_df = pd.DataFrame(kpi_data)

        fig_monthly = go.Figure(
            data=[
                go.Bar(name="Actual", x=kpi_df["Metric"], y=kpi_df["Actual"], marker_color=BRAND_COLOURS["primary"]),
                go.Bar(
                    name="Forecast", x=kpi_df["Metric"], y=kpi_df["Forecast"], marker_color=BRAND_COLOURS["secondary"]
                ),
            ]
        )

        fig_monthly.update_layout(
            title="Monthly KPIs",
            barmode="group",
            yaxis_title="Percentage (%)",
            height=350,
            showlegend=True,
            paper_bgcolor=BRAND_COLOURS["surface"],
            plot_bgcolor=BRAND_COLOURS["surface"],
            font=dict(color=BRAND_COLOURS["text"]),
            yaxis=dict(range=[0, 105], gridcolor=BRAND_COLOURS["border"]),
            xaxis=dict(gridcolor=BRAND_COLOURS["border"]),
        )

        st.plotly_chart(fig_monthly, use_container_width=True)
        if callable(report_button_fn):
            report_button_fn(
                content=fig_monthly,
                title="Monthly KPIs - PR & Availability",
                item_type='chart',
                description="Monthly PR and Availability vs Forecast",
                source_page="ExCom Report",
                button_key="add_kpi_monthly"
            )

    # YTD KPIs
    with col2:
        kpi_ytd_data = {
            "Metric": ["PR", "Availability"],
            "Actual": [pr_ytd, avail_ytd],
            "Forecast": [pr_ytd_forecast, avail_ytd_forecast],
        }
        kpi_ytd_df = pd.DataFrame(kpi_ytd_data)

        fig_ytd = go.Figure(
            data=[
                go.Bar(
                    name="Actual", x=kpi_ytd_df["Metric"], y=kpi_ytd_df["Actual"], marker_color=BRAND_COLOURS["primary"]
                ),
                go.Bar(
                    name="Forecast",
                    x=kpi_ytd_df["Metric"],
                    y=kpi_ytd_df["Forecast"],
                    marker_color=BRAND_COLOURS["secondary"],
                ),
            ]
        )

        fig_ytd.update_layout(
            title="YTD KPIs",
            barmode="group",
            yaxis_title="Percentage (%)",
            height=350,
            showlegend=True,
            paper_bgcolor=BRAND_COLOURS["surface"],
            plot_bgcolor=BRAND_COLOURS["surface"],
            font=dict(color=BRAND_COLOURS["text"]),
            yaxis=dict(range=[0, 105], gridcolor=BRAND_COLOURS["border"]),
            xaxis=dict(gridcolor=BRAND_COLOURS["border"]),
        )

        st.plotly_chart(fig_ytd, use_container_width=True)
        if callable(report_button_fn):
            report_button_fn(
                content=fig_ytd,
                title="YTD KPIs - PR & Availability",
                item_type='chart',
                description="Year-to-date PR and Availability vs Forecast",
                source_page="ExCom Report",
                button_key="add_kpi_ytd"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# TECHNICAL LOSSES TABLES - TOP AND BOTTOM PERFORMERS
# ═══════════════════════════════════════════════════════════════════════════════


def create_technical_losses_site_tables(
    df: pd.DataFrame,
    colmap: Dict[str, str],
    period_filter: Optional[str] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Create top 5 and bottom 5 sites tables based on technical losses.

    Args:
        df: DataFrame with site-level data
        colmap: Column mapping dictionary
        period_filter: Optional period filter for specific month

    Returns:
        Tuple of (top_5_df, bottom_5_df) - both DataFrames with Site, Technical Loss, PR, and Availability
    """
    data = df.copy()

    # Apply period filter if provided
    if period_filter:
        date_col = colmap.get("date")
        if date_col and date_col in data.columns:
            data = data[data[date_col] == period_filter]

    # Use SolarDataAnalyzer to compute losses
    if SolarDataAnalyzer:
        analyzer = SolarDataAnalyzer(data, colmap)
        data = analyzer.compute_losses()

    # Get column mappings
    site_col = colmap.get("site")
    pr_col = colmap.get("pr_actual")
    avail_col = colmap.get("availability")
    actual_col = colmap.get("actual_gen")  # Extract once to avoid duplication

    if not site_col or site_col not in data.columns:
        # Return empty dataframes if no site column
        empty_df = pd.DataFrame(columns=["Site", "Technical Loss (kWh)", "PR (%)", "Availability (%)"])
        return empty_df, empty_df

    # Check if losses were calculated
    if "Loss_Total_Tech_kWh" not in data.columns:
        empty_df = pd.DataFrame(columns=["Site", "Technical Loss (kWh)", "PR (%)", "Availability (%)"])
        return empty_df, empty_df

    # Group by site and sum technical losses
    site_summary = data.groupby(site_col).agg(
        {
            "Loss_Total_Tech_kWh": "sum",
        }
    )

    # Check if site_summary is empty
    if site_summary.empty:
        empty_df = pd.DataFrame(columns=["Site", "Technical Loss (kWh)", "PR (%)", "Availability (%)"])
        return empty_df, empty_df

    # Calculate weighted averages for PR and Availability
    if pr_col and pr_col in data.columns:
        if actual_col and actual_col in data.columns:
            # Weighted average PR
            if weighted_average is not None:
                pr_by_site = data.groupby(site_col, group_keys=False).apply(
                    lambda x: weighted_average(x, pr_col, actual_col), include_groups=False
                )
                site_summary["PR"] = pr_by_site
            else:
                site_summary["PR"] = data.groupby(site_col)[pr_col].mean()
        else:
            site_summary["PR"] = data.groupby(site_col)[pr_col].mean()
    else:
        site_summary["PR"] = 0

    if avail_col and avail_col in data.columns:
        if actual_col and actual_col in data.columns:
            # Weighted average Availability
            if weighted_average is not None:
                avail_by_site = data.groupby(site_col, group_keys=False).apply(
                    lambda x: weighted_average(x, avail_col, actual_col), include_groups=False
                )
                site_summary["Availability"] = avail_by_site
            else:
                site_summary["Availability"] = data.groupby(site_col)[avail_col].mean()
        else:
            site_summary["Availability"] = data.groupby(site_col)[avail_col].mean()
    else:
        site_summary["Availability"] = 0

    # Normalize PR and Availability to 0-100 scale if needed
    if not site_summary.empty:
        # Use dropna().max() to handle NaN values
        pr_max = site_summary["PR"].dropna().max() if not site_summary["PR"].isna().all() else 100
        if pd.notna(pr_max) and pr_max <= 1:
            site_summary["PR"] = site_summary["PR"] * 100
        
        avail_max = site_summary["Availability"].dropna().max() if not site_summary["Availability"].isna().all() else 100
        if pd.notna(avail_max) and avail_max <= 1:
            site_summary["Availability"] = site_summary["Availability"] * 100

    # Reset index to have site as a column
    site_summary = site_summary.reset_index()
    site_summary.columns = ["Site", "Technical Loss (kWh)", "PR (%)", "Availability (%)"]

    # Sort by technical loss (descending = worst performers first)
    site_summary = site_summary.sort_values("Technical Loss (kWh)", ascending=False)

    # Get top 5 (worst - highest losses) and bottom 5 (best - lowest losses)
    top_5 = site_summary.head(5).copy()
    bottom_5 = site_summary.tail(5).copy()

    # Sort bottom 5 in ascending order for display
    bottom_5 = bottom_5.sort_values("Technical Loss (kWh)", ascending=True)

    return top_5, bottom_5


def _format_losses_table(df: pd.DataFrame) -> pd.DataFrame:
    """
    Helper function to format technical losses table for display.

    Args:
        df: DataFrame with Site, Technical Loss, PR, and Availability columns

    Returns:
        Formatted DataFrame with proper string formatting
    """
    display_df = df.copy()
    display_df["Technical Loss (kWh)"] = display_df["Technical Loss (kWh)"].apply(
        lambda x: f"{x:,.0f}" if pd.notna(x) else ""
    )
    display_df["PR (%)"] = display_df["PR (%)"].apply(
        lambda x: f"{x:.1f}%" if pd.notna(x) else ""
    )
    display_df["Availability (%)"] = display_df["Availability (%)"].apply(
        lambda x: f"{x:.1f}%" if pd.notna(x) else ""
    )
    return display_df


def display_technical_losses_tables(
    top_5: pd.DataFrame,
    bottom_5: pd.DataFrame,
    period_name: str = "Monthly",
):
    """
    Display top 5 and bottom 5 sites by technical losses with PR and Availability.

    Args:
        top_5: DataFrame with top 5 sites (highest losses)
        bottom_5: DataFrame with bottom 5 sites (lowest losses)
        period_name: Name of the period (e.g., "Monthly", "YTD")
    """
    # Get the report button function dynamically (may be injected at runtime)
    report_button_fn = globals().get('add_to_report_button')

    st.subheader(f"Technical Losses by Site ({period_name})")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### 🔴 Top 5 Sites - Highest Technical Losses")
        if not top_5.empty:
            display_top = _format_losses_table(top_5)
            st.dataframe(
                display_top,
                hide_index=True,
                use_container_width=True,
            )
            if callable(report_button_fn):
                report_button_fn(
                    content=top_5,
                    title=f"Top 5 Sites - Highest Technical Losses ({period_name})",
                    item_type='table',
                    description=f"Sites with highest technical losses for {period_name}",
                    source_page="ExCom Report",
                    button_key=f"add_top5_losses_{period_name}".replace(' ', '_')
                )
        else:
            st.info("No data available")

    with col2:
        st.markdown("#### 🟢 Bottom 5 Sites - Lowest Technical Losses")
        if not bottom_5.empty:
            display_bottom = _format_losses_table(bottom_5)
            st.dataframe(
                display_bottom,
                hide_index=True,
                use_container_width=True,
            )
            if callable(report_button_fn):
                report_button_fn(
                    content=bottom_5,
                    title=f"Bottom 5 Sites - Lowest Technical Losses ({period_name})",
                    item_type='table',
                    description=f"Sites with lowest technical losses for {period_name}",
                    source_page="ExCom Report",
                    button_key=f"add_bottom5_losses_{period_name}".replace(' ', '_')
                )
        else:
            st.info("No data available")


# ═══════════════════════════════════════════════════════════════════════════════
# PORTFOLIO SUMMARY TABLE
# ═══════════════════════════════════════════════════════════════════════════════


def create_portfolio_summary_table(
    data: pd.DataFrame,
    group_column: str = "Type",
    month_name: str = "October 2025",
) -> pd.DataFrame:
    """
    Create the portfolio summary table grouped by asset type.

    Expected columns in data:
    - Type (e.g., "UK (roof solar)", "UK (ground solar)")
    - Sites (count)
    - MWp (capacity)
    - Budget_Monthly, WAB_Monthly, Actual_Monthly
    - Budget_YTD, WAB_YTD, Actual_YTD
    """

    # Calculate variance and revenue impact
    summary = (
        data.groupby(group_column)
        .agg(
            {
                "Sites": "sum",
                "MWp": "sum",
                "Budget_Monthly": "sum",
                "WAB_Monthly": "sum",
                "Actual_Monthly": "sum",
                "Budget_YTD": "sum",
                "WAB_YTD": "sum",
                "Actual_YTD": "sum",
            }
        )
        .reset_index()
    )

    # Add variance columns
    summary["Variance_Monthly"] = summary["Actual_Monthly"] / summary["WAB_Monthly"]
    summary["Variance_YTD"] = summary["Actual_YTD"] / summary["WAB_YTD"]

    # Add totals row
    totals = pd.DataFrame(
        [
            {
                group_column: "Total",
                "Sites": summary["Sites"].sum(),
                "MWp": summary["MWp"].sum(),
                "Budget_Monthly": summary["Budget_Monthly"].sum(),
                "WAB_Monthly": summary["WAB_Monthly"].sum(),
                "Actual_Monthly": summary["Actual_Monthly"].sum(),
                "Budget_YTD": summary["Budget_YTD"].sum(),
                "WAB_YTD": summary["WAB_YTD"].sum(),
                "Actual_YTD": summary["Actual_YTD"].sum(),
            }
        ]
    )
    totals["Variance_Monthly"] = totals["Actual_Monthly"] / totals["WAB_Monthly"]
    totals["Variance_YTD"] = totals["Actual_YTD"] / totals["WAB_YTD"]

    summary = pd.concat([summary, totals], ignore_index=True)

    return summary


def display_portfolio_table(df: pd.DataFrame, month_name: str = "October 2025"):
    """Display the formatted portfolio summary table."""

    # Get the report button function dynamically (may be injected at runtime)
    report_button_fn = globals().get('add_to_report_button')

    # Format for display
    display_df = df.copy()

    # Format numeric columns
    for col in display_df.columns:
        if display_df[col].dtype in ["float64", "int64"]:
            col_lower = col.lower()
            if "variance" in col_lower:
                display_df[col] = display_df[col].apply(lambda x: f"{x:.0%}" if pd.notna(x) and x != 0 else "")
            elif "mwp" in col_lower:
                display_df[col] = display_df[col].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "")
            elif "sites" in col_lower or col == "#":
                display_df[col] = display_df[col].apply(lambda x: f"{int(x)}" if pd.notna(x) else "")
            else:
                display_df[col] = display_df[col].apply(lambda x: f"{x:,.0f}" if pd.notna(x) else "")

    st.dataframe(
        display_df,
        hide_index=True,
        use_container_width=True,
    )

    # Offer export to report if available
    if callable(report_button_fn):
        report_button_fn(
            content=df,
            title=f"Portfolio Summary ({month_name})",
            item_type='table',
            description="Portfolio breakdown by asset type with budget vs actual",
            source_page="ExCom Report",
            button_key=f"add_portfolio_summary_{month_name}".replace(' ', '_')
        )


# ═══════════════════════════════════════════════════════════════════════════════
# DATA CALCULATION HELPERS - ALIGNED WITH analysis.py
# ═══════════════════════════════════════════════════════════════════════════════


def calculate_waterfall_components(
    df: pd.DataFrame,
    colmap: Dict[str, str],
    period_filter: Optional[str] = None,
) -> Dict[str, float]:
    """
    Calculate the waterfall components using SolarDataAnalyzer.
    """
    data = df.copy()

    # Apply period filter if provided
    if period_filter:
        date_col = colmap.get("date")
        if date_col and date_col in data.columns:
            data = data[data[date_col] == period_filter]

    # Use SolarDataAnalyzer to compute losses
    if SolarDataAnalyzer:
        analyzer = SolarDataAnalyzer(data, colmap)
        data = analyzer.compute_losses()

    # Get column mappings
    budget_col = colmap.get("budget_gen")
    actual_col = colmap.get("actual_gen")
    wab_col = colmap.get("wab")

    # Calculate totals
    budget = data[budget_col].sum() if budget_col and budget_col in data.columns else 0
    actual = data[actual_col].sum() if actual_col and actual_col in data.columns else 0
    wab = data[wab_col].sum() if wab_col and wab_col in data.columns else 0

    # Get calculated losses
    weather_var = data["Var_Weather_kWh"].sum() if "Var_Weather_kWh" in data.columns else 0
    pr_loss = data["Loss_PR_kWh"].sum() if "Loss_PR_kWh" in data.columns else 0
    avail_loss = data["Loss_Avail_kWh"].sum() if "Loss_Avail_kWh" in data.columns else 0
    total_tech_loss = data["Loss_Total_Tech_kWh"].sum() if "Loss_Total_Tech_kWh" in data.columns else 0

    return {
        "budget": budget,
        "weather_var": weather_var,
        "wab": wab,
        "pr_loss": pr_loss,
        "avail_loss": avail_loss,
        "total_tech_loss": total_tech_loss,
        "actual": actual,
    }


def calculate_kpis(
    df: pd.DataFrame,
    colmap: Dict[str, str],
    period_filter: Optional[str] = None,
) -> Dict[str, float]:
    """
    Calculate PR and Availability KPIs using weighted_average from analysis.py.
    """

    data = df.copy()

    if period_filter:
        date_col = colmap.get("date")
        if date_col and date_col in data.columns:
            data = data[data[date_col] == period_filter]

    # Ensure calculated columns exist
    if SolarDataAnalyzer:
        analyzer = SolarDataAnalyzer(data, colmap)
        data = analyzer.compute_losses()

    pr_col = colmap.get("pr_actual")
    pr_budget_col = colmap.get("pr_budget")
    avail_col = colmap.get("availability")
    actual_col = colmap.get("actual_gen")

    # Use weighted_average from analysis.py if available
    if weighted_average is not None and actual_col and actual_col in data.columns:
        # Weighted average PR (weighted by actual generation)
        if pr_col and pr_col in data.columns:
            pr = weighted_average(data, pr_col, actual_col)
            if pd.isna(pr):
                pr = data[pr_col].mean()
        else:
            pr = 0

        # Weighted average PR budget
        if pr_budget_col and pr_budget_col in data.columns:
            pr_budget = weighted_average(data, pr_budget_col, actual_col)
            if pd.isna(pr_budget):
                pr_budget = data[pr_budget_col].mean()
        else:
            pr_budget = Config.DEFAULT_PR_BUDGET

        # Weighted average availability
        if avail_col and avail_col in data.columns:
            avail = weighted_average(data, avail_col, actual_col)
            if pd.isna(avail):
                avail = data[avail_col].mean()
        else:
            avail = Config.DEFAULT_AVAILABILITY
    else:
        # Fallback to simple mean
        pr = data[pr_col].mean() if pr_col and pr_col in data.columns else 0
        pr_budget = (
            data[pr_budget_col].mean() if pr_budget_col and pr_budget_col in data.columns else Config.DEFAULT_PR_BUDGET
        )
        avail = data[avail_col].mean() if avail_col and avail_col in data.columns else Config.DEFAULT_AVAILABILITY

    # Normalize to percentage scale (0-100)
    if pr and pr <= 1:
        pr = pr * 100
    if pr_budget and pr_budget <= 1:
        pr_budget = pr_budget * 100
    if avail and avail <= 1:
        avail = avail * 100

    return {
        "pr": pr if not pd.isna(pr) else 0,
        "pr_forecast": pr_budget if not pd.isna(pr_budget) else Config.DEFAULT_PR_BUDGET,
        "availability": avail if not pd.isna(avail) else Config.DEFAULT_AVAILABILITY,
        "availability_forecast": Config.TARGET_AVAILABILITY,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# CSV EXPORT GENERATION
# ═══════════════════════════════════════════════════════════════════════════════

REVENUE_RATE_PER_KWH = 0.1  # £0.1 per kWh


def generate_excom_csv_export(summary_data, monthly_components, ytd_components, monthly_kpis, ytd_kpis, month_name):
    """
    Generate CSV export matching the ExCom table format.
    
    Returns a CSV string with:
    - Portfolio summary table
    - KPI table (PR, Availability)
    - Month waterfall components
    - YTD waterfall components
    
    Revenue is calculated at £0.1/kWh. The # column is left blank.
    """
    import io
    
    output = io.StringIO()
    
    # ── Portfolio Summary Table ──
    output.write(f"ExCom Report - {month_name}\n\n")
    output.write("Portfolio Summary\n")
    
    # Header row
    output.write("Portfolio[1],#,AUM MWp,")
    output.write("Month Budget,Month W-A-B,Month Actual,Month Variance,Month Revenue Impact (£k),")
    output.write("YTD Budget,YTD W-A-B,YTD Actual,YTD Variance,YTD Revenue Impact (£k)\n")
    
    # Data rows from summary_data
    for row in summary_data:
        portfolio_name = row.get("Type", "")
        mwp = row.get("MWp", 0)
        
        # Month values
        m_budget = row.get("Budget_Monthly", 0)
        m_wab = row.get("WAB_Monthly", 0)
        m_actual = row.get("Actual_Monthly", 0)
        m_variance = m_actual / m_wab if m_wab else 0
        m_revenue = (m_actual - m_wab) * REVENUE_RATE_PER_KWH / 1000  # Convert to £k
        
        # YTD values
        y_budget = row.get("Budget_YTD", 0)
        y_wab = row.get("WAB_YTD", 0)
        y_actual = row.get("Actual_YTD", 0)
        y_variance = y_actual / y_wab if y_wab else 0
        y_revenue = (y_actual - y_wab) * REVENUE_RATE_PER_KWH / 1000  # Convert to £k
        
        output.write(f"{portfolio_name},,{mwp:.1f},")
        output.write(f"{m_budget:.0f},{m_wab:.0f},{m_actual:.0f},{m_variance:.1%},{m_revenue:.1f},")
        output.write(f"{y_budget:.0f},{y_wab:.0f},{y_actual:.0f},{y_variance:.1%},{y_revenue:.1f}\n")
    
    output.write("\n")
    
    # ── KPI Table (layout matches ExCom format) ──
    output.write("KPIs\n")
    output.write(",Forecast,Actual\n")
    
    # Values are already in percentage scale (e.g., 85 means 85%)
    pr_forecast = monthly_kpis.get("pr_forecast", 0)
    pr_month = monthly_kpis.get("pr", 0)
    pr_ytd = ytd_kpis.get("pr", 0)
    avail_forecast = monthly_kpis.get("availability_forecast", 0)
    avail_month = monthly_kpis.get("availability", 0)
    avail_ytd = ytd_kpis.get("availability", 0)
    
    output.write(f"PR,{pr_forecast:.0f}%,{pr_month:.0f}%\n")
    output.write(f"Availability,{avail_forecast:.0f}%,{avail_month:.0f}%\n")
    output.write(f"PR - YTD,{pr_forecast:.0f}%,{pr_ytd:.1f}%\n")
    output.write(f"Availability - YTD,{avail_forecast:.0f}%,{avail_ytd:.1f}%\n")
    
    output.write("\n")
    
    # ── Month Waterfall ──
    output.write("Month Waterfall\n")
    output.write("Component,Value (MWh)\n")
    output.write(f"Budget,{monthly_components.get('budget', 0):.0f}\n")
    output.write(f"Irradiance,{monthly_components.get('weather_var', 0):.0f}\n")
    output.write(f"Availability,{monthly_components.get('avail_loss', 0):.0f}\n")
    output.write(f"Efficiency,{monthly_components.get('pr_loss', 0):.0f}\n")
    output.write(f"Actual,{monthly_components.get('actual', 0):.0f}\n")
    
    output.write("\n")
    
    # ── YTD Waterfall ──
    output.write("YTD Waterfall\n")
    output.write("Component,Value (MWh)\n")
    output.write(f"Budget,{ytd_components.get('budget', 0):.0f}\n")
    output.write(f"Irradiance,{ytd_components.get('weather_var', 0):.0f}\n")
    output.write(f"Availability,{ytd_components.get('avail_loss', 0):.0f}\n")
    output.write(f"Efficiency,{ytd_components.get('pr_loss', 0):.0f}\n")
    output.write(f"Actual,{ytd_components.get('actual', 0):.0f}\n")
    
    return output.getvalue()


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN REPORT TAB
# ═══════════════════════════════════════════════════════════════════════════════


def render_excom_report_tab(tab, extractor):
    """
    Render the ExCom-style operational report tab.
    """

    with tab:
        st.header("📊 Operational Performance Report")

        # Get data
        tables = extractor.list_tables()
        if not tables:
            st.warning("Upload data first.")
            return

        colmap = st.session_state.get("colmap", {})
        if not colmap or not st.session_state.get("colmap_confirmed"):
            st.error("Column mapping not confirmed. Go to Upload tab first.")
            return

        # Data source selection
        col1, col2 = st.columns([2, 1])
        with col1:
            source_tbl = st.selectbox("📁 Data Source", list(tables), key="excom_table")

        # Load data
        session_key = f"res_{source_tbl}"
        if session_key in st.session_state:
            df = st.session_state[session_key].copy()
        else:
            ok, df = extractor.query_data(f"SELECT * FROM {source_tbl}")
            if not ok or isinstance(df, str) or df.empty:
                st.error("Could not load data.")
                return

        # Get date column and available periods
        date_col = colmap.get("date")
        if date_col and date_col in df.columns:
            periods = sorted(df[date_col].dropna().unique().tolist())

            with col2:
                selected_month = st.selectbox(
                    "📅 Reporting Month", periods, index=len(periods) - 1 if periods else 0, key="excom_month"
                )
        else:
            st.warning("No date column found.")
            selected_month = None
            periods = []

        st.divider()

        # ────────────────────────────────────────────────────────────────
        # CALCULATE MONTHLY DATA
        # ────────────────────────────────────────────────────────────────

        monthly_components = calculate_waterfall_components(df, colmap, selected_month)
        monthly_kpis = calculate_kpis(df, colmap, selected_month)

        # ────────────────────────────────────────────────────────────────
        # CALCULATE YTD DATA
        # ────────────────────────────────────────────────────────────────

        fiscal_start = st.session_state.get("fiscal_year_start", 4)
        ytd_periods = []  # Initialize to empty list

        if date_col and selected_month and periods:
            try:
                selected_date = pd.to_datetime(selected_month, format="%b-%y", errors="coerce")
                if pd.isna(selected_date):
                    selected_date = pd.to_datetime(selected_month, errors="coerce")

                if selected_date.month >= fiscal_start:
                    fy_start = pd.Timestamp(year=selected_date.year, month=fiscal_start, day=1)
                else:
                    fy_start = pd.Timestamp(year=selected_date.year - 1, month=fiscal_start, day=1)

                ytd_periods = []
                for p in periods:
                    p_date = pd.to_datetime(p, format="%b-%y", errors="coerce")
                    if pd.isna(p_date):
                        p_date = pd.to_datetime(p, errors="coerce")
                    if not pd.isna(p_date) and fy_start <= p_date <= selected_date:
                        ytd_periods.append(p)

                df_ytd = df[df[date_col].isin(ytd_periods)]
                ytd_components = calculate_waterfall_components(df_ytd, colmap)
                ytd_kpis = calculate_kpis(df_ytd, colmap)

            except Exception as e:
                st.warning(f"Could not calculate YTD: {e}")
                ytd_components = monthly_components
                ytd_kpis = monthly_kpis
        else:
            ytd_components = calculate_waterfall_components(df, colmap)
            ytd_kpis = calculate_kpis(df, colmap)

        # ────────────────────────────────────────────────────────────────
        # DISPLAY WATERFALLS (EXCOM STYLE)
        # ────────────────────────────────────────────────────────────────

        # Get the report button function dynamically (may be injected at runtime)
        report_button_fn = globals().get('add_to_report_button')

        col1, col2 = st.columns(2)

        with col1:
            fig_monthly = create_excom_waterfall(
                budget=monthly_components["budget"],
                weather_var=monthly_components["weather_var"],
                wab=monthly_components["wab"],
                pr_loss=monthly_components["pr_loss"],
                avail_loss=monthly_components["avail_loss"],
                actual=monthly_components["actual"],
                title=f"Performance {selected_month or 'Monthly'}",
                height=380,
            )
            st.plotly_chart(fig_monthly, use_container_width=True)
            if callable(report_button_fn):
                report_button_fn(
                    content=fig_monthly,
                    title=f"Performance Waterfall - {selected_month or 'Monthly'}",
                    item_type='chart',
                    description=f"Monthly performance waterfall chart",
                    source_page="ExCom Report",
                    button_key=f"add_waterfall_monthly_{selected_month or 'Monthly'}".replace(' ', '_').replace('-', '_')
                )

        with col2:
            fig_ytd = create_excom_waterfall(
                budget=ytd_components["budget"],
                weather_var=ytd_components["weather_var"],
                wab=ytd_components["wab"],
                pr_loss=ytd_components["pr_loss"],
                avail_loss=ytd_components["avail_loss"],
                actual=ytd_components["actual"],
                title="Performance YTD",
                height=380,
            )
            st.plotly_chart(fig_ytd, use_container_width=True)
            if callable(report_button_fn):
                report_button_fn(
                    content=fig_ytd,
                    title="Performance Waterfall - YTD",
                    item_type='chart',
                    description="Year-to-date performance waterfall chart",
                    source_page="ExCom Report",
                    button_key="add_waterfall_ytd"
                )

        st.divider()

        # ────────────────────────────────────────────────────────────────
        # DISPLAY KPI CARDS
        # ────────────────────────────────────────────────────────────────

        display_kpi_cards(
            pr_actual=monthly_kpis["pr"],
            pr_forecast=monthly_kpis["pr_forecast"],
            avail_actual=monthly_kpis["availability"],
            avail_forecast=monthly_kpis["availability_forecast"],
            pr_ytd=ytd_kpis["pr"],
            pr_ytd_forecast=ytd_kpis["pr_forecast"],
            avail_ytd=ytd_kpis["availability"],
            avail_ytd_forecast=ytd_kpis["availability_forecast"],
        )

        st.divider()

        # ────────────────────────────────────────────────────────────────
        # TECHNICAL LOSSES BY SITE - TOP 5 AND BOTTOM 5
        # ────────────────────────────────────────────────────────────────

        # Calculate technical losses for monthly period
        monthly_top_5, monthly_bottom_5 = create_technical_losses_site_tables(
            df, colmap, selected_month
        )

        # Display the tables
        display_technical_losses_tables(
            monthly_top_5, monthly_bottom_5, f"{selected_month or 'Monthly'}"
        )

        st.divider()

        # ────────────────────────────────────────────────────────────────
        # PORTFOLIO SUMMARY TABLE
        # ────────────────────────────────────────────────────────────────

        st.subheader("Portfolio Summary")

        # Check for type column
        type_col = None
        for c in df.columns:
            if any(x in c.lower() for x in ["type", "technology", "category", "asset"]):
                type_col = c
                break

        if type_col:
            site_col = colmap.get("site")
            capacity_col = colmap.get("capacity")

            summary_data = []

            for asset_type in df[type_col].dropna().unique():
                df_type = df[df[type_col] == asset_type]
                df_type_month = df_type[df_type[date_col] == selected_month] if date_col and selected_month else df_type
                # Use ytd_periods if available and not empty
                df_type_ytd = df_type[df_type[date_col].isin(ytd_periods)] if date_col and ytd_periods else df_type

                # Calculate MWp using unique capacities per site (avoid double-counting multiple months)
                mwp = 0
                if capacity_col and capacity_col in df_type.columns and site_col and site_col in df_type.columns:
                    # Get unique site-capacity pairs, sorted by date descending to get latest values
                    df_type_sorted = (
                        df_type.sort_values(date_col, ascending=False)
                        if date_col and date_col in df_type.columns
                        else df_type
                    )
                    unique_capacities = df_type_sorted.drop_duplicates(subset=[site_col], keep="first")[
                        capacity_col
                    ].sum()
                    mwp = unique_capacities / 1000

                # Use waterfall components for consistency with charts
                monthly_type_components = calculate_waterfall_components(df_type_month, colmap)
                ytd_type_components = calculate_waterfall_components(df_type_ytd, colmap)

                row = {
                    "Type": asset_type,
                    "Sites": df_type[site_col].nunique() if site_col and site_col in df_type.columns else 0,
                    "MWp": mwp,
                    "Budget_Monthly": monthly_type_components["budget"],
                    "WAB_Monthly": monthly_type_components["wab"],
                    "Actual_Monthly": monthly_type_components["actual"],
                    "Budget_YTD": ytd_type_components["budget"],
                    "WAB_YTD": ytd_type_components["wab"],
                    "Actual_YTD": ytd_type_components["actual"],
                }
                summary_data.append(row)

            if summary_data:
                summary_df = pd.DataFrame(summary_data)

                # Add totals row
                totals = {
                    "Type": "Total",
                    "Sites": sum(row["Sites"] for row in summary_data),
                    "MWp": sum(row["MWp"] for row in summary_data),
                    "Budget_Monthly": sum(row["Budget_Monthly"] for row in summary_data),
                    "WAB_Monthly": sum(row["WAB_Monthly"] for row in summary_data),
                    "Actual_Monthly": sum(row["Actual_Monthly"] for row in summary_data),
                    "Budget_YTD": sum(row["Budget_YTD"] for row in summary_data),
                    "WAB_YTD": sum(row["WAB_YTD"] for row in summary_data),
                    "Actual_YTD": sum(row["Actual_YTD"] for row in summary_data),
                }
                summary_data.append(totals)
                summary_df = pd.DataFrame(summary_data)

                # Add variance columns
                summary_df["Variance_Monthly"] = summary_df["Actual_Monthly"] / summary_df["WAB_Monthly"]
                summary_df["Variance_YTD"] = summary_df["Actual_YTD"] / summary_df["WAB_YTD"]

                display_portfolio_table(summary_df, selected_month or "")
        else:
            st.info("Add a 'Type' column to your data to see the portfolio breakdown by asset type.")

            m1, m2, m3, m4 = st.columns(4)
            with m1:
                st.metric("Budget (Monthly)", f"{monthly_components['budget']:,.0f} MWh")
            with m2:
                st.metric("W-A-B (Monthly)", f"{monthly_components['wab']:,.0f} MWh")
            with m3:
                st.metric("Actual (Monthly)", f"{monthly_components['actual']:,.0f} MWh")
            with m4:
                variance = monthly_components["actual"] / monthly_components["wab"] if monthly_components["wab"] else 0
                st.metric("Variance", f"{variance:.0%}")

        # ────────────────────────────────────────────────────────────────
        # EXPORT
        # ────────────────────────────────────────────────────────────────

        st.divider()

        col1, col2 = st.columns(2)

        with col1:
            # Generate CSV export matching ExCom table format
            csv = generate_excom_csv_export(
                summary_data=summary_data if 'summary_data' in dir() else [],
                monthly_components=monthly_components,
                ytd_components=ytd_components,
                monthly_kpis=monthly_kpis,
                ytd_kpis=ytd_kpis,
                month_name=selected_month or ""
            )
            st.download_button(
                "📥 Download Report Data (CSV)",
                csv,
                f"excom_report_{selected_month}.csv",
                "text/csv",
                use_container_width=True,
            )
