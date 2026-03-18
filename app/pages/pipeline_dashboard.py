"""
Pipeline Dashboard — Investment Opportunities from Dynamics 365 CRM

Displays the solar development pipeline fetched from Dynamics 365,
with status codes and technology type codes mapped to human-readable labels.

Status codes:  1=Live, 2=On Hold, 3=Dead
Technology types: Roof, Ground Mount, BESS, Carport, Wind

Entry point: render()
"""
from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd
import streamlit as st

from app.components.layouts import page_header
from app.styles.design_tokens import AMPYR_TEAL, STATUS_COLORS

logger = logging.getLogger(__name__)

# ── Status colour mapping ─────────────────────────────────────────────

_STATUS_COLORS: dict[str, str] = {
    "Live": STATUS_COLORS.get("good", "#2ECC71"),
    "On Hold": STATUS_COLORS.get("warning", "#F39C12"),
    "Dead": STATUS_COLORS.get("offline", "#95A5A6"),
}

_STATUS_BADGE: dict[str, str] = {
    "Live": "🟢",
    "On Hold": "🟡",
    "Dead": "⚫",
}

_TECH_BADGE: dict[str, str] = {
    "Roof": "🏠",
    "Ground Mount": "🌱",
    "BESS": "🔋",
    "Carport": "🚗",
    "Wind": "💨",
}

# ── Data loader ───────────────────────────────────────────────────────


@st.cache_data(ttl=300, show_spinner=False)
def _load_opportunities() -> tuple[list[dict], str | None]:
    """Fetch opportunities from Dynamics 365. Returns (rows, error_msg)."""
    try:
        from solar_platform.integrations.dynamics import DynamicsClient
        client = DynamicsClient()
        rows = client.get_opportunities()
        return rows, None
    except RuntimeError as exc:
        # Credentials not configured — show demo data with a warning
        logger.warning("Dynamics 365 not configured: %s", exc)
        return _demo_opportunities(), str(exc)
    except Exception as exc:
        logger.exception("Failed to load opportunities: %s", exc)
        return [], str(exc)


def _demo_opportunities() -> list[dict]:
    """Demo data matching the Dynamics 365 schema for local development."""
    return [
        {
            "name": "Sunny Valley - Retail Stores",
            "status": "Live",
            "status_code": 1,
            "probability": 75,
            "forecast_close": "2026-02-28T00:00:00Z",
            "technology_type": "Roof",
            "technology_type_code": 919160000,
            "gross_capacity_ac": 919160000,
            "gross_capacity_mw": 4.303,
            "modified_on": "2026-03-07T01:10:00Z",
        },
        {
            "name": "Eastfield Fabrications",
            "status": "On Hold",
            "status_code": 2,
            "probability": None,
            "forecast_close": None,
            "technology_type": "Ground Mount",
            "technology_type_code": 919160001,
            "gross_capacity_ac": 919160000,
            "gross_capacity_mw": 0.064,
            "modified_on": "2026-02-19T15:28:00Z",
        },
        {
            "name": "Briarwood Hydraulics",
            "status": "On Hold",
            "status_code": 2,
            "probability": None,
            "forecast_close": None,
            "technology_type": "Ground Mount",
            "technology_type_code": 919160001,
            "gross_capacity_ac": 919160000,
            "gross_capacity_mw": 0.089,
            "modified_on": "2026-02-19T15:28:00Z",
        },
        {
            "name": "Ashford Community College",
            "status": "On Hold",
            "status_code": 2,
            "probability": None,
            "forecast_close": None,
            "technology_type": "Roof",
            "technology_type_code": 919160000,
            "gross_capacity_ac": 919160000,
            "gross_capacity_mw": 0.224,
            "modified_on": "2026-02-19T15:28:00Z",
        },
        {
            "name": "Pennington Engineering",
            "status": "On Hold",
            "status_code": 2,
            "probability": None,
            "forecast_close": None,
            "technology_type": "Carport",
            "technology_type_code": 919160003,
            "gross_capacity_ac": 919160000,
            "gross_capacity_mw": 0.218,
            "modified_on": "2026-02-19T15:28:00Z",
        },
        {
            "name": "Meadowbrook Rental",
            "status": "On Hold",
            "status_code": 2,
            "probability": None,
            "forecast_close": None,
            "technology_type": "Roof",
            "technology_type_code": 919160000,
            "gross_capacity_ac": 919160000,
            "gross_capacity_mw": 0.094,
            "modified_on": "2026-02-19T15:28:00Z",
        },
        {
            "name": "Epping Forest Golf Club",
            "status": "On Hold",
            "status_code": 2,
            "probability": None,
            "forecast_close": None,
            "technology_type": "Ground Mount",
            "technology_type_code": 919160001,
            "gross_capacity_ac": 919160000,
            "gross_capacity_mw": 0.059,
            "modified_on": "2026-02-19T15:28:00Z",
        },
        {
            "name": "Archived Project",
            "status": "Dead",
            "status_code": 3,
            "probability": None,
            "forecast_close": None,
            "technology_type": "Wind",
            "technology_type_code": 919160004,
            "gross_capacity_ac": 0,
            "gross_capacity_mw": 0.0,
            "modified_on": "2025-12-10T17:02:00Z",
        },
    ]


# ── KPI helpers ───────────────────────────────────────────────────────


def _kpi_counts(rows: list[dict]) -> dict:
    total = len(rows)
    live = sum(1 for r in rows if r["status"] == "Live")
    on_hold = sum(1 for r in rows if r["status"] == "On Hold")
    dead = sum(1 for r in rows if r["status"] == "Dead")
    total_mw = sum(r.get("gross_capacity_mw", 0) or 0 for r in rows if r["status"] != "Dead")
    return {
        "total": total,
        "live": live,
        "on_hold": on_hold,
        "dead": dead,
        "pipeline_mw": round(total_mw, 2),
    }


# ── Render ────────────────────────────────────────────────────────────


def render() -> None:
    """Render the Pipeline Dashboard page."""
    page_header(
        "Pipeline Dashboard",
        subtitle="Investment opportunities from Dynamics 365 CRM",
        icon="📈",
    )

    rows, error = _load_opportunities()

    if error:
        st.warning(
            f"Using demo data — Dynamics 365 connection unavailable.\n\n`{error}`",
            icon="⚠️",
        )

    if not rows:
        st.error("No opportunity data available.")
        return

    kpi = _kpi_counts(rows)

    # ── KPI summary row ──────────────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Opportunities", kpi["total"])
    c2.metric("🟢 Live", kpi["live"])
    c3.metric("🟡 On Hold", kpi["on_hold"])
    c4.metric("⚫ Dead", kpi["dead"])
    c5.metric("Pipeline Capacity", f"{kpi['pipeline_mw']:.2f} MW")

    st.divider()

    # ── Filters ──────────────────────────────────────────────────────
    col_status, col_tech, col_search = st.columns([2, 2, 3])
    with col_status:
        status_options = ["All"] + sorted({r["status"] for r in rows})
        selected_status = st.selectbox("Status", status_options, key="pipe_status")
    with col_tech:
        tech_options = ["All"] + sorted({r["technology_type"] for r in rows})
        selected_tech = st.selectbox("Technology Type", tech_options, key="pipe_tech")
    with col_search:
        search = st.text_input("Search by name", placeholder="Type to filter…", key="pipe_search")

    # Apply filters
    filtered = rows
    if selected_status != "All":
        filtered = [r for r in filtered if r["status"] == selected_status]
    if selected_tech != "All":
        filtered = [r for r in filtered if r["technology_type"] == selected_tech]
    if search:
        q = search.lower()
        filtered = [r for r in filtered if q in r["name"].lower()]

    st.caption(f"{len(filtered)} opportunities shown")

    # ── Table ────────────────────────────────────────────────────────
    if not filtered:
        st.info("No opportunities match the current filters.")
        return

    rows_html = ""
    for row in filtered:
        status = row["status"]
        tech = row["technology_type"]
        badge = _STATUS_BADGE.get(status, "")
        tech_badge = _TECH_BADGE.get(tech, "")
        color = _STATUS_COLORS.get(status, "#ccc")

        prob = row.get("probability")
        prob_str = f"{prob}%" if prob is not None else "—"

        fc = row.get("forecast_close")
        if fc:
            try:
                fc_str = datetime.fromisoformat(fc.replace("Z", "+00:00")).strftime("%d %b %Y")
            except Exception:
                fc_str = str(fc)[:10]
        else:
            fc_str = "—"

        mw = row.get("gross_capacity_mw") or 0
        mw_str = f"{mw:.3f}" if mw else "—"

        mod = row.get("modified_on")
        if mod:
            try:
                mod_str = datetime.fromisoformat(mod.replace("Z", "+00:00")).strftime("%d %b %Y %H:%M")
            except Exception:
                mod_str = str(mod)[:16]
        else:
            mod_str = "—"

        rows_html += f"""
        <tr>
            <td style="font-weight:600; padding:0.5rem 0.8rem;">{row['name']}</td>
            <td style="padding:0.5rem 0.8rem;">
                <span style="color:{color}; font-weight:700;">{badge} {status}</span>
            </td>
            <td style="padding:0.5rem 0.8rem;">{prob_str}</td>
            <td style="padding:0.5rem 0.8rem;">{fc_str}</td>
            <td style="padding:0.5rem 0.8rem;">{tech_badge} {tech}</td>
            <td style="padding:0.5rem 0.8rem; text-align:right;">{mw_str}</td>
            <td style="padding:0.5rem 0.8rem; color:#666; font-size:0.85rem;">{mod_str}</td>
        </tr>
        """

    st.markdown(
        f"""
        <div style="overflow-x:auto;">
        <table style="width:100%; border-collapse:collapse; font-size:0.9rem;">
            <thead>
                <tr style="background:{AMPYR_TEAL}; color:white; text-align:left;">
                    <th style="padding:0.6rem 0.8rem;">Investment Opportunity</th>
                    <th style="padding:0.6rem 0.8rem;">Status</th>
                    <th style="padding:0.6rem 0.8rem;">Probability</th>
                    <th style="padding:0.6rem 0.8rem;">Forecast Close</th>
                    <th style="padding:0.6rem 0.8rem;">Technology Type</th>
                    <th style="padding:0.6rem 0.8rem; text-align:right;">Gross Capacity (MW)</th>
                    <th style="padding:0.6rem 0.8rem;">Modified On</th>
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

    # ── Breakdown charts ─────────────────────────────────────────────
    st.divider()
    _render_breakdown_charts(filtered)


def _render_breakdown_charts(rows: list[dict]) -> None:
    """Render status and technology type breakdown charts."""
    try:
        import plotly.graph_objects as go
        from app.styles.design_tokens import CHART_COLORS, PLOTLY_TEMPLATE
    except ImportError:
        return

    col_a, col_b = st.columns(2)

    # Status breakdown
    with col_a:
        st.subheader("By Status")
        status_counts: dict[str, int] = {}
        for r in rows:
            status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1

        colors = [_STATUS_COLORS.get(s, "#ccc") for s in status_counts]
        fig = go.Figure(go.Pie(
            labels=list(status_counts.keys()),
            values=list(status_counts.values()),
            marker_colors=colors,
            hole=0.45,
            textinfo="label+value",
        ))
        fig.update_layout(height=300, showlegend=False, **PLOTLY_TEMPLATE.get("layout", {}))
        st.plotly_chart(fig, use_container_width=True, key="pipe_status_chart")

    # Technology type breakdown
    with col_b:
        st.subheader("By Technology Type")
        tech_counts: dict[str, int] = {}
        for r in rows:
            tech_counts[r["technology_type"]] = tech_counts.get(r["technology_type"], 0) + 1

        fig2 = go.Figure(go.Pie(
            labels=list(tech_counts.keys()),
            values=list(tech_counts.values()),
            marker_colors=CHART_COLORS[:len(tech_counts)],
            hole=0.45,
            textinfo="label+value",
        ))
        fig2.update_layout(height=300, showlegend=False, **PLOTLY_TEMPLATE.get("layout", {}))
        st.plotly_chart(fig2, use_container_width=True, key="pipe_tech_chart")
