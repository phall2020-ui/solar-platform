"""Plant Management — register, edit, and fetch data for solar sites."""
import json
import logging
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

from solar_platform.services.data_pull import JuggleDataPullService
from app.styles import render_alert, render_divider, render_section_header

logger = logging.getLogger(__name__)


def _get_service() -> JuggleDataPullService:
    """Lazily create and cache the data pull service."""
    return JuggleDataPullService()


def render():
    """Render the Plant Management & Data Fetch page."""
    logger.info("Rendering Plant Management page")
    st.title("🌱 Plant Management")
    st.markdown("Manage sites and fetch operational data.")

    svc = _get_service()

    # --- Pre-computation ---
    plant_list = svc.get_registered_plants()
    plant_aliases = [p["alias"] for p in plant_list]

    # --- Section 1: Check for New Plants ---
    with st.expander("🔍 Check for New Plants", expanded=True):
        col_btn, col_info = st.columns([1, 4])
        with col_btn:
            if st.button("🔄 Scan API for Updates", key="scan_api_btn", type="primary"):
                if not svc.api_key:
                    st.session_state["api_scan_results"] = []
                    st.session_state["api_scan_error"] = (
                        "No API key configured. Set JUGGLE_API_KEY or EMIG_API_KEY in your .env file."
                    )
                else:
                    try:
                        api_plants = svc.discover_plants()
                        st.session_state["api_scan_results"] = api_plants
                        st.session_state["api_scan_error"] = None
                    except Exception as e:
                        st.session_state["api_scan_results"] = []
                        st.session_state["api_scan_error"] = str(e)

        scan_results = st.session_state.get("api_scan_results", [])
        scan_error = st.session_state.get("api_scan_error")

        if scan_error:
            render_alert(f"API Error: {scan_error}", "error")

        # Identify New vs Registered
        registered_uids = [p["plant_uid"] for p in plant_list]
        new_plants = [p for p in scan_results if p.get("uid") not in registered_uids]

        with col_info:
            if scan_results:
                render_alert(
                    f"Found {len(scan_results)} total plants. {len(new_plants)} are new.",
                    "success",
                )
            elif "api_scan_results" in st.session_state:
                render_alert("No plants found in API.", "info")

        # --- Display New Plants ---
        if new_plants:
            render_section_header(f"Found {len(new_plants)} New Sites", icon="✨")
            st.markdown(
                "Please review and confirm details for each new site to add it to the database."
            )

            for i, np_item in enumerate(new_plants):
                with st.expander(
                    f"🆕 Found: {np_item.get('name', 'Unknown')} ({np_item['uid']})",
                    expanded=True,
                ):
                    with st.form(f"add_plant_form_{i}"):
                        col1, col2 = st.columns(2)
                        with col1:
                            new_alias = st.text_input(
                                "Alias (Short Name)",
                                value=np_item.get("name", ""),
                                key=f"new_alias_{i}",
                            )
                            _new_uid = st.text_input(
                                "Plant UID",
                                value=np_item["uid"],
                                disabled=True,
                                key=f"new_uid_{i}",
                            )
                        with col2:
                            new_inv_ids = st.text_area(
                                "Inverters",
                                value=", ".join(np_item.get("inverter_ids", [])),
                                key=f"new_inv_{i}",
                            )
                            new_poa = st.text_input(
                                "Weather / POA Device ID",
                                value=np_item.get("weather_id") or "",
                                key=f"new_poa_{i}",
                            )
                            new_dc = st.number_input(
                                "DC Size (kW)",
                                value=float(np_item.get("dc_size_kw") or 1000.0),
                                key=f"new_dc_{i}",
                            )

                        submit_add = st.form_submit_button("✅ Add to Database")

                        if submit_add:
                            try:
                                inv_list = [
                                    x.strip() for x in new_inv_ids.split(",") if x.strip()
                                ]
                                svc.register_plants_in_db(
                                    [
                                        {
                                            "uid": np_item["uid"],
                                            "name": new_alias,
                                            "api_name": np_item.get("api_name", new_alias),
                                            "inverter_ids": inv_list,
                                            "weather_id": new_poa or None,
                                            "dc_size_kw": new_dc,
                                        }
                                    ]
                                )
                                logger.info(
                                    "Plant added: alias=%s, uid=%s", new_alias, np_item["uid"]
                                )
                                st.toast(f"Plant {new_alias} added successfully!")
                                st.rerun()
                            except Exception as e:
                                logger.error("Failed to add plant %s: %s", new_alias, e)
                                st.error(f"Error saving plant: {e}")

    render_divider()

    # --- Manage & Update Data ---
    render_section_header("Managed Sites & Data", icon="📋")

    tab_list, tab_update = st.tabs(["Registered Sites", "Bulk Data Update"])

    with tab_list:
        if not plant_list:
            render_alert("No sites registered yet. Use 'Scan API for Updates' above to discover sites.", "info")
        else:
            display_rows = []
            for p in plant_list:
                inv_ids = p.get("inverter_ids", [])
                display_rows.append(
                    {
                        "Alias": p["alias"],
                        "UID": p["plant_uid"],
                        "DC Size (kW)": p.get("dc_size_kw"),
                        "Inverters": len(inv_ids) if isinstance(inv_ids, list) else 0,
                        "Weather ID": p.get("weather_id") or "—",
                    }
                )
            st.dataframe(
                pd.DataFrame(display_rows),
                use_container_width=True,
                hide_index=True,
            )

            with st.expander("✏️ Edit Selected Site"):
                edit_plant_alias = st.selectbox(
                    "Select Site", options=["-- Select --"] + plant_aliases
                )
                if edit_plant_alias != "-- Select --":
                    edit_plant = next(
                        (p for p in plant_list if p["alias"] == edit_plant_alias), None
                    )
                    if edit_plant:
                        with st.form("edit_existing_form"):
                            e_alias = st.text_input("Alias", edit_plant["alias"])
                            e_uid = st.text_input("UID", edit_plant["plant_uid"], disabled=True)
                            inv_ids = edit_plant.get("inverter_ids", [])
                            if isinstance(inv_ids, str):
                                inv_display = inv_ids
                            else:
                                inv_display = ", ".join(inv_ids)
                            e_inv = st.text_area("Inverters", inv_display)
                            e_poa = st.text_input(
                                "Weather / POA ID",
                                edit_plant.get("weather_id", "") or "",
                            )
                            e_dc = st.number_input(
                                "DC Size (kW)",
                                value=float(edit_plant.get("dc_size_kw") or 0),
                            )

                            if st.form_submit_button("Update Site"):
                                inv_list = [
                                    x.strip() for x in e_inv.split(",") if x.strip()
                                ]
                                svc.register_plants_in_db(
                                    [
                                        {
                                            "uid": edit_plant["plant_uid"],
                                            "name": e_alias,
                                            "api_name": edit_plant.get("api_name", e_alias),
                                            "inverter_ids": inv_list,
                                            "weather_id": e_poa or None,
                                            "dc_size_kw": e_dc,
                                        }
                                    ]
                                )
                                logger.info(
                                    "Plant updated: alias=%s, uid=%s",
                                    e_alias,
                                    edit_plant["plant_uid"],
                                )
                                st.toast(f"Plant {e_alias} updated!")
                                st.rerun()

    with tab_update:
        st.write("Fetch operational data from the API.")

        if not svc.api_key:
            st.error(
                "**No API key configured.** Set `JUGGLE_API_KEY` or `EMIG_API_KEY` "
                "in your `.env` file or environment variables."
            )
            return

        update_mode = st.radio(
            "Update Mode",
            ["Bulk Smart Update (Recommended)", "Selective Fetch"],
            horizontal=True,
        )

        if update_mode == "Bulk Smart Update (Recommended)":
            render_alert(
                "Updates ALL registered sites. Fetches data for the specified date range.",
                "info",
            )

            col_d1, col_d2 = st.columns(2)
            manual_start = col_d1.date_input(
                "Start Date", value=datetime.today() - timedelta(days=30)
            )
            manual_end = col_d2.date_input(
                "End Date", value=datetime.today() - timedelta(days=1)
            )

            if st.button("🔄 Update All Data", type="primary"):
                if not plant_list:
                    render_alert("No plants registered.", "warning")
                else:
                    progress_bar = st.progress(0)
                    status_log = st.empty()
                    results = []
                    s_str = manual_start.strftime("%Y%m%d")
                    e_str = manual_end.strftime("%Y%m%d")

                    for i, p in enumerate(plant_list):
                        alias = p["alias"]
                        uid = p["plant_uid"]
                        status_log.write(f"Processing {alias}...")

                        try:
                            result = svc.pull_plant(
                                plant_uid=uid,
                                alias=alias,
                                inverter_ids=p.get("inverter_ids", []),
                                weather_id=p.get("weather_id"),
                                start_date=s_str,
                                end_date=e_str,
                            )
                            if result.success:
                                results.append(
                                    f"✅ {alias}: {result.readings_stored} readings stored"
                                )
                            else:
                                results.append(
                                    f"❌ {alias}: {'; '.join(result.errors)}"
                                )
                        except Exception as e:
                            logger.error("Bulk fetch failed for %s: %s", alias, e)
                            results.append(f"❌ {alias}: Error - {e}")

                        progress_bar.progress((i + 1) / len(plant_list))

                    status_log.empty()
                    render_alert("Update Complete!", "success")
                    with st.expander("Update Report", expanded=True):
                        for r in results:
                            st.write(r)

        else:
            render_alert(
                "Manually select sites and date ranges. This forces a fetch for the specified period.",
                "warning",
            )
            sel_plants = st.multiselect(
                "Select Sites",
                options=plant_aliases,
                default=plant_aliases[:1] if plant_aliases else None,
            )
            c1, c2 = st.columns(2)
            sel_start = c1.date_input(
                "Start Date", value=datetime.today() - timedelta(days=7)
            )
            sel_end = c2.date_input(
                "End Date", value=datetime.today() - timedelta(days=1)
            )

            if st.button("📥 Fetch Data"):
                if not sel_plants:
                    render_alert("Please select at least one site.", "error")
                else:
                    s_str = sel_start.strftime("%Y%m%d")
                    e_str = sel_end.strftime("%Y%m%d")

                    progress = st.progress(0)
                    status = st.empty()

                    for i, alias in enumerate(sel_plants):
                        status.write(f"Fetching {alias}...")
                        p = next(
                            (x for x in plant_list if x["alias"] == alias), None
                        )
                        if p:
                            try:
                                result = svc.pull_plant(
                                    plant_uid=p["plant_uid"],
                                    alias=alias,
                                    inverter_ids=p.get("inverter_ids", []),
                                    weather_id=p.get("weather_id"),
                                    start_date=s_str,
                                    end_date=e_str,
                                )
                                if result.success:
                                    st.toast(
                                        f"✅ {alias}: {result.readings_stored} readings"
                                    )
                                else:
                                    st.error(
                                        f"Failed {alias}: {'; '.join(result.errors)}"
                                    )
                            except Exception as e:
                                logger.error(
                                    "Selective fetch failed for %s: %s", alias, e
                                )
                                st.error(f"Failed to fetch {alias}: {e}")
                        progress.progress((i + 1) / len(sel_plants))
                    status.empty()
                    render_alert("Selective fetch complete.", "success")
