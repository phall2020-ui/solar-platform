"""
Portfolio Dashboard — landing page after login.

Shows fleet-level KPIs, plant status grid, generation trend, and alert summary.
All data from services layer — no direct DB queries.

DESIGN NOTES FOR EXTRACTION:
- KPI calculations live in services/portfolio_service.py
- This module only handles Streamlit rendering
- When moving to React: replace st.columns → CSS Grid, st.metric → <KPICard>
"""
import logging

import plotly.graph_objects as go
import streamlit as st

from app.components.kpi_cards import render_kpi_row
from app.components.report_button import add_to_report_button
from solar_platform.services.portfolio import PortfolioService
from app.styles.design_tokens import AMPYR_TEAL, PLOTLY_TEMPLATE, STATUS_COLORS
from app.config_compat import config

logger = logging.getLogger(__name__)

# Backwards-compat: conditionally import system health widget
try:
    from app.pages.system_health import render_system_health_widget

    _HAS_HEALTH_WIDGET = True
except ImportError:
    _HAS_HEALTH_WIDGET = False


def render():
    """Render the portfolio dashboard page (entry point from page registry)."""
    logger.info("Rendering portfolio dashboard")

    st.title("📊 Portfolio Dashboard")

    # System health widget (collapsible)
    if getattr(config, "enable_observability", False) and _HAS_HEALTH_WIDGET:
        render_system_health_widget()

    # Time range selector
    col_title, col_range = st.columns([3, 1])
    with col_range:
        time_range = st.selectbox(
            "Period",
            ["Last 24 Hours", "Last 7 Days", "Last 30 Days", "Month to Date", "Year to Date"],
            label_visibility="collapsed",
        )

    # Load portfolio summary from service
    portfolio = PortfolioService()

    try:
        summary = portfolio.get_summary(time_range)
    except Exception as e:
        logger.error("Failed to load portfolio summary: %s", e)
        st.error(f"Could not load portfolio data: {e}")
        _render_fallback()
        return

    # ── KPI Row ─────────────────────────────────────────────
    render_kpi_row(
        [
            {
                "label": "Total Capacity",
                "value": f"{summary.total_capacity_mwp:.1f} MWp",
                "delta": f"{summary.plant_count} plants",
                "status": "good",
                "icon": "⚡",
            },
            {
                "label": "Total Generation",
                "value": f"{summary.total_generation_mwh:.1f} MWh",
                "delta": f"{summary.generation_delta_pct:+.1f}%",
                "status": "good" if summary.generation_delta_pct >= 0 else "warning",
                "icon": "🔋",
            },
            {
                "label": "Fleet Performance Ratio",
                "value": f"{summary.fleet_pr_pct:.1f}%",
                "delta": f"{summary.pr_delta_pct:+.1f}%",
                "status": _pr_status(summary.fleet_pr_pct),
                "icon": "📊",
            },
            {
                "label": "Active Alerts",
                "value": str(summary.active_alerts),
                "delta": f"{summary.critical_alerts} critical",
                "status": "critical" if summary.critical_alerts > 0 else "good",
                "icon": "🔔",
            },
        ]
    )

    # Add KPIs to report builder
    add_to_report_button(
        content={
            "Total Capacity": f"{summary.total_capacity_mwp:.1f} MWp",
            "Total Generation": f"{summary.total_generation_mwh:.1f} MWh",
            "Fleet PR": f"{summary.fleet_pr_pct:.1f}%",
            "Active Alerts": str(summary.active_alerts),
        },
        title="Portfolio KPI Summary",
        item_type="kpi",
        description="Fleet-level KPIs for the selected period",
        source_page="Dashboard",
        button_key="add_dashboard_kpis",
    )

    st.divider()

    # ── Plant Status Grid ───────────────────────────────────
    st.subheader("Plant Status")

    col_search, col_filter = st.columns([3, 1])
    with col_search:
        search = st.text_input(
            "🔍 Filter plants",
            label_visibility="collapsed",
            placeholder="Filter plants...",
            key="dashboard_plant_search",
        )
    with col_filter:
        status_filter = st.selectbox(
            "Status",
            ["All", "Excellent", "Good", "Warning", "Critical", "Offline"],
            label_visibility="collapsed",
            key="dashboard_status_filter",
        )

    plants = portfolio.get_plant_statuses(time_range)

    # Apply filters
    if search:
        plants = [p for p in plants if search.lower() in p["name"].lower()]
    if status_filter != "All":
        plants = [p for p in plants if p["status"] == status_filter.lower()]

    if plants:
        # Header row
        header_cols = st.columns([3, 1, 1, 1, 1])
        with header_cols[0]:
            st.markdown("**Plant**")
        with header_cols[1]:
            st.markdown("**Status**")
        with header_cols[2]:
            st.markdown("**PR**")
        with header_cols[3]:
            st.markdown("**Generation**")
        with header_cols[4]:
            st.markdown("**Alerts**")

        st.markdown("---")

        for plant in plants:
            _render_plant_row(plant)
    else:
        st.info("No plants match the current filters.")

    st.divider()

    # ── Charts Row ──────────────────────────────────────────
    col_chart, col_alerts = st.columns([2, 1])

    with col_chart:
        st.subheader("Portfolio Generation Trend")
        trend = portfolio.get_generation_trend(days=7)
        if trend:
            fig = _build_trend_chart(trend)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No generation trend data available.")

    with col_alerts:
        st.subheader("Alert Summary")
        alerts = portfolio.get_alert_summary()
        if alerts:
            for alert in alerts:
                icon = (
                    "🔴"
                    if alert["severity"] == "critical"
                    else "🟡" if alert["severity"] == "warning" else "ℹ️"
                )
                st.markdown(f"{icon} **{alert['count']}** {alert['type']}")
        else:
            st.caption("No active alerts. Alert system will be enabled in Phase 4.")

    # Quick links footer
    st.divider()
    _render_quick_links()


# ── Helper Functions ────────────────────────────────────────────────


def _pr_status(pr: float) -> str:
    """Map PR value to status category."""
    if pr >= 85:
        return "excellent"
    if pr >= 70:
        return "good"
    if pr >= 50:
        return "warning"
    return "critical"


def _render_plant_row(plant: dict):
    """Render a single plant status row with click-to-detail."""
    status = plant["status"]
    status_icon = {
        "excellent": "🟢",
        "good": "🟢",
        "warning": "🟡",
        "critical": "🔴",
        "offline": "⚫",
    }.get(status, "⚪")

    cols = st.columns([3, 1, 1, 1, 1])
    with cols[0]:
        # Clicking sets selected_plant_uid and navigates to Plant Detail
        if st.button(f"☀️ {plant['name']}", key=f"plant_{plant['uid']}"):
            st.session_state["selected_plant_uid"] = plant["uid"]
            st.session_state["selected_plant_name"] = plant["name"]
            st.session_state["current_page"] = "Plant Detail"
            st.rerun()
    with cols[1]:
        st.markdown(f"{status_icon} {status.title()}")
    with cols[2]:
        pr_val = plant.get("pr")
        st.markdown(f"{pr_val:.1f}%" if pr_val is not None else "—")
    with cols[3]:
        gen_val = plant.get("generation_mwh", 0)
        st.markdown(f"{gen_val:.1f} MWh")
    with cols[4]:
        alert_count = plant.get("alerts", 0)
        st.markdown(str(alert_count))


def _build_trend_chart(trend: list[dict]) -> go.Figure:
    """Build portfolio generation trend chart."""
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=[t["date"] for t in trend],
            y=[t["generation_mwh"] for t in trend],
            fill="tozeroy",
            fillcolor="rgba(27,77,92,0.15)",
            line=dict(color=AMPYR_TEAL, width=2),
            name="Generation",
        )
    )
    fig.update_layout(
        **PLOTLY_TEMPLATE["layout"],
        yaxis_title="MWh",
        showlegend=False,
        height=300,
    )
    return fig


def _render_quick_links():
    """Render quick action links at the bottom."""
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("### 🔧 Operations")
        st.markdown(
            """
        - **Plant Management**: Register and configure plants
        - **POA Import**: Import irradiance data
        - **Data Explorer**: Browse database contents
        """
        )

    with col2:
        st.markdown("### 📈 Analysis")
        st.markdown(
            """
        - **Fouling Analysis**: Detect panel soiling
        - **Shading Analysis**: Identify shading losses
        - **Clipping Analysis**: Estimate inverter losses
        """
        )

    with col3:
        st.markdown("### 💼 Reporting")
        st.markdown(
            """
        - **Monthly Performance**: ExCom reports
        - **Waterfall Analysis**: Loss breakdowns
        - **Report Builder**: Custom reports
        """
        )


def _render_fallback():
    """Render fallback content when portfolio service fails."""
    st.warning("Could not load portfolio data. Showing fallback view.")
    st.markdown(
        """
    ### Quick Actions
    - Go to **Plant Management** to register plants
    - Go to **Data Explorer** to browse the database
    - Check **System Health** for diagnostic information
    """
    )
