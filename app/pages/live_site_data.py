"""
Live Site Data — Real-time generation monitoring and historical day view.

Provides an interactive Streamlit page with:
  • Plant selector with device-level filtering
  • Date navigation (previous/today/next)
  • Live-mode toggle with 30s auto-refresh
  • KPI summary cards (Current Power, Energy Today, Irradiance, PR)
  • Plotly dual-axis chart (power + irradiance)
  • Multi-day comparison view with overlay and daily energy bar chart
  • Collapsible raw data table

All data sourced via :mod:`services.live_data_service` — no direct DB queries.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, date, datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from solar_platform.services.live_data import LiveDataService
from app.styles.design_tokens import (
    AMPYR_TEAL,
    AMPYR_TEAL_LIGHT,
    CHART_COLORS,
    PLOTLY_TEMPLATE,
    STATUS_COLORS,
)

logger = logging.getLogger(__name__)

# ── Helpers ─────────────────────────────────────────────────────────


@st.cache_data(ttl=300)
def _get_plant_list() -> list[dict]:
    """Cached plant list fetch."""
    svc = LiveDataService()
    return svc.get_plant_list()


def _freshness_indicator(freshness: str | None) -> str:
    """Return a coloured dot + label for data freshness."""
    if not freshness:
        return "🔴 No recent data"

    try:
        last_ts = datetime.fromisoformat(freshness)
        delta = datetime.now(tz=UTC) - last_ts
        minutes = delta.total_seconds() / 60
    except (ValueError, TypeError):
        # freshness might already be a human-readable string
        return f"⚪ Last reading: {freshness}"

    if minutes < 5:
        return f"🟢 Last reading: {freshness}"
    if minutes < 30:
        return f"🟡 Last reading: {freshness}"
    return f"🔴 Last reading: {freshness}"


# ═══════════════════════════════════════════════════════════════════════
# Public entry point (called from PAGE_REGISTRY)
# ═══════════════════════════════════════════════════════════════════════


def render() -> None:
    """Render the Live Site Data page."""
    logger.info("Rendering live site data page")

    # ── Header ──────────────────────────────────────────────────────
    st.title("📊 Live Site Data")
    st.markdown("Real-time generation monitoring and historical day view")

    # ── Service ─────────────────────────────────────────────────────
    svc = LiveDataService()

    # ── Plant list ──────────────────────────────────────────────────
    try:
        plants = _get_plant_list()
    except Exception as exc:
        logger.exception("Failed to load plant list")
        st.error(f"Could not load plants: {exc}")
        return

    if not plants:
        st.warning("No plants configured. Add a plant in Plant Management first.")
        return

    plant_aliases = [p["alias"] for p in plants]
    plant_uid_map = {p["alias"]: p["uid"] for p in plants}

    # ── Sidebar Controls ────────────────────────────────────────────
    with st.sidebar:
        st.subheader("📊 Live Site Data")

        # Plant selector
        selected_alias = st.selectbox(
            "Plant",
            plant_aliases,
            index=0,
            key="live_plant_selector",
        )
        selected_uid = plant_uid_map[selected_alias]

        # Persist in session state
        st.session_state["selected_plant"] = selected_uid

        # Date selector
        today = date.today()
        if "selected_date" not in st.session_state:
            st.session_state["selected_date"] = today

        selected_date = st.date_input(
            "Date",
            value=st.session_state["selected_date"],
            max_value=today,
            key="live_date_input",
        )
        st.session_state["selected_date"] = selected_date

        # Quick navigation
        col_prev, col_today, col_next = st.columns(3)
        with col_prev:
            if st.button("← Previous Day", use_container_width=True):
                st.session_state["selected_date"] = selected_date - timedelta(days=1)
                st.rerun()
        with col_today:
            if st.button("Today", use_container_width=True):
                st.session_state["selected_date"] = today
                st.rerun()
        with col_next:
            next_disabled = selected_date >= today
            if st.button("Next Day →", use_container_width=True, disabled=next_disabled):
                st.session_state["selected_date"] = selected_date + timedelta(days=1)
                st.rerun()

        st.divider()

        # Device filter
        try:
            devices = svc.get_device_list(selected_uid)
        except Exception as exc:
            logger.warning("Could not load device list: %s", exc)
            devices = []

        selected_devices = st.multiselect(
            "Devices",
            options=devices,
            default=devices if devices else [],
            placeholder="All devices",
            key="live_device_filter",
        )
        device_ids = selected_devices if selected_devices else None

        st.divider()

        # Live mode toggle
        live_mode = st.toggle("🔴 Live Mode", value=False, key="live_mode_toggle")

        # Refresh button
        if st.button("🔄 Refresh Data", use_container_width=True):
            try:
                svc.refresh_live_data(selected_uid)
                st.success("Data refreshed!")
            except Exception as exc:
                logger.warning("Refresh failed: %s", exc)
                st.error(f"Refresh failed: {exc}")

    # ── Fetch day data ──────────────────────────────────────────────
    try:
        df = svc.get_readings(selected_uid, selected_date, device_ids=device_ids)
    except Exception as exc:
        logger.exception("Failed to load readings")
        st.error(f"Could not load readings: {exc}")
        df = pd.DataFrame()

    try:
        kpis = svc.get_daily_kpis(selected_uid, selected_date)
    except Exception as exc:
        logger.exception("Failed to load KPIs")
        st.error(f"Could not load KPIs: {exc}")
        kpis = {}

    # ── Empty state ─────────────────────────────────────────────────
    if df is None or (isinstance(df, pd.DataFrame) and df.empty):
        st.info(
            f"No readings available for {selected_date.strftime('%d %b %Y')}. "
            "Try refreshing or selecting a different date."
        )
        # Still handle live-mode rerun even when empty
        if live_mode:
            time.sleep(30)
            st.rerun()
        return

    # ── KPI Cards Row ───────────────────────────────────────────────
    current_power = kpis.get("current_power_kw", 0)
    capacity = kpis.get("capacity_kw", 1)
    pct_of_capacity = (current_power / capacity * 100) if capacity else 0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric(
            "⚡ Current Power",
            f"{current_power:,.1f} kW",
            delta=f"{pct_of_capacity:.0f}% of capacity",
        )
    with c2:
        st.metric(
            "📈 Energy Today",
            f"{kpis.get('total_energy_kwh', 0):,.1f} kWh",
        )
    with c3:
        st.metric(
            "☀️ Avg Irradiance",
            f"{kpis.get('avg_irradiance_wm2', 0):,.0f} W/m²",
        )
    with c4:
        st.metric(
            "✅ Performance Ratio",
            f"{kpis.get('pr_pct', 0):,.1f}%",
        )

    # Data freshness indicator
    freshness_text = _freshness_indicator(kpis.get("data_freshness"))
    st.caption(freshness_text)

    # ── Tabs ────────────────────────────────────────────────────────
    tab_today, tab_multi = st.tabs(["Today", "Multi-Day Comparison"])

    # ── Tab 1: Today chart ──────────────────────────────────────────
    with tab_today:
        _render_daily_chart(df, selected_alias, selected_date)

    # ── Tab 2: Multi-day comparison ─────────────────────────────────
    with tab_multi:
        _render_multi_day(svc, selected_uid, selected_alias, selected_date, device_ids)

    # ── Raw Data (collapsible) ──────────────────────────────────────
    with st.expander("📋 Raw Data"):
        st.dataframe(df, use_container_width=True)

    # ── Live mode auto-refresh ──────────────────────────────────────
    if live_mode:
        time.sleep(30)
        st.rerun()


# ═══════════════════════════════════════════════════════════════════════
# Chart renderers
# ═══════════════════════════════════════════════════════════════════════


def _render_daily_chart(df: pd.DataFrame, plant_alias: str, view_date: date) -> None:
    """Render power + irradiance dual-axis chart for a single day."""
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # One area trace per device
    device_ids = sorted(df["device_id"].unique()) if "device_id" in df.columns else ["all"]

    for idx, dev in enumerate(device_ids):
        dev_df = df[df["device_id"] == dev] if "device_id" in df.columns else df
        color = CHART_COLORS[idx % len(CHART_COLORS)]

        fig.add_trace(
            go.Scatter(
                x=dev_df["ts"],
                y=dev_df["power_kw"],
                name=f"Power — {dev}",
                mode="lines",
                fill="tonexty" if idx > 0 else "tozeroy",
                stackgroup="power",
                line={"color": color},
                hovertemplate="%{x|%H:%M}<br>%{y:,.1f} kW<extra>" + dev + "</extra>",
            ),
            secondary_y=False,
        )

    # Irradiance trace
    if "irradiance_wm2" in df.columns and df["irradiance_wm2"].notna().any():
        irr_df = df.groupby("ts", as_index=False)["irradiance_wm2"].mean()
        fig.add_trace(
            go.Scatter(
                x=irr_df["ts"],
                y=irr_df["irradiance_wm2"],
                name="Irradiance",
                mode="lines",
                line={"color": "#F39C12", "dash": "dash", "width": 2},
                hovertemplate="%{x|%H:%M}<br>%{y:,.0f} W/m²<extra>Irradiance</extra>",
            ),
            secondary_y=True,
        )

    # "Now" line if viewing today
    if view_date == date.today():
        now = datetime.now()
        fig.add_vline(
            x=now,
            line_dash="dot",
            line_color=AMPYR_TEAL,
            annotation_text="Now",
            annotation_position="top right",
        )

    fig.update_layout(
        template=PLOTLY_TEMPLATE,
        title=f"{plant_alias} — {view_date.strftime('%d %b %Y')}",
        hovermode="x unified",
        legend={"orientation": "h", "yanchor": "bottom", "y": -0.25},
    )
    fig.update_xaxes(title_text="Time")
    fig.update_yaxes(title_text="Power (kW)", secondary_y=False)
    fig.update_yaxes(title_text="Irradiance (W/m²)", secondary_y=True)

    st.plotly_chart(fig, use_container_width=True)


def _render_multi_day(
    svc: LiveDataService,
    plant_uid: str,
    plant_alias: str,
    end_date: date,
    device_ids: list[str] | None,
) -> None:
    """Render multi-day comparison: power overlay + daily energy bar."""
    days_back = st.slider("Days to compare", 1, 30, 7, key="multi_day_slider")
    start_date = end_date - timedelta(days=days_back)

    try:
        mdf = svc.get_multi_day_readings(plant_uid, start_date, end_date, device_ids=device_ids)
    except Exception as exc:
        logger.exception("Failed to load multi-day readings")
        st.error(f"Could not load multi-day data: {exc}")
        return

    if mdf is None or (isinstance(mdf, pd.DataFrame) and mdf.empty):
        st.info("No multi-day data available for the selected range.")
        return

    mdf["ts"] = pd.to_datetime(mdf["ts"])
    mdf["date"] = mdf["ts"].dt.date
    mdf["time_of_day"] = mdf["ts"].dt.time

    unique_dates = sorted(mdf["date"].unique())

    # ── Power overlay chart ─────────────────────────────────────────
    fig_overlay = go.Figure()
    for idx, d in enumerate(unique_dates):
        day_df = mdf[mdf["date"] == d]
        agg = day_df.groupby("time_of_day", as_index=False)["power_kw"].sum()
        color = CHART_COLORS[idx % len(CHART_COLORS)]

        fig_overlay.add_trace(
            go.Scatter(
                x=agg["time_of_day"].astype(str),
                y=agg["power_kw"],
                name=str(d),
                mode="lines",
                line={"color": color},
                hovertemplate="%{x}<br>%{y:,.1f} kW<extra>" + str(d) + "</extra>",
            )
        )

    fig_overlay.update_layout(
        template=PLOTLY_TEMPLATE,
        title=f"{plant_alias} — Power Overlay ({start_date.strftime('%d %b')} – {end_date.strftime('%d %b %Y')})",
        xaxis_title="Time of Day",
        yaxis_title="Power (kW)",
        hovermode="x unified",
        legend={"orientation": "h", "yanchor": "bottom", "y": -0.3},
    )
    st.plotly_chart(fig_overlay, use_container_width=True)

    # ── Daily energy bar chart ──────────────────────────────────────
    if "energy_kwh" in mdf.columns:
        daily_energy = mdf.groupby("date", as_index=False)["energy_kwh"].sum()

        fig_bar = go.Figure(
            go.Bar(
                x=[str(d) for d in daily_energy["date"]],
                y=daily_energy["energy_kwh"],
                marker_color=AMPYR_TEAL_LIGHT,
                hovertemplate="%{x}<br>%{y:,.0f} kWh<extra></extra>",
            )
        )
        fig_bar.update_layout(
            template=PLOTLY_TEMPLATE,
            title="Daily Energy Production",
            xaxis_title="Date",
            yaxis_title="Energy (kWh)",
        )
        st.plotly_chart(fig_bar, use_container_width=True)
