"""
Reusable KPI card component.

Provides styled KPI cards with status-colored borders,
delta indicators, and responsive layout.

Usage:
    from components.kpi_cards import render_kpi_row

    render_kpi_row([
        {"label": "Total Capacity", "value": "125 MWp", "delta": "+5%", "status": "good"},
        {"label": "Fleet PR", "value": "82.3%", "delta": "-1.1%", "status": "warning"},
    ])

DESIGN NOTES FOR EXTRACTION:
- When moving to React, this becomes a <KPICard> component
- Status colors from design_tokens.py map to CSS classes
"""
import streamlit as st

from styles.design_tokens import STATUS_COLORS, AMPYR_TEAL


def render_kpi_row(kpis: list[dict], columns: int | None = None):
    """Render a row of KPI cards.

    Args:
        kpis: List of dicts with keys: label, value, delta (optional), status (optional), icon (optional)
        columns: Number of columns (default: len(kpis))
    """
    n = columns or len(kpis)
    cols = st.columns(n)

    for i, kpi in enumerate(kpis):
        if i >= n:
            break
        with cols[i]:
            _render_card(kpi)


def render_kpi_card_single(
    label: str,
    value: str,
    delta: str = "",
    status: str = "good",
    icon: str = "",
):
    """Render a single KPI card (convenience wrapper).

    Args:
        label: The metric label (e.g., "Total Capacity")
        value: The metric value (e.g., "125 MWp")
        delta: Optional delta string (e.g., "+5%")
        status: Status for border color (excellent, good, warning, critical, offline)
        icon: Optional emoji icon
    """
    kpi = {"label": label, "value": value, "delta": delta, "status": status}
    if icon:
        kpi["icon"] = icon
    _render_card(kpi)


def _render_card(kpi: dict):
    """Render a single KPI card with colored left border."""
    status = kpi.get("status", "good")
    color = STATUS_COLORS.get(status, STATUS_COLORS["good"])
    icon = kpi.get("icon", "")
    icon_html = f'<span style="font-size: 1.25rem; margin-right: 0.5rem;">{icon}</span>' if icon else ""

    st.markdown(
        f"""
        <div style="
            background: white;
            border-radius: 0.5rem;
            padding: 1.25rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            border-left: 4px solid {color};
            transition: box-shadow 0.2s ease;
            margin-bottom: 0.5rem;
        ">
            <div style="font-size: 0.8rem; color: #7F8C8D; text-transform: uppercase; font-weight: 500; letter-spacing: 0.5px;">
                {icon_html}{kpi["label"]}
            </div>
            <div style="font-size: 1.75rem; font-weight: 700; color: {AMPYR_TEAL}; margin: 0.25rem 0;">
                {kpi["value"]}
            </div>
            <div style="font-size: 0.85rem; color: {_delta_color(kpi.get('delta', ''))};">
                {kpi.get("delta", "")}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_status_badge(status: str, label: str | None = None) -> None:
    """Render a small colored status badge.

    Args:
        status: One of excellent, good, warning, critical, offline
        label: Optional override label (defaults to status title-cased)
    """
    label = label or status.title()
    color = STATUS_COLORS.get(status, STATUS_COLORS.get("unknown", "#BDC3C7"))

    # Map status to background/text colors for badges
    badge_styles = {
        "excellent": ("background: #D5F5E3; color: #196F3D;"),
        "good": ("background: #D1F2EB; color: #0E6655;"),
        "warning": ("background: #FDEBD0; color: #935116;"),
        "critical": ("background: #FADBD8; color: #922B21;"),
        "offline": ("background: #E5E8E8; color: #566573;"),
    }
    style = badge_styles.get(status, "background: #E5E8E8; color: #566573;")

    status_icons = {
        "excellent": "🟢",
        "good": "🟢",
        "warning": "🟡",
        "critical": "🔴",
        "offline": "⚫",
    }
    icon = status_icons.get(status, "⚪")

    st.markdown(
        f"""
        <span style="
            display: inline-flex;
            align-items: center;
            gap: 0.375rem;
            padding: 0.25rem 0.75rem;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            {style}
        ">
            {icon} {label}
        </span>
        """,
        unsafe_allow_html=True,
    )


def _delta_color(delta: str) -> str:
    """Determine color for a delta value string."""
    if not delta:
        return "#7F8C8D"
    if delta.startswith("+") or "▲" in delta:
        return "#2ECC71"
    if delta.startswith("-") or "▼" in delta:
        return "#E74C3C"
    return "#7F8C8D"
