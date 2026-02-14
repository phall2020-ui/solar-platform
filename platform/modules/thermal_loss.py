"""Thermal Loss Analysis – thin Streamlit renderer."""
from __future__ import annotations

from datetime import datetime, timedelta

import plotly.graph_objects as go
import streamlit as st

from components.report_button import add_to_report_button
from services.analysis.chart_templates import apply_analysis_template
from services.analysis.thermal import ThermalLossEngine
from services.database.repository import PlantRepository


def render() -> None:
    """Render the Thermal Loss Analysis page."""
    st.markdown("## 🌡️ Thermal Loss Analysis")
    st.caption("Module vs ambient temperature and estimated thermal derating.")

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

    col1, col2, col3 = st.columns(3)
    with col1:
        name = st.selectbox("Plant", list(plant_map.keys()))
    with col2:
        days = st.selectbox("Period (days)", [30, 60, 90, 180, 365], index=1)
    with col3:
        gamma = st.slider(
            "Temp coefficient (%/°C)",
            min_value=-0.6,
            max_value=-0.2,
            value=-0.4,
            step=0.05,
            help="Typical c-Si modules: −0.35 to −0.45 %/°C",
        )

    # ── Run engine ───────────────────────────────────────────────────
    end = datetime.utcnow()
    start = end - timedelta(days=int(days))

    with st.spinner("Running thermal loss analysis…"):
        result = ThermalLossEngine().run(
            plant_map[name], start, end, gamma_pct_per_c=gamma,
        )

    if not result.has_data:
        st.warning("No data available for the selected period.")
        for w in result.warnings:
            st.caption(f"⚠ {w}")
        return

    # ── KPI metrics ──────────────────────────────────────────────────
    s = result.summary
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Avg Module Temp", f"{s.get('avg_module_temp_c', 0):.1f} °C")
    k2.metric("Avg Ambient Temp", f"{s.get('avg_ambient_temp_c', 0):.1f} °C")
    k3.metric("Avg ΔT", f"{s.get('avg_delta_c', 0):.1f} °C")
    k4.metric("Estimated Loss", f"{s.get('estimated_thermal_loss_pct', 0):.1f} %")

    add_to_report_button(
        content={
            "Avg Module °C": s.get("avg_module_temp_c"),
            "Avg Ambient °C": s.get("avg_ambient_temp_c"),
            "Avg ΔT °C": s.get("avg_delta_c"),
            "Loss %": s.get("estimated_thermal_loss_pct"),
        },
        title=f"Thermal KPIs – {name}",
        item_type="kpi",
        description="Temperature statistics and estimated thermal loss",
        source_page="Thermal Loss",
        button_key=f"thermal_kpi_{name}".replace(" ", "_"),
    )

    if result.warnings:
        with st.expander("Warnings"):
            for w in result.warnings:
                st.caption(f"⚠ {w}")

    # ── Temperature timeseries chart ─────────────────────────────────
    ts = result.timeseries
    if ts is not None and not ts.empty:
        ts_col = ts.columns[0]  # first column is the timestamp

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=ts[ts_col], y=ts["module_temp_c"],
            mode="lines", name="Module Temp",
            line=dict(color="#c62828", width=1.5),
        ))
        fig.add_trace(go.Scatter(
            x=ts[ts_col], y=ts["ambient_temp_c"],
            mode="lines", name="Ambient Temp",
            line=dict(color="#1565c0", width=1.5),
        ))
        apply_analysis_template(fig, title="Module vs Ambient Temperature")
        fig.update_yaxes(title_text="Temperature (°C)")
        st.plotly_chart(fig, use_container_width=True)

        add_to_report_button(
            content=fig,
            title=f"Thermal Temps – {name}",
            item_type="chart",
            description="Module and ambient temperature timeseries",
            source_page="Thermal Loss",
            button_key=f"thermal_temp_chart_{name}".replace(" ", "_"),
        )

        # ── Thermal loss % timeseries ────────────────────────────────
        if "thermal_loss_pct" in ts.columns:
            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(
                x=ts[ts_col], y=ts["thermal_loss_pct"],
                mode="lines", name="Thermal Loss %",
                line=dict(color="#ff8f00", width=1.5),
                fill="tozeroy", fillcolor="rgba(255,143,0,0.15)",
            ))
            apply_analysis_template(fig2, title="Thermal Loss Over Time")
            fig2.update_yaxes(title_text="Loss (%)")
            st.plotly_chart(fig2, use_container_width=True)

            add_to_report_button(
                content=fig2,
                title=f"Thermal Loss % – {name}",
                item_type="chart",
                description="Instantaneous thermal loss percentage",
                source_page="Thermal Loss",
                button_key=f"thermal_loss_chart_{name}".replace(" ", "_"),
            )

        # ── Data table ───────────────────────────────────────────────
        with st.expander("Timeseries data table"):
            st.dataframe(ts, use_container_width=True, hide_index=True)
            add_to_report_button(
                content=ts,
                title=f"Thermal Data – {name}",
                item_type="table",
                description="Temperature and thermal loss timeseries",
                source_page="Thermal Loss",
                button_key=f"thermal_table_{name}".replace(" ", "_"),
            )

    st.caption(f"Calculation took {result.calculation_seconds:.2f} s")
