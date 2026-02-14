"""
Financial Dashboard — Phase 7.10

YTD revenue vs budget overview with monthly comparison charts,
plant-level breakdown, and variance analysis.

Entry point: render()
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.kpi_cards import render_kpi_row
from components.layouts import page_header
from styles.design_tokens import (
    AMPYR_TEAL,
    AMPYR_TEAL_LIGHT,
    CHART_COLORS,
    PLOTLY_TEMPLATE,
    STATUS_COLORS,
)

logger = logging.getLogger(__name__)

# ── Service imports (guarded) ───────────────────────────────────────

try:
    from services.financial.revenue import RevenueResult, RevenueService, TariffType

    REVENUE_AVAILABLE = True
except Exception:
    REVENUE_AVAILABLE = False

try:
    from services.financial.budget import BudgetComparison, BudgetService

    BUDGET_AVAILABLE = True
except Exception:
    BUDGET_AVAILABLE = False

try:
    from services.financial.tariff import TariffManager

    TARIFF_AVAILABLE = True
except Exception:
    TARIFF_AVAILABLE = False

try:
    from services.database.repository import PlantRepository

    PLANT_REPO_AVAILABLE = True
except Exception:
    PLANT_REPO_AVAILABLE = False

# ── Constants ────────────────────────────────────────────────────────

CURRENCY_SYMBOL = "£"
MONTHS = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

DEMO_PLANTS = [
    "Alderney Farm",
    "Beacon Hill",
    "Crowland South",
    "Dunston Fields",
    "Elmbridge Park",
    "Foxley Meadow",
    "Great Staughton",
    "Hinckley North",
]


# ── Demo data ────────────────────────────────────────────────────────


def _demo_monthly_revenue(year: int) -> pd.DataFrame:
    """Monthly actual vs budget revenue for the portfolio."""
    np.random.seed(year)
    current_month = datetime.now(UTC).month if year == datetime.now(UTC).year else 12

    budget_base = np.array([120, 150, 220, 310, 380, 420, 450, 410, 340, 260, 170, 130], dtype=float)
    budget = budget_base * np.random.uniform(0.95, 1.05, 12) * 1000  # £k -> £

    actual = budget.copy()
    for m in range(current_month):
        actual[m] = budget[m] * np.random.uniform(0.85, 1.12)
    # Future months have no actual
    for m in range(current_month, 12):
        actual[m] = np.nan

    return pd.DataFrame(
        {
            "month": MONTHS,
            "month_num": list(range(1, 13)),
            "actual": np.round(actual, 0),
            "budget": np.round(budget, 0),
        }
    )


def _demo_plant_breakdown(year: int) -> pd.DataFrame:
    """Per-plant revenue, generation, tariff, and variance."""
    np.random.seed(year + 99)
    rows = []
    for plant in DEMO_PLANTS:
        capacity_mwp = round(np.random.uniform(5, 50), 1)
        gen_mwh = round(capacity_mwp * np.random.uniform(800, 1100), 0)
        tariff = round(np.random.uniform(40, 85), 2)
        tariff_type = np.random.choice(["Fixed PPA", "ROC", "FiT", "CfD"])
        revenue = round(gen_mwh * tariff, 0)
        budget_rev = round(revenue * np.random.uniform(0.88, 1.12), 0)
        variance_pct = round((revenue - budget_rev) / budget_rev * 100, 1)
        rows.append(
            {
                "plant": plant,
                "tariff_type": tariff_type,
                "tariff_rate": tariff,
                "gen_mwh": gen_mwh,
                "revenue": revenue,
                "budget": budget_rev,
                "variance_pct": variance_pct,
            }
        )
    return pd.DataFrame(rows).sort_values("revenue", ascending=False)


def _demo_ytd_summary(monthly_df: pd.DataFrame) -> dict:
    """Calculate YTD KPI values from monthly data."""
    ytd_actual = monthly_df["actual"].sum()
    ytd_budget = monthly_df["budget"].sum()
    variance = ytd_actual - ytd_budget
    variance_pct = (variance / ytd_budget * 100) if ytd_budget else 0.0
    avg_tariff = round(np.random.uniform(52, 68), 2)
    return {
        "ytd_revenue": ytd_actual,
        "ytd_budget": ytd_budget,
        "variance": variance,
        "variance_pct": variance_pct,
        "avg_tariff": avg_tariff,
    }


# ── Helpers ──────────────────────────────────────────────────────────


def _variance_status(pct: float) -> str:
    """Color-code variance: green ≤ ±5%, amber ±5-15%, red > ±15%."""
    abs_pct = abs(pct)
    if abs_pct <= 5:
        return "good"
    if abs_pct <= 15:
        return "warning"
    return "critical"


def _variance_color(pct: float) -> str:
    return STATUS_COLORS[_variance_status(pct)]


def _format_currency(value: float, compact: bool = False) -> str:
    if compact and abs(value) >= 1_000_000:
        return f"{CURRENCY_SYMBOL}{value / 1_000_000:.2f}M"
    if compact and abs(value) >= 1_000:
        return f"{CURRENCY_SYMBOL}{value / 1_000:.1f}k"
    return f"{CURRENCY_SYMBOL}{value:,.0f}"


def _apply_template(fig: go.Figure) -> go.Figure:
    fig.update_layout(**PLOTLY_TEMPLATE["layout"])
    return fig


# ── Main render ──────────────────────────────────────────────────────


def render() -> None:
    """Render the Financial Dashboard page."""
    page_header(
        "Financial Dashboard",
        subtitle="Revenue tracking, budget comparison, and tariff analysis",
        icon="💰",
    )

    using_demo = not (REVENUE_AVAILABLE and BUDGET_AVAILABLE)
    if using_demo:
        st.info("📋 Showing demo data — financial services are loading in the background.", icon="ℹ️")

    # ── Filters ──────────────────────────────────────────────
    current_year = datetime.now(UTC).year
    col_year, col_currency, col_spacer = st.columns([1, 1, 3])
    with col_year:
        year = st.selectbox(
            "Year",
            list(range(current_year, current_year - 4, -1)),
            key="fin_year",
        )
    with col_currency:
        st.text_input("Currency", value="£ GBP", disabled=True, key="fin_currency")

    # ── Load data ────────────────────────────────────────────
    monthly_df = _load_monthly_revenue(year)
    plant_df = _load_plant_breakdown(year)
    ytd = _calc_ytd(monthly_df)

    # ── KPI Row ──────────────────────────────────────────────
    var_status = _variance_status(ytd["variance_pct"])

    render_kpi_row(
        [
            {
                "label": "YTD Revenue",
                "value": _format_currency(ytd["ytd_revenue"], compact=True),
                "delta": f"vs {_format_currency(ytd['ytd_budget'], compact=True)} budget",
                "status": "good",
                "icon": "💷",
            },
            {
                "label": "YTD Budget",
                "value": _format_currency(ytd["ytd_budget"], compact=True),
                "status": "good",
                "icon": "📋",
            },
            {
                "label": "Variance",
                "value": _format_currency(ytd["variance"], compact=True),
                "delta": f"{ytd['variance_pct']:+.1f}%",
                "status": var_status,
                "icon": "📊",
            },
            {
                "label": "Avg Tariff",
                "value": f"{CURRENCY_SYMBOL}{ytd['avg_tariff']:.2f}/MWh",
                "status": "good",
                "icon": "⚡",
            },
        ]
    )

    st.divider()

    # ── Monthly Revenue Chart ────────────────────────────────
    st.subheader("📅 Monthly Revenue: Actual vs Budget")
    _render_monthly_chart(monthly_df)

    # ── Plant Revenue Breakdown ──────────────────────────────
    st.subheader("🏭 Plant Revenue Breakdown")
    _render_plant_table(plant_df)

    # ── Variance waterfall (optional viz) ────────────────────
    st.subheader("📊 Variance Analysis by Plant")
    _render_variance_chart(plant_df)


# ── Data loaders ─────────────────────────────────────────────────────


def _load_monthly_revenue(year: int) -> pd.DataFrame:
    if REVENUE_AVAILABLE and BUDGET_AVAILABLE:
        try:
            rev_svc = RevenueService()
            bud_svc = BudgetService()
            monthly_rev = rev_svc.monthly_portfolio(year=year)
            monthly_bud = bud_svc.monthly_portfolio(year=year)
            return pd.DataFrame(
                {
                    "month": MONTHS,
                    "month_num": list(range(1, 13)),
                    "actual": monthly_rev,
                    "budget": monthly_bud,
                }
            )
        except Exception as e:
            logger.warning("Revenue/Budget service failed: %s", e)
    return _demo_monthly_revenue(year)


def _load_plant_breakdown(year: int) -> pd.DataFrame:
    if REVENUE_AVAILABLE:
        try:
            svc = RevenueService()
            return svc.plant_breakdown(year=year)
        except Exception as e:
            logger.warning("Plant breakdown failed: %s", e)
    return _demo_plant_breakdown(year)


def _calc_ytd(monthly_df: pd.DataFrame) -> dict:
    if REVENUE_AVAILABLE and BUDGET_AVAILABLE:
        try:
            svc = RevenueService()
            return svc.ytd_summary()
        except Exception:
            pass
    return _demo_ytd_summary(monthly_df)


# ── Chart renderers ──────────────────────────────────────────────────


def _render_monthly_chart(df: pd.DataFrame) -> None:
    """Side-by-side bar chart: actual vs budget by month."""
    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            x=df["month"],
            y=df["actual"],
            name="Actual",
            marker_color=AMPYR_TEAL,
            hovertemplate="%{x}: " + CURRENCY_SYMBOL + "%{y:,.0f}<extra>Actual</extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            x=df["month"],
            y=df["budget"],
            name="Budget",
            marker_color=AMPYR_TEAL_LIGHT,
            opacity=0.6,
            hovertemplate="%{x}: " + CURRENCY_SYMBOL + "%{y:,.0f}<extra>Budget</extra>",
        )
    )

    fig.update_layout(
        barmode="group",
        height=400,
        xaxis_title="Month",
        yaxis_title=f"Revenue ({CURRENCY_SYMBOL})",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    _apply_template(fig)
    st.plotly_chart(fig, use_container_width=True, key="fin_monthly")


def _render_plant_table(df: pd.DataFrame) -> None:
    """Plant revenue breakdown with color-coded variance."""
    if df.empty:
        st.warning("No plant revenue data available.")
        return

    display_df = df.copy()
    display_df["revenue_fmt"] = display_df["revenue"].apply(lambda v: _format_currency(v))
    display_df["budget_fmt"] = display_df["budget"].apply(lambda v: _format_currency(v))
    display_df["tariff_fmt"] = display_df["tariff_rate"].apply(lambda v: f"{CURRENCY_SYMBOL}{v:.2f}/MWh")
    display_df["variance_fmt"] = display_df["variance_pct"].apply(lambda v: f"{v:+.1f}%")

    # Build styled HTML table for colour-coded variance
    rows_html = ""
    for _, row in display_df.iterrows():
        var_color = _variance_color(row["variance_pct"])
        rows_html += f"""
        <tr>
            <td style="font-weight:600;">{row['plant']}</td>
            <td>{row['tariff_type']}</td>
            <td style="text-align:right;">{row['tariff_fmt']}</td>
            <td style="text-align:right;">{row['gen_mwh']:,.0f}</td>
            <td style="text-align:right;">{row['revenue_fmt']}</td>
            <td style="text-align:right;">{row['budget_fmt']}</td>
            <td style="text-align:right; color:{var_color}; font-weight:700;">
                {row['variance_fmt']}
            </td>
        </tr>
        """

    st.markdown(
        f"""
        <div style="overflow-x:auto;">
        <table style="width:100%; border-collapse:collapse; font-size:0.9rem;">
            <thead>
                <tr style="background:{AMPYR_TEAL}; color:white; text-align:left;">
                    <th style="padding:0.6rem;">Plant</th>
                    <th style="padding:0.6rem;">Tariff Type</th>
                    <th style="padding:0.6rem; text-align:right;">Rate</th>
                    <th style="padding:0.6rem; text-align:right;">Gen (MWh)</th>
                    <th style="padding:0.6rem; text-align:right;">Revenue</th>
                    <th style="padding:0.6rem; text-align:right;">Budget</th>
                    <th style="padding:0.6rem; text-align:right;">Variance</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_variance_chart(df: pd.DataFrame) -> None:
    """Horizontal bar chart of variance % per plant, color-coded."""
    if df.empty:
        return

    colors = [_variance_color(v) for v in df["variance_pct"]]

    fig = go.Figure(
        go.Bar(
            x=df["variance_pct"],
            y=df["plant"],
            orientation="h",
            marker_color=colors,
            hovertemplate="%{y}: %{x:+.1f}%<extra></extra>",
        )
    )

    # Add ±5% and ±15% threshold lines
    fig.add_vline(x=5, line_dash="dot", line_color=STATUS_COLORS["warning"], opacity=0.5)
    fig.add_vline(x=-5, line_dash="dot", line_color=STATUS_COLORS["warning"], opacity=0.5)
    fig.add_vline(x=15, line_dash="dot", line_color=STATUS_COLORS["critical"], opacity=0.5)
    fig.add_vline(x=-15, line_dash="dot", line_color=STATUS_COLORS["critical"], opacity=0.5)
    fig.add_vline(x=0, line_color="#333", line_width=1)

    fig.update_layout(
        height=max(300, len(df) * 40),
        xaxis_title="Variance (%)",
        yaxis_title="",
        showlegend=False,
    )
    _apply_template(fig)
    st.plotly_chart(fig, use_container_width=True, key="fin_variance")
