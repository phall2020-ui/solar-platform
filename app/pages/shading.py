"""Shading Analysis – thin Streamlit renderer."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.components.report_button import add_to_report_button
from solar_platform.analysis.chart_templates import apply_analysis_template
from solar_platform.analysis.shading import ShadingEngine
from solar_platform.db.repository import PlantRepository


def render() -> None:
    """Render the Shading Analysis page."""
    st.markdown("## 🌤️ Shading Analysis")
    st.caption("Hourly normalised performance profile – shoulder vs midday ratio.")

    try:
        _render_body()
    except Exception as e:
        if "lock" in str(e).lower():
            st.warning(
                "⏳ The database is currently busy (a background job may be running). "
                "Please try again in a moment."
            )
        else:
            st.error(f"Error rendering Shading Analysis: {e}")


def _render_body() -> None:
    # ── Plant selection ──────────────────────────────────────────────
    plants = PlantRepository().list_all()
    if plants.empty:
        st.warning("No plants found.")
        return

    uid_col = "plant_uid" if "plant_uid" in plants.columns else "uid"
    name_col = "alias" if "alias" in plants.columns else "plant_name"
    plant_map = {
        str(row[name_col]): str(row[uid_col]) for _, row in plants.iterrows()
    }

    col1, col2 = st.columns(2)
    with col1:
        name = st.selectbox("Plant", list(plant_map.keys()))
    with col2:
        days = st.selectbox("Period (days)", [30, 60, 90, 180, 365], index=2)

    # ── Run engine ───────────────────────────────────────────────────
    end = datetime.now(UTC)
    start = end - timedelta(days=int(days))

    with st.spinner("Running shading analysis…"):
        result = ShadingEngine().run(plant_map[name], start, end)

    if not result.has_data:
        st.warning("No data available for the selected period.")
        for w in result.warnings:
            st.caption(f"⚠ {w}")
        return

    # ── KPI metrics ──────────────────────────────────────────────────
    s = result.summary
    k1, k2, k3 = st.columns(3)
    k1.metric("Shading Ratio", f"{s.get('shading_ratio', 0):.3f}")
    k2.metric("Estimated Loss", f"{s.get('estimated_shading_loss_pct', 0):.1f} %")
    k3.metric("Hourly Data Points", s.get("hourly_points", 0))

    add_to_report_button(
        content={"Shading Ratio": s.get("shading_ratio"), "Loss %": s.get("estimated_shading_loss_pct")},
        title=f"Shading KPIs – {name}",
        item_type="kpi",
        description="Shoulder-to-midday shading ratio and estimated loss",
        source_page="Shading",
        button_key=f"shading_kpi_{name}".replace(" ", "_"),
    )

    if result.warnings:
        with st.expander("Warnings"):
            for w in result.warnings:
                st.caption(f"⚠ {w}")

    # ── Hourly profile bar chart ─────────────────────────────────────
    hourly = result.table
    if hourly is not None and not hourly.empty:
        fig = px.bar(
            hourly,
            x="hour",
            y="norm_ratio",
            labels={"hour": "Hour of Day", "norm_ratio": "Normalised Ratio"},
        )
        fig.update_traces(marker_color=[
            "#c62828" if v < 0.85 else ("#ff8f00" if v < 0.95 else "#2e7d32")
            for v in hourly["norm_ratio"]
        ])
        apply_analysis_template(fig, title="Hourly Normalised Performance Profile")
        st.plotly_chart(fig, use_container_width=True)

        add_to_report_button(
            content=fig,
            title=f"Shading Hourly Profile – {name}",
            item_type="chart",
            description="Normalised power-to-irradiance ratio by hour of day",
            source_page="Shading",
            button_key=f"shading_chart_{name}".replace(" ", "_"),
        )

        # ── Classification legend ────────────────────────────────────
        st.markdown(
            "**Classification:**   🟢 Ratio ≥ 0.95 (no shading) · "
            "🟡 0.85–0.95 (mild) · 🟠 0.70–0.85 (moderate) · 🔴 < 0.70 (severe)"
        )

        # ── Data table ───────────────────────────────────────────────
        with st.expander("Hourly data table"):
            st.dataframe(hourly, use_container_width=True, hide_index=True)
            add_to_report_button(
                content=hourly,
                title=f"Shading Hourly Table – {name}",
                item_type="table",
                description="Normalised ratio by hour of day",
                source_page="Shading",
                button_key=f"shading_table_{name}".replace(" ", "_"),
            )

    st.caption(f"Calculation took {result.calculation_seconds:.2f} s")
