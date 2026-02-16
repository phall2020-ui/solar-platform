"""Curtailment Analysis -- thin Streamlit renderer backed by CurtailmentEngine."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.components.report_button import add_to_report_button
from solar_platform.analysis.chart_templates import apply_analysis_template
from solar_platform.analysis.curtailment import CurtailmentEngine
from solar_platform.db.repository import PlantRepository


# ---------------------------------------------------------------------------
# Cached data fetch
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300)
def _cached_curtailment(plant_uid: str, start_iso: str, end_iso: str,
                       limit_threshold_pct: int):
    """Cache curtailment analysis results (5-min TTL)."""
    start_dt = datetime.fromisoformat(start_iso)
    end_dt = datetime.fromisoformat(end_iso)
    return CurtailmentEngine().run(
        plant_uid, start_dt, end_dt,
        limit_threshold_pct=limit_threshold_pct,
    )


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

    selected = st.selectbox("Select Plant", options=options, key="curt_plant")
    return uid_map.get(selected)


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

def _curtailment_timeseries_chart(timeseries, ts_col):
    """Show curtailment events over time as a coloured scatter."""
    df = timeseries.copy()
    df["status"] = df["is_curtailed"].map({True: "Curtailed", False: "Normal"})
    colour_map = {"Normal": "#4C78A8", "Curtailed": "#E45756"}

    fig = px.scatter(
        df, x=ts_col, y="is_curtailed",
        color="status", color_discrete_map=colour_map,
        title="Curtailment Events Over Time",
        labels={"is_curtailed": "Curtailed?", ts_col: "Timestamp"},
    )
    fig.update_traces(marker=dict(size=4))
    apply_analysis_template(fig, title="Curtailment Events Over Time")
    return fig


def _daily_summary(timeseries, ts_col):
    """Aggregate curtailment stats by day."""
    df = timeseries.copy()
    df["date"] = df[ts_col].dt.date
    daily = df.groupby("date").agg(
        records=("is_curtailed", "count"),
        curtailed_records=("is_curtailed", "sum"),
    ).reset_index()
    daily["curtailment_rate_pct"] = (daily["curtailed_records"] / daily["records"] * 100).round(2)
    return daily


# ---------------------------------------------------------------------------
# Main render
# ---------------------------------------------------------------------------

def render():
    """Render the Curtailment Analysis page."""
    st.markdown("## \U0001f50c Curtailment Analysis")
    st.caption("Detects export-limitation curtailment events, backed by CurtailmentEngine.")

    try:
        _render_body()
    except Exception as e:
        if "lock" in str(e).lower():
            st.warning(
                "⏳ The database is currently busy (a background job may be running). "
                "Please try again in a moment."
            )
        else:
            st.error(f"Error rendering Curtailment Analysis: {e}")


def _render_body():
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
            key="curt_date_range",
        )

    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        start_dt = datetime.combine(date_range[0], datetime.min.time())
        end_dt = datetime.combine(date_range[1], datetime.max.time())
    else:
        start_dt, end_dt = _default_date_range()

    # Analysis-specific parameters
    with st.expander("Analysis Parameters", expanded=False):
        limit_threshold_pct = st.slider(
            "Export Limit Threshold (%)", min_value=50, max_value=100,
            value=99, step=1, key="curt_threshold",
            help="Records with export limit below this percentage are considered curtailed.",
        )

    # --- Run engine (cached) ------------------------------------------------
    with st.spinner("Running curtailment analysis..."):
        result = _cached_curtailment(
            plant_uid, start_dt.isoformat(), end_dt.isoformat(),
            limit_threshold_pct=limit_threshold_pct,
        )

    # --- Warnings -----------------------------------------------------------
    if result.warnings:
        for w in result.warnings:
            st.warning(w)
        if result.timeseries is None or result.timeseries.empty:
            return

    # --- KPI Metrics --------------------------------------------------------
    k1, k2, k3 = st.columns(3)
    k1.metric("Curtailment Rate", f"{result.summary.get('curtailment_rate_pct', 0):.2f} %")
    k2.metric("Curtailed Records", f"{result.summary.get('curtailed_records', 0):,}")
    k3.metric("Total Records", f"{result.summary.get('records', 0):,}")

    st.divider()

    # --- Time-series chart --------------------------------------------------
    ts = result.timeseries
    if ts is not None and not ts.empty:
        ts_col = [c for c in ts.columns if c != "is_curtailed"][0]

        st.markdown("### Curtailment Events")
        fig = _curtailment_timeseries_chart(ts, ts_col)
        st.plotly_chart(fig, use_container_width=True)
        add_to_report_button(
            fig, title="Curtailment \u2014 Events Chart",
            item_type="chart", source_page="Curtailment Analysis",
            button_key="curt_ts_chart",
        )

        # --- Daily summary table --------------------------------------------
        st.markdown("### Daily Curtailment Summary")
        daily = _daily_summary(ts, ts_col)
        st.dataframe(daily, use_container_width=True, hide_index=True)
        add_to_report_button(
            daily, title="Curtailment \u2014 Daily Summary",
            item_type="table", source_page="Curtailment Analysis",
            button_key="curt_daily_table",
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
