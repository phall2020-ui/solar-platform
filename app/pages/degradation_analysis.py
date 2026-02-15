"""Degradation analysis page."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import plotly.express as px
import streamlit as st

from solar_platform.analysis.chart_templates import apply_analysis_template
from solar_platform.analysis.degradation import DegradationEngine
from solar_platform.db.repository import PlantRepository


def render() -> None:
    st.markdown("## 📉 Degradation Analysis")
    st.caption("Annualized PR trend estimation from monthly medians.")

    plants = PlantRepository().list_all()
    if plants.empty:
        st.warning("No plants found.")
        return

    uid_col = "plant_uid" if "plant_uid" in plants.columns else "uid"
    name_col = "alias" if "alias" in plants.columns else "plant_name"
    plant_map = {str(row[name_col]): str(row[uid_col]) for _, row in plants.iterrows()}

    col1, col2 = st.columns(2)
    with col1:
        plant = st.selectbox("Plant", options=list(plant_map.keys()))
    with col2:
        years = st.selectbox("Lookback", options=[1, 2, 3], index=0)

    end = datetime.now(UTC)
    start = end - timedelta(days=365 * int(years))

    result = DegradationEngine().run(plant_map[plant], start, end)
    if result.timeseries is None or result.timeseries.empty:
        st.warning("No degradation data available.")
        for warning in result.warnings:
            st.caption(f"- {warning}")
        return

    annualized = result.summary.get("annualized_pr_change_pct")
    st.metric("Annualized PR Change (%)", f"{annualized:.3f}" if annualized is not None else "n/a")
    st.metric("Months Analyzed", result.summary.get("months_analyzed", 0))

    fig = px.line(result.timeseries, x="month", y=["pr_pct", "trend_pr_pct"], title="Monthly PR and Trend")
    apply_analysis_template(fig)
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(result.timeseries, use_container_width=True, hide_index=True)
