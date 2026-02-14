"""
Plant detail view with tabbed interface.

Each tab delegates to a function that only uses the service layer.
No direct database queries — everything goes through PlantService.

DESIGN NOTES FOR EXTRACTION:
- When moving to React, each tab becomes a route: /plants/{uid}/overview, etc.
- Service layer stays unchanged
"""
import streamlit as st
from datetime import datetime, timedelta

from components.kpi_cards import render_kpi_row, render_status_badge
from services.plant_service import PlantService


def render():
    """Render plant detail view (entry point from page registry)."""
    render_plant_detail()


def render_plant_detail():
    """Render plant detail view."""
    # Get selected plant from session state
    plant_uid = st.session_state.get("selected_plant_uid")
    if not plant_uid:
        st.warning("No plant selected. Go to Dashboard and click on a plant to view details.")
        if st.button("← Back to Dashboard"):
            st.session_state["current_page"] = "Dashboard"
            st.rerun()
        return

    service = PlantService()
    plant = service.get_plant(plant_uid)

    if not plant:
        st.error(f"Plant not found: {plant_uid}")
        if st.button("← Back to Dashboard"):
            st.session_state["current_page"] = "Dashboard"
            st.rerun()
        return

    # Back button
    if st.button("← Back to Dashboard"):
        st.session_state.pop("selected_plant_uid", None)
        st.session_state["current_page"] = "Dashboard"
        st.rerun()

    # Header
    name = plant.get("alias", plant.get("name", "Unknown Plant"))
    st.title(f"☀️ {name}")

    pr = plant.get("current_pr")
    status = _get_status(pr)
    status_icon = {"excellent": "🟢", "good": "🟢", "warning": "🟡", "critical": "🔴", "offline": "⚫"}.get(status, "⚪")

    col_status, col_info = st.columns([1, 3])
    with col_status:
        render_status_badge(status)
    with col_info:
        capacity = plant.get("dc_size_kw", 0)
        cap_str = f" | Capacity: {capacity/1000:.1f} MWp" if capacity else ""
        pr_str = f" | PR: {pr:.1f}%" if pr else ""
        st.caption(f"UID: {plant_uid}{cap_str}{pr_str}")

    st.divider()

    # Tabs
    tab_overview, tab_production, tab_environmental, tab_devices, tab_history = st.tabs(
        ["📊 Overview", "⚡ Production", "🌤️ Environmental", "🔌 Devices", "📜 History"]
    )

    with tab_overview:
        _render_overview(service, plant_uid)

    with tab_production:
        _render_production(service, plant_uid)

    with tab_environmental:
        _render_environmental(service, plant_uid)

    with tab_devices:
        _render_devices(service, plant_uid)

    with tab_history:
        _render_history(service, plant_uid)


def _render_overview(service: PlantService, plant_uid: str):
    """Plant overview tab with KPIs."""
    summary = service.get_daily_summary(plant_uid)

    render_kpi_row([
        {
            "label": "Today's Generation",
            "value": f"{summary.get('today_mwh', 0):.1f} MWh",
            "icon": "⚡",
            "status": "good",
        },
        {
            "label": "Current Power",
            "value": f"{summary.get('current_kw', 0):.0f} kW",
            "icon": "🔌",
            "status": "good",
        },
        {
            "label": "Performance Ratio",
            "value": f"{summary.get('pr', 0):.1f}%",
            "icon": "📊",
            "status": _get_status(summary.get("pr")),
        },
        {
            "label": "Availability",
            "value": f"{summary.get('availability', 0):.1f}%",
            "icon": "✅",
            "status": "good" if summary.get("availability", 0) >= 98 else "warning",
        },
    ])


def _render_production(service: PlantService, plant_uid: str):
    """Production tab — charts and data."""
    st.subheader("Production Data")
    days = st.selectbox("Time range", [7, 14, 30, 90], index=1, format_func=lambda d: f"Last {d} days")
    df = service.get_production_data(plant_uid, days=days)
    if df.empty:
        st.info("No production data available for this period.")
    else:
        st.dataframe(df, use_container_width=True)
    st.caption("For detailed analysis, use Clipping Analysis or Curtailment Analysis modules.")


def _render_environmental(service: PlantService, plant_uid: str):
    """Environmental tab — irradiance, temperature, wind."""
    st.subheader("Environmental Data")
    st.info("🌤️ Environmental data — irradiance, temperature, and wind readings will be displayed here.")
    st.caption("Detailed environmental analysis is available in the Shading and Thermal Loss modules.")


def _render_devices(service: PlantService, plant_uid: str):
    """Devices tab — inverters, meters, sensors."""
    st.subheader("Registered Devices")
    devices = service.get_devices(plant_uid)
    if not devices:
        st.info("No devices found for this plant.")
        return

    for device in devices:
        cols = st.columns([2, 1])
        with cols[0]:
            st.markdown(f"🔌 **{device['device_id']}**")
        with cols[1]:
            st.caption(device.get("type", "unknown"))


def _render_history(service: PlantService, plant_uid: str):
    """History tab — historical data explorer."""
    st.subheader("Historical Data")
    st.info("📜 Historical data explorer — browse past readings and events.")
    st.caption("Use Data Explorer for full database browsing capabilities.")


def _get_status(pr) -> str:
    """Map PR value to status string."""
    if pr is None:
        return "offline"
    if pr >= 85:
        return "excellent"
    if pr >= 70:
        return "good"
    if pr >= 50:
        return "warning"
    return "critical"
