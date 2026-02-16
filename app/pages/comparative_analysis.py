"""Comparative Analysis page backed by ComparativeEngine (DuckDB repositories)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import plotly.express as px
import streamlit as st

from solar_platform.analysis.chart_templates import apply_analysis_template
from solar_platform.analysis.comparative import ComparativeEngine
from solar_platform.db.repository import PlantRepository


def _default_date_range() -> tuple[datetime, datetime]:
    end = datetime.now(UTC)
    return end - timedelta(days=30), end


@st.cache_data(ttl=300)
def _cached_comparative_run(start_iso: str, end_iso: str, plant_uids: tuple):
    from datetime import datetime as _dt
    start = _dt.fromisoformat(start_iso)
    end = _dt.fromisoformat(end_iso)
    return ComparativeEngine().run(start=start, end=end, plant_uids=list(plant_uids))


def render() -> None:
    """Render comparative analysis dashboard."""
    st.markdown("## 📊 Comparative Analysis")
    st.caption("Cross-plant performance comparison powered by repository-backed analysis services.")

    try:
        _render_body()
    except Exception as e:
        if "lock" in str(e).lower():
            st.warning(
                "⏳ The database is currently busy (a background job may be running). "
                "Please try again in a moment."
            )
        else:
            st.error(f"Error rendering Comparative Analysis: {e}")


def _render_body() -> None:
    plants = PlantRepository().list_all()
    if plants.empty:
        st.warning("No plants available for comparison.")
        return

    uid_col = "plant_uid" if "plant_uid" in plants.columns else "uid"
    name_col = "alias" if "alias" in plants.columns else "plant_name"
    options = [f"{row[name_col]} ({row[uid_col]})" for _, row in plants.iterrows()]
    option_to_uid = {f"{row[name_col]} ({row[uid_col]})": row[uid_col] for _, row in plants.iterrows()}

    col1, col2 = st.columns([2, 1])
    with col1:
        selected = st.multiselect("Plants", options=options, default=options[: min(5, len(options))])
    with col2:
        days = st.selectbox("Window", options=[7, 30, 90, 180, 365], index=1)

    if not selected:
        st.info("Select at least one plant.")
        return

    end = datetime.now(UTC)
    start = end - timedelta(days=int(days))
    uids = [option_to_uid[item] for item in selected]

    result = _cached_comparative_run(start.isoformat(), end.isoformat(), tuple(uids))

    if result.table is None or result.table.empty:
        st.warning("No comparison data available for selected plants.")
        for warning in result.warnings:
            st.caption(f"- {warning}")
        return

    k1, k2, k3 = st.columns(3)
    k1.metric("Plants Compared", result.summary.get("plants_compared", 0))
    k2.metric("Total Energy (kWh)", f"{result.summary.get('total_energy_kwh', 0):,.1f}")
    mean_pr = result.summary.get("mean_pr_pct")
    k3.metric("Mean PR (%)", f"{mean_pr:.2f}" if mean_pr is not None else "n/a")

    st.markdown("### Summary Table")
    st.dataframe(result.table, use_container_width=True, hide_index=True)

    chart_metric = st.selectbox(
        "Chart Metric",
        options=["Energy (kWh)", "PR (%)", "Availability (%)", "Clipping Loss (%)"],
        index=0,
    )

    chart_df = result.table[["plant_name", chart_metric]].dropna()
    fig = px.bar(
        chart_df,
        x="plant_name",
        y=chart_metric,
        color=chart_metric,
        color_continuous_scale="Tealgrn",
        title=f"Comparative {chart_metric}",
    )
    apply_analysis_template(fig)
    st.plotly_chart(fig, use_container_width=True)

    if result.timeseries is not None and not result.timeseries.empty:
        st.markdown("### Daily Energy Proxy Trend")
        ts_fig = px.line(
            result.timeseries,
            x="date",
            y="energy_proxy",
            color="plant_name",
            title="Daily Energy Proxy by Plant",
        )
        apply_analysis_template(ts_fig)
        st.plotly_chart(ts_fig, use_container_width=True)
