"""
Site Monitor — Live & historic time-series charting for individual solar sites.

Provides an interactive Streamlit page with:
  • Plant selector with device-level breakdown
  • Date-range picker with quick presets
  • Live-mode toggle (auto-refresh via ``st.rerun``)
  • Plotly time-series chart (power + irradiance dual-axis)
  • Per-inverter breakdown tabs
  • KPI summary cards (Current Power, Today's Energy, PR, Availability)
  • Data quality indicator

Reads from the existing DuckDB ``readings`` table through
:mod:`backend.database`.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from solar_platform.db.cache import cached
from solar_platform.db.legacy import get_db

logger = logging.getLogger(__name__)

# ── Constants ───────────────────────────────────────────────────────────

_PRESETS: dict[str, tuple[int, str]] = {
    "Today": (0, "today"),
    "Yesterday": (1, "yesterday"),
    "Last 7 Days": (7, "range"),
    "Last 30 Days": (30, "range"),
    "Custom": (-1, "custom"),
}

# Column name preferences — mirrors Solar Toolkit conventions
_POWER_COLS = ("activePower_value", "apparentPower_value", "dcCurrent_value", "exportEnergy_value")
_IRRADIANCE_COL = "poaIrradiance_value"

# Brand colours (AMPYR)
_CLR_PRIMARY = "#5FBFA0"
_CLR_SECONDARY = "#4A9E80"
_CLR_ACCENT = "#8FE0C5"
_CLR_NEGATIVE = "#E66B6B"
_CLR_WARNING = "#F2C265"
_CLR_SURFACE = "#1E2538"

_CHART_PALETTE = [
    "#5FBFA0", "#8E44AD", "#5D6D7E", "#4A9E80",
    "#E66B6B", "#F2C265", "#8FE0C5", "#3498DB",
    "#E67E22", "#1ABC9C", "#9B59B6", "#2ECC71",
]


# ═══════════════════════════════════════════════════════════════════════
# Public entry point (called from PAGE_REGISTRY)
# ═══════════════════════════════════════════════════════════════════════


def render() -> None:
    """Render the Site Monitor page."""
    st.title("📡 Site Monitor")
    st.markdown("Live and historic performance monitoring for individual solar sites.")

    db = get_db()

    # ── Plant selector ──────────────────────────────────────────────────
    try:
        plants = db.get_plants()
    except Exception as exc:
        st.error(f"Could not load plants: {exc}")
        logger.exception("Failed to load plants")
        return

    if not plants:
        st.warning("No plants registered. Add a plant in **Plant Management** first.")
        return

    alias_map: dict[str, Any] = {p.alias: p for p in plants}
    selected_alias = st.selectbox(
        "Select Plant",
        options=list(alias_map.keys()),
        key="sm_plant_select",
    )
    plant = alias_map[selected_alias]

    # ── Date range ──────────────────────────────────────────────────────
    col_preset, col_start, col_end = st.columns([1.5, 1, 1])
    with col_preset:
        preset = st.selectbox("Date Range", options=list(_PRESETS.keys()), index=0, key="sm_preset")

    today = date.today()
    days_back, mode = _PRESETS[preset]

    if mode == "today":
        default_start = today
        default_end = today
    elif mode == "yesterday":
        default_start = today - timedelta(days=1)
        default_end = today - timedelta(days=1)
    elif mode == "range":
        default_start = today - timedelta(days=days_back)
        default_end = today
    else:
        default_start = today - timedelta(days=7)
        default_end = today

    with col_start:
        start_date = st.date_input("Start", value=default_start, key="sm_start")
    with col_end:
        end_date = st.date_input("End", value=default_end, key="sm_end")

    if start_date > end_date:
        st.error("Start date must be before or equal to end date.")
        return

    # ── Live mode toggle ────────────────────────────────────────────────
    col_live, col_info = st.columns([1, 3])
    with col_live:
        live_mode = st.toggle("🔴 Live Mode", value=False, key="sm_live")
    with col_info:
        if live_mode:
            st.caption("Auto-refreshes every 30 seconds")

    # Initialise / manage refresh timer
    if live_mode:
        if "sm_last_refresh" not in st.session_state:
            st.session_state["sm_last_refresh"] = datetime.now(tz=timezone.utc)
        elapsed = (datetime.now(tz=timezone.utc) - st.session_state["sm_last_refresh"]).total_seconds()
        if elapsed >= 30:
            st.session_state["sm_last_refresh"] = datetime.now(tz=timezone.utc)
            st.rerun()

    # ── Fetch data ──────────────────────────────────────────────────────
    start_str = start_date.isoformat()
    end_str = end_date.isoformat()

    with st.spinner("Loading readings…"):
        try:
            df = db.query_readings_df(
                plant_uid=plant.plant_uid,
                start_date=start_str,
                end_date=end_str,
                limit=100_000,
            )
        except Exception as exc:
            st.error(f"Query failed: {exc}")
            logger.exception("query_readings_df failed for %s", plant.plant_uid)
            return

    if df.empty:
        st.info("No readings found for the selected plant and date range.")
        return

    # Ensure ts is datetime
    df["ts"] = pd.to_datetime(df["ts"], utc=True, errors="coerce")
    df = df.dropna(subset=["ts"]).sort_values("ts")

    # Detect the power column
    power_col = _detect_column(df, _POWER_COLS)
    irr_col = _IRRADIANCE_COL if _IRRADIANCE_COL in df.columns else None

    # ── KPI summary cards ───────────────────────────────────────────────
    _render_kpi_cards(df, power_col, irr_col, plant)

    # ── Data quality indicator ─────────────────────────────────────────
    _render_data_quality(db, plant, start_date, end_date)

    st.markdown("---")

    # ── Main chart: Power + Irradiance ──────────────────────────────────
    _render_main_chart(df, power_col, irr_col, plant.alias)

    # ── Device-level breakdown tabs ─────────────────────────────────────
    _render_device_tabs(df, power_col, irr_col)


# ═══════════════════════════════════════════════════════════════════════
# Internal rendering helpers
# ═══════════════════════════════════════════════════════════════════════


def _detect_column(df: pd.DataFrame, preferences: tuple[str, ...]) -> str | None:
    """Return the first column name from *preferences* that exists and has data."""
    for col in preferences:
        if col in df.columns:
            try:
                if pd.to_numeric(df[col], errors="coerce").notna().any():
                    return col
            except Exception:
                continue
    return None


def _render_kpi_cards(
    df: pd.DataFrame,
    power_col: str | None,
    irr_col: str | None,
    plant: Any,
) -> None:
    """Render the four KPI cards across the top."""
    c1, c2, c3, c4 = st.columns(4)

    # ── Current Power ───────────────────────────────────────────────────
    with c1:
        if power_col and power_col in df.columns:
            latest_power = pd.to_numeric(df[power_col], errors="coerce").dropna()
            if not latest_power.empty:
                current_kw = latest_power.iloc[-1]
                label = f"{current_kw:,.1f} kW"
            else:
                label = "N/A"
        else:
            label = "N/A"
        st.metric("⚡ Current Power", label)

    # ── Today's Energy (simple trapezoidal estimate) ────────────────────
    with c2:
        energy_kwh = _estimate_energy(df, power_col)
        st.metric("🔋 Energy (period)", f"{energy_kwh:,.1f} kWh" if energy_kwh else "N/A")

    # ── Performance Ratio ──────────────────────────────────────────────
    with c3:
        pr = _estimate_pr(df, power_col, irr_col, plant)
        if pr is not None:
            st.metric("📊 Est. PR", f"{pr:.1%}")
        else:
            st.metric("📊 Est. PR", "N/A")

    # ── Data Availability ──────────────────────────────────────────────
    with c4:
        avail = _availability_pct(df)
        colour = "normal" if avail is None else ("off" if avail < 95.0 else "normal")
        st.metric(
            "✅ Availability",
            f"{avail:.1f} %" if avail is not None else "N/A",
            delta=None,
            delta_color=colour,
        )


def _render_data_quality(db: Any, plant: Any, start_date: date, end_date: date) -> None:
    """Show a data completeness indicator."""
    try:
        dq = db.get_data_quality(
            plant_uid=plant.plant_uid,
            start=datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc),
            end=datetime.combine(end_date + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc),
        )
        pct = dq.completeness_pct
        level = dq.level.value
        colour_map = {"good": "🟢", "acceptable": "🟡", "poor": "🔴"}
        icon = colour_map.get(level, "⚪")
        st.caption(f"{icon} Data completeness: **{pct:.1f} %** ({level}) — "
                   f"{dq.actual_readings:,} / {dq.expected_readings:,} readings")
    except Exception as exc:
        logger.debug("Data quality check skipped: %s", exc)


def _render_main_chart(
    df: pd.DataFrame,
    power_col: str | None,
    irr_col: str | None,
    plant_name: str,
) -> None:
    """Plotly dual-axis chart: power on left, irradiance on right."""
    fig = go.Figure()

    if power_col and power_col in df.columns:
        power_series = pd.to_numeric(df[power_col], errors="coerce")
        fig.add_trace(
            go.Scatter(
                x=df["ts"],
                y=power_series,
                mode="lines",
                name="Power (kW)",
                line=dict(color=_CLR_PRIMARY, width=2),
                hovertemplate="%{x}<br>Power: %{y:,.1f} kW<extra></extra>",
            )
        )

    if irr_col and irr_col in df.columns:
        irr_series = pd.to_numeric(df[irr_col], errors="coerce")
        fig.add_trace(
            go.Scatter(
                x=df["ts"],
                y=irr_series,
                mode="lines",
                name="Irradiance (W/m²)",
                line=dict(color=_CLR_WARNING, width=1.5, dash="dot"),
                yaxis="y2",
                hovertemplate="%{x}<br>Irradiance: %{y:,.0f} W/m²<extra></extra>",
            )
        )

    fig.update_layout(
        title=f"{plant_name} — Power & Irradiance",
        template="plotly_dark",
        paper_bgcolor=_CLR_SURFACE,
        plot_bgcolor=_CLR_SURFACE,
        height=480,
        margin=dict(l=60, r=60, t=50, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        xaxis=dict(title="", gridcolor="#2B354E"),
        yaxis=dict(title="Power (kW)", gridcolor="#2B354E", side="left"),
        yaxis2=dict(
            title="Irradiance (W/m²)",
            overlaying="y",
            side="right",
            showgrid=False,
        ),
        hovermode="x unified",
    )

    st.plotly_chart(fig, use_container_width=True, key="sm_main_chart")


def _render_device_tabs(
    df: pd.DataFrame,
    power_col: str | None,
    irr_col: str | None,
) -> None:
    """One tab per inverter / device showing its individual power curve."""
    device_ids = sorted(df["emig_id"].dropna().unique())
    if len(device_ids) <= 1:
        return  # nothing to break down

    st.subheader("Device-Level Breakdown")

    tabs = st.tabs([f"🔌 {did}" for did in device_ids])
    for tab, did in zip(tabs, device_ids):
        with tab:
            ddf = df[df["emig_id"] == did].copy()
            if ddf.empty or power_col is None or power_col not in ddf.columns:
                st.info(f"No power data for device {did}.")
                continue

            power_series = pd.to_numeric(ddf[power_col], errors="coerce")

            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=ddf["ts"],
                    y=power_series,
                    mode="lines",
                    name="Power (kW)",
                    line=dict(color=_CLR_PRIMARY, width=1.5),
                )
            )
            if irr_col and irr_col in ddf.columns:
                irr_series = pd.to_numeric(ddf[irr_col], errors="coerce")
                fig.add_trace(
                    go.Scatter(
                        x=ddf["ts"],
                        y=irr_series,
                        mode="lines",
                        name="Irradiance (W/m²)",
                        line=dict(color=_CLR_WARNING, width=1, dash="dot"),
                        yaxis="y2",
                    )
                )

            fig.update_layout(
                title=f"Device {did}",
                template="plotly_dark",
                paper_bgcolor=_CLR_SURFACE,
                plot_bgcolor=_CLR_SURFACE,
                height=350,
                margin=dict(l=50, r=50, t=40, b=30),
                xaxis=dict(gridcolor="#2B354E"),
                yaxis=dict(title="kW", gridcolor="#2B354E"),
                yaxis2=dict(title="W/m²", overlaying="y", side="right", showgrid=False),
                showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True, key=f"sm_dev_{did}")

            # Mini-stats
            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("Readings", f"{len(ddf):,}")
            peak = power_series.max()
            mc2.metric("Peak Power", f"{peak:,.1f} kW" if pd.notna(peak) else "N/A")
            mean_p = power_series.mean()
            mc3.metric("Avg Power", f"{mean_p:,.1f} kW" if pd.notna(mean_p) else "N/A")


# ═══════════════════════════════════════════════════════════════════════
# KPI calculation helpers
# ═══════════════════════════════════════════════════════════════════════


def _estimate_energy(df: pd.DataFrame, power_col: str | None) -> float | None:
    """Rough energy estimate (kWh) using trapezoidal integration on the power series."""
    if not power_col or power_col not in df.columns:
        return None

    try:
        ts = df["ts"]
        power = pd.to_numeric(df[power_col], errors="coerce")
        mask = power.notna()
        if mask.sum() < 2:
            return None

        ts_sec = ts[mask].astype("int64") / 1e9  # epoch seconds
        p = power[mask].values
        # Trapezoidal: sum of (Δt * (p[i]+p[i+1])/2)
        dt = ts_sec.diff().iloc[1:].values
        avg_p = (p[:-1] + p[1:]) / 2.0
        energy_ws = (dt * avg_p).sum()  # watt-seconds (if power is kW → kWh after /3600)
        return energy_ws / 3600.0
    except Exception:
        return None


def _estimate_pr(
    df: pd.DataFrame,
    power_col: str | None,
    irr_col: str | None,
    plant: Any,
) -> float | None:
    """
    Very rough Performance Ratio estimate.

    PR = (Actual Energy / (Irradiance × DC_Size)) — simplified.
    Returns None if insufficient data.
    """
    if not power_col or not irr_col or not plant.dc_size_kw:
        return None
    if power_col not in df.columns or irr_col not in df.columns:
        return None
    try:
        power = pd.to_numeric(df[power_col], errors="coerce")
        irr = pd.to_numeric(df[irr_col], errors="coerce")
        mask = power.notna() & irr.notna() & (irr > 50)
        if mask.sum() < 10:
            return None
        avg_power = power[mask].mean()
        avg_irr = irr[mask].mean()
        if avg_irr == 0:
            return None
        # PR ≈ (avg_power / dc_size) / (avg_irr / 1000)
        pr = (avg_power / plant.dc_size_kw) / (avg_irr / 1000.0)
        return max(0.0, min(pr, 1.5))  # clamp to reasonable bounds
    except Exception:
        return None


def _availability_pct(df: pd.DataFrame) -> float | None:
    """
    Simple availability proxy: % of 15-min intervals that have at least one reading.
    """
    if df.empty:
        return None
    try:
        ts = df["ts"]
        total_span = (ts.max() - ts.min()).total_seconds()
        if total_span <= 0:
            return 100.0
        expected_intervals = total_span / (15 * 60)
        if expected_intervals < 1:
            return 100.0
        actual_intervals = df.set_index("ts").resample("15min").size().gt(0).sum()
        return min(100.0, 100.0 * actual_intervals / expected_intervals)
    except Exception:
        return None
