"""
Portfolio map view — geographic display of all plants.

Uses streamlit-folium for interactive map with:
- Status-colored markers per plant
- Popup with plant KPIs
- Cluster view for zoomed-out portfolio overview

Falls back gracefully if folium/streamlit-folium not installed.

DESIGN NOTES FOR EXTRACTION:
- When moving to React, replace with Mapbox GL JS or Leaflet
"""
import streamlit as st

from solar_platform.services.portfolio import PortfolioService


STATUS_MARKER_COLORS = {
    "excellent": "green",
    "good": "blue",
    "warning": "orange",
    "critical": "red",
    "offline": "gray",
}


def render():
    """Entry point from page registry."""
    render_portfolio_map()


def render_portfolio_map():
    """Render geographic map of all plants."""
    st.title("🗺️ Portfolio Map")

    # Check if folium is available
    try:
        import folium
        from streamlit_folium import st_folium
        from folium.plugins import MarkerCluster
        _HAS_FOLIUM = True
    except ImportError:
        _HAS_FOLIUM = False

    portfolio = PortfolioService()
    plants = portfolio.get_plant_statuses("Last 24 Hours")

    if not plants:
        st.info("No plants found. Add plants in Plant Management.")
        return

    # Filter plants with coordinates
    plants_with_coords = [p for p in plants if p.get("lat") and p.get("lng")]

    if not _HAS_FOLIUM:
        st.warning(
            "Map view requires `folium` and `streamlit-folium`. "
            "Install with: `pip install folium streamlit-folium`"
        )
        # Fallback: show plant list with coordinates
        st.subheader("Plant Locations")
        for plant in plants:
            lat = plant.get("lat")
            lng = plant.get("lng")
            loc = f"({lat:.4f}, {lng:.4f})" if lat and lng else "No coordinates"
            status_icon = {"excellent": "🟢", "good": "🟢", "warning": "🟡", "critical": "🔴", "offline": "⚫"}.get(
                plant["status"], "⚪"
            )
            st.markdown(f"{status_icon} **{plant['name']}** — {loc}")
        return

    if not plants_with_coords:
        st.warning("No plants have geographic coordinates. Add lat/lng in Plant Management.")
        return

    # Calculate map center from plant coordinates
    center_lat = sum(p["lat"] for p in plants_with_coords) / len(plants_with_coords)
    center_lng = sum(p["lng"] for p in plants_with_coords) / len(plants_with_coords)

    # Create map
    m = folium.Map(
        location=[center_lat, center_lng],
        zoom_start=6,
        tiles="CartoDB positron",
    )
    cluster = MarkerCluster()

    for plant in plants_with_coords:
        pr_str = f"{plant.get('pr', 0):.1f}%" if plant.get("pr") is not None else "N/A"
        gen_str = f"{plant.get('generation_mwh', 0):.1f} MWh"

        popup_html = f"""
        <div style="font-family: 'Inter', sans-serif; min-width: 180px;">
            <h4 style="margin: 0 0 8px 0; color: #1B4D5C;">{plant['name']}</h4>
            <table style="font-size: 13px;">
                <tr><td><b>Status:</b></td><td>{plant['status'].title()}</td></tr>
                <tr><td><b>PR:</b></td><td>{pr_str}</td></tr>
                <tr><td><b>Generation:</b></td><td>{gen_str}</td></tr>
            </table>
        </div>
        """

        folium.Marker(
            location=[plant["lat"], plant["lng"]],
            popup=folium.Popup(popup_html, max_width=250),
            icon=folium.Icon(
                color=STATUS_MARKER_COLORS.get(plant["status"], "gray"),
                icon="sun-o",
                prefix="fa",
            ),
        ).add_to(cluster)

    cluster.add_to(m)

    st.caption(f"Showing {len(plants_with_coords)} of {len(plants)} plants with coordinates")
    st_folium(m, width=None, height=600)

    # Summary table below map
    st.divider()
    st.subheader("Plant Summary")
    import pandas as pd
    summary_data = []
    for p in plants:
        summary_data.append({
            "Plant": p["name"],
            "Status": p["status"].title(),
            "PR (%)": f"{p.get('pr', 0):.1f}" if p.get("pr") is not None else "—",
            "Generation (MWh)": f"{p.get('generation_mwh', 0):.1f}",
            "Coordinates": "✅" if p.get("lat") and p.get("lng") else "❌",
        })
    st.dataframe(pd.DataFrame(summary_data), use_container_width=True, hide_index=True)
