"""Clipping Analysis -- thin Streamlit renderer backed by ClippingEngine."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from components.report_button import add_to_report_button
from services.analysis.chart_templates import apply_analysis_template
from services.analysis.clipping import ClippingEngine
from services.database.repository import PlantRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _default_date_range():
    end = datetime.now(UTC)
    return end - timedelta(days=30), end


def _plant_selector():
    """Render plant dropdown and return selected plant_uid (or None)."""
    plants = PlantRepository().list_all()
    if plants.empty:
        st.warning("No plants available. Please add plant data first.")
        return None

    uid_col = "plant_uid" if "plant_uid" in plants.columns else "uid"
    name_col = "alias" if "alias" in plants.columns else "plant_name"
    options = [f"{row[name_col]} ({row[uid_col]})" for _, row in plants.iterrows()]
    uid_map = {f"{row[name_col]} ({row[uid_col]})": row[uid_col] for _, row in plants.iterrows()}

    selected = st.selectbox("Select Plant", options=options, key="clip_plant")
    return uid_map.get(selected)


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

def _power_timeseries_chart(timeseries, ts_col, power_col):
    """Power timeseries with clipped intervals highlighted."""
    normal = timeseries[~timeseries["is_clipped"]]
    clipped = timeseries[timeseries["is_clipped"]]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=normal[ts_col], y=normal[power_col],
        mode="markers", marker=dict(size=3, color="#4C78A8"),
        name="Normal",
    ))
    fig.add_trace(go.Scatter(
        x=clipped[ts_col], y=clipped[power_col],
        mode="markers", marker=dict(size=4, color="#E45756"),
        name="Clipped",
    ))
    apply_analysis_template(fig, title="Power Output \u2014 Clipped Intervals Highlighted")
    fig.update_xaxes(title_text="Timestamp")
    fig.update_yaxes(title_text="Power")
    return fig


def _daily_summary(timeseries, ts_col, power_col):
    """Aggregate clipping stats by day."""
    df = timeseries.copy()
    df["date"] = df[ts_col].dt.date
    daily = df.groupby("date").agg(
        records=(power_col, "count"),
        clipped_records=("is_clipped", "sum"),
        mean_power=(power_col, "mean"),
        max_power=(power_col, "max"),
    ).reset_index()
    daily["clipping_rate_pct"] = (daily["clipped_records"] / daily["records"] * 100).round(2)
    return daily


# ---------------------------------------------------------------------------
# Main render
# ---------------------------------------------------------------------------

def render():
    """Render the Clipping Analysis page."""
    st.markdown("## \u26a1 Clipping Analysis")
    st.caption("Detects inverter clipping using power-plateau analysis, backed by ClippingEngine.")

    # --- Controls -----------------------------------------------------------
    col_plant, col_dates = st.columns([2, 1])

    with col_plant:
        plant_uid = _plant_selector()
    if plant_uid is None:
        return

    with col_dates:
        default_start, default_end = _default_date_range()
        date_range = st.date_input(
            "Date Range",
            value=(default_start.date(), default_end.date()),
            key="clip_date_range",
        )

    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        start_dt = datetime.combine(date_range[0], datetime.min.time())
        end_dt = datetime.combine(date_range[1], datetime.max.time())
    else:
        start_dt, end_dt = _default_date_range()

    # Analysis-specific parameters
    with st.expander("Analysis Parameters", expanded=False):
        p1, p2 = st.columns(2)
        with p1:
            plateau_quantile = st.slider(
                "Plateau Quantile", min_value=0.90, max_value=0.99,
                value=0.98, step=0.01, key="clip_quantile",
                help="Power quantile above which output is considered clipped.",
            )
        with p2:
            min_irradiance = st.slider(
                "Min Irradiance (W/m\u00b2)", min_value=200, max_value=800,
                value=600, step=50, key="clip_min_irr",
                help="Minimum irradiance for clipping to be meaningful.",
            )

    # --- Run engine ---------------------------------------------------------
    engine = ClippingEngine()
    with st.spinner("Running clipping analysis..."):
        result = engine.run(
            plant_uid, start_dt, end_dt,
            plateau_quantile=plateau_quantile,
            min_irradiance=min_irradiance,
        )

    # --- Warnings -----------------------------------------------------------
    if result.warnings:
        for w in result.warnings:
            st.warning(w)
        if result.timeseries is None or result.timeseries.empty:
            return

    # --- KPI Metrics --------------------------------------------------------
    k1, k2, k3 = st.columns(3)
    k1.metric("Clipping Rate", f"{result.summary.get('clipping_rate_pct', 0):.2f} %")
    k2.metric("Estimated Loss", f"{result.summary.get('estimated_clipping_loss_pct', 0):.2f} %")
    k3.metric("Total Energy", f"{result.summary.get('energy_kwh', 0):,.1f} kWh")

    st.divider()

    # --- Time-series chart --------------------------------------------------
    ts = result.timeseries
    if ts is not None and not ts.empty:
        cols = [c for c in ts.columns if c != "is_clipped"]
        ts_col = cols[0]
        power_col = cols[1] if len(cols) > 1 else cols[0]

        st.markdown("### Power Time-Series")
        fig = _power_timeseries_chart(ts, ts_col, power_col)
        st.plotly_chart(fig, use_container_width=True)
        add_to_report_button(
            fig, title="Clipping \u2014 Power Time-Series",
            item_type="chart", source_page="Clipping Analysis",
            button_key="clip_ts_chart",
        )

        # --- Daily summary table --------------------------------------------
        st.markdown("### Daily Clipping Summary")
        daily = _daily_summary(ts, ts_col, power_col)
        st.dataframe(daily, use_container_width=True, hide_index=True)
        add_to_report_button(
            daily, title="Clipping \u2014 Daily Summary",
            item_type="table", source_page="Clipping Analysis",
            button_key="clip_daily_table",
        )

    # --- Raw detail ---------------------------------------------------------
    with st.expander("Detailed Readings"):
        if ts is not None and not ts.empty:
            st.dataframe(ts, use_container_width=True, hide_index=True)

    # --- Calculation metadata -----------------------------------------------
    st.caption(
        f"Analysis completed in {result.calculation_seconds:.3f}s \u00b7 "
        f"{result.summary.get('records', 0):,} records processed"
    )
