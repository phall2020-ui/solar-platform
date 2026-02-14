"""Loss Waterfall – thin Streamlit renderer."""
from __future__ import annotations

from datetime import datetime, timedelta

import plotly.graph_objects as go
import streamlit as st

from components.report_button import add_to_report_button
from services.analysis.chart_templates import ANALYSIS_COLORS, apply_analysis_template
from services.analysis.waterfall import LossWaterfallEngine
from services.database.repository import PlantRepository

# Icons for each loss category
_ICONS = {
    "clipping": "⚡",
    "curtailment": "🚫",
    "shading": "🌑",
    "fouling": "🧹",
    "thermal": "🌡️",
}


def render() -> None:
    """Render the Loss Waterfall page."""
    st.markdown("## 📊 Loss Waterfall")
    st.caption("Aggregated loss breakdown across all analysis engines.")

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

    with st.spinner("Running all loss engines…"):
        result = LossWaterfallEngine().run(plant_map[name], start, end)

    if not result.has_data:
        st.warning("No data available for the selected period.")
        for w in result.warnings:
            st.caption(f"⚠ {w}")
        return

    # ── KPI metrics ──────────────────────────────────────────────────
    s = result.summary
    total_loss = s.get("total_estimated_loss_pct", 0)
    largest = s.get("largest_loss_component", "—")

    k1, k2 = st.columns(2)
    k1.metric("Total Estimated Loss", f"{total_loss:.1f} %")
    k2.metric("Largest Component", f"{_ICONS.get(largest, '')} {largest}")

    add_to_report_button(
        content={"Total Loss %": total_loss, "Largest Component": largest},
        title=f"Loss Waterfall KPIs – {name}",
        item_type="kpi",
        description="Total aggregated loss and dominant component",
        source_page="Loss Waterfall",
        button_key=f"waterfall_kpi_{name}".replace(" ", "_"),
    )

    if result.warnings:
        with st.expander(f"Warnings ({len(result.warnings)})"):
            for w in result.warnings:
                st.caption(f"⚠ {w}")

    # ── Waterfall chart ──────────────────────────────────────────────
    losses = result.losses or {}
    table = result.table

    if table is not None and not table.empty:
        # Build Plotly waterfall
        labels = [f"{_ICONS.get(r['loss_type'], '')} {r['loss_type']}" for _, r in table.iterrows()]
        values = [round(r["loss_pct"], 2) for _, r in table.iterrows()]

        fig = go.Figure(go.Waterfall(
            name="Loss",
            orientation="v",
            measure=["relative"] * len(values) + ["total"],
            x=labels + ["Total"],
            y=values + [0],  # total is auto-computed
            connector=dict(line=dict(color="rgba(0,0,0,0.3)", width=1)),
            increasing=dict(marker=dict(color=ANALYSIS_COLORS["negative"])),
            decreasing=dict(marker=dict(color=ANALYSIS_COLORS["positive"])),
            totals=dict(marker=dict(color=ANALYSIS_COLORS["primary"])),
            textposition="outside",
            text=[f"{v:.1f}%" for v in values] + [f"{total_loss:.1f}%"],
        ))
        apply_analysis_template(fig, title=f"Loss Breakdown – {name}")
        fig.update_yaxes(title_text="Loss (%)")
        st.plotly_chart(fig, use_container_width=True)

        add_to_report_button(
            content=fig,
            title=f"Loss Waterfall Chart – {name}",
            item_type="chart",
            description="Waterfall breakdown of all loss categories",
            source_page="Loss Waterfall",
            button_key=f"waterfall_chart_{name}".replace(" ", "_"),
        )

        # ── Horizontal bar (alternate view) ──────────────────────────
        with st.expander("Horizontal bar view"):
            fig_bar = go.Figure(go.Bar(
                y=[f"{_ICONS.get(r['loss_type'], '')} {r['loss_type']}" for _, r in table.iterrows()],
                x=[r["loss_pct"] for _, r in table.iterrows()],
                orientation="h",
                marker_color=ANALYSIS_COLORS["negative"],
                text=[f"{r['loss_pct']:.1f}%" for _, r in table.iterrows()],
                textposition="outside",
            ))
            apply_analysis_template(fig_bar, title="Loss Categories (sorted)")
            fig_bar.update_xaxes(title_text="Loss (%)")
            st.plotly_chart(fig_bar, use_container_width=True)

        # ── Data table ───────────────────────────────────────────────
        with st.expander("Loss breakdown table"):
            display = table.copy()
            display["loss_pct"] = display["loss_pct"].round(2)
            display.columns = ["Loss Type", "Loss (%)"]
            st.dataframe(display, use_container_width=True, hide_index=True)
            add_to_report_button(
                content=display,
                title=f"Loss Breakdown Table – {name}",
                item_type="table",
                description="All loss categories sorted by magnitude",
                source_page="Loss Waterfall",
                button_key=f"waterfall_table_{name}".replace(" ", "_"),
            )

    st.caption(f"Calculation took {result.calculation_seconds:.2f} s")
