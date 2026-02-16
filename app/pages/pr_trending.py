"""PR trending analysis page."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import plotly.express as px
import streamlit as st

from solar_platform.analysis.chart_templates import apply_analysis_template
from solar_platform.analysis.pr_trending import PRTrendingEngine
from solar_platform.db.repository import PlantRepository


def render() -> None:
    st.markdown("## 📈 PR Trending")

    try:
        _render_body()
    except Exception as e:
        if "lock" in str(e).lower():
            st.warning(
                "⏳ The database is currently busy (a background job may be running). "
                "Please try again in a moment."
            )
        else:
            st.error(f"Error rendering PR Trending: {e}")


def _render_body() -> None:
    plants = PlantRepository().list_all()
    if plants.empty:
        st.warning("No plants found.")
        return

    uid_col = "plant_uid" if "plant_uid" in plants.columns else "uid"
    name_col = "alias" if "alias" in plants.columns else "plant_name"
    plant_map = {str(row[name_col]): str(row[uid_col]) for _, row in plants.iterrows()}

    col1, col2, col3 = st.columns(3)
    with col1:
        name = st.selectbox("Plant", options=list(plant_map.keys()))
    with col2:
        days = st.selectbox("Days", options=[30, 60, 90, 180, 365], index=2)
    with col3:
        window = st.selectbox("Rolling Window", options=[3, 7, 14, 30], index=1)

    end = datetime.now(UTC)
    start = end - timedelta(days=int(days))

    result = PRTrendingEngine().run(plant_map[name], start, end, rolling_window_days=window)
    if result.timeseries is None or result.timeseries.empty:
        st.warning("No PR trend data available.")
        return

    st.metric("Mean PR (%)", f"{result.summary.get('mean_pr_pct', 0):.2f}")
    st.metric("Latest PR (%)", f"{result.summary.get('latest_pr_pct', 0):.2f}")

    fig = px.line(result.timeseries, x="date", y=["pr_pct", "rolling_pr_pct"], title="PR Trend")
    apply_analysis_template(fig)
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(result.timeseries.tail(30), use_container_width=True, hide_index=True)
