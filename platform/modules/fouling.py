"""Fouling (Soiling) Analysis – thin Streamlit renderer."""
from __future__ import annotations

from datetime import datetime, timedelta

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from components.report_button import add_to_report_button
from services.analysis.chart_templates import apply_analysis_template
from services.analysis.fouling import FoulingEngine
from services.database.repository import PlantRepository


def render() -> None:
    """Render the Fouling Analysis page."""
    st.markdown("## 🧹 Fouling Analysis")
    st.caption("Daily soiling trend – baseline vs current normalised ratio.")

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
    end = datetime.utcnow()
    start = end - timedelta(days=int(days))

    with st.spinner("Running fouling analysis…"):
        result = FoulingEngine().run(plant_map[name], start, end)

    if not result.has_data:
        st.warning("No data available for the selected period.")
        for w in result.warnings:
            st.caption(f"⚠ {w}")
        return

    # ── KPI metrics ──────────────────────────────────────────────────
    s = result.summary
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Days Analysed", s.get("days_analyzed", 0))
    k2.metric("Baseline Ratio", f"{s.get('baseline_ratio', 0):.4f}")
    k3.metric("Current Ratio", f"{s.get('current_ratio', 0):.4f}")
    k4.metric("Estimated Loss", f"{s.get('estimated_fouling_loss_pct', 0):.1f} %")

    add_to_report_button(
        content={
            "Days Analysed": s.get("days_analyzed"),
            "Baseline Ratio": s.get("baseline_ratio"),
            "Current Ratio": s.get("current_ratio"),
            "Loss %": s.get("estimated_fouling_loss_pct"),
        },
        title=f"Fouling KPIs – {name}",
        item_type="kpi",
        description="Baseline vs current soiling ratio and estimated loss",
        source_page="Fouling",
        button_key=f"fouling_kpi_{name}".replace(" ", "_"),
    )

    if result.warnings:
        with st.expander("Warnings"):
            for w in result.warnings:
                st.caption(f"⚠ {w}")

    # ── Daily soiling trend line chart ───────────────────────────────
    ts = result.timeseries
    if ts is not None and not ts.empty:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=ts["date"],
            y=ts["norm_ratio"],
            mode="lines+markers",
            name="Daily Ratio",
            line=dict(color="#00838f"),
            marker=dict(size=4),
        ))

        # Baseline reference line
        baseline = s.get("baseline_ratio")
        if baseline:
            fig.add_hline(
                y=baseline,
                line_dash="dash",
                line_color="#2e7d32",
                annotation_text=f"Baseline {baseline:.4f}",
                annotation_position="top left",
            )

        apply_analysis_template(fig, title="Daily Soiling Trend")
        fig.update_yaxes(title_text="Normalised Ratio")
        fig.update_xaxes(title_text="Date")
        st.plotly_chart(fig, use_container_width=True)

        add_to_report_button(
            content=fig,
            title=f"Fouling Trend – {name}",
            item_type="chart",
            description="Daily normalised power-to-irradiance ratio with baseline",
            source_page="Fouling",
            button_key=f"fouling_chart_{name}".replace(" ", "_"),
        )

        # ── Data table ───────────────────────────────────────────────
        with st.expander("Daily data table"):
            st.dataframe(ts, use_container_width=True, hide_index=True)
            add_to_report_button(
                content=ts,
                title=f"Fouling Daily Data – {name}",
                item_type="table",
                description="Daily normalised ratio values",
                source_page="Fouling",
                button_key=f"fouling_table_{name}".replace(" ", "_"),
            )

    st.caption(f"Calculation took {result.calculation_seconds:.2f} s")
