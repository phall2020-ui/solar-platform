"""Plant Management (Legacy Wrapper)."""
import logging
import os
import sys
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

from solar_platform.services import legacy_toolkit
from styles import render_alert, render_divider, render_section_header

logger = logging.getLogger(__name__)

def render():
    """Render the legacy Plant Management & Data Fetch page."""
    logger.info("Rendering Plant Management page")
    orch = legacy_toolkit.get_orchestrator()
    if not orch:
        st.error("Orchestrator not available.")
        return

    # --- Pre-computation (Legacy Global) ---
    plant_list = orch.get_plants()
    plant_aliases = [p['alias'] for p in plant_list]

    st.title("🌱 Plant Management")
    st.markdown("Manage sites and fetch operational data.")

    # --- Section 1: Plants & Data Fetch Content ---
    
    # Initialize API client for plant discovery
    @st.cache_data(ttl=300)  # Cache for 5 minutes
    def fetch_api_plants():
        """Fetch plants from EMIG API."""
        try:
            # Add repo root to path for local imports if needed
            repo_root = os.path.dirname(legacy_toolkit.toolkit_path) # Assumes structure
            if repo_root not in sys.path:
                sys.path.insert(0, repo_root)
                
            # Try importing from package first
            try:
                from solar_toolkit.juggle_crawler import EmigApiClient
            except ImportError:
                # Fallback to direct path
                from juggle_crawler import EmigApiClient
            
            from solar_toolkit.config import settings as tk_settings
            api_key = tk_settings.JUGGLE_API_KEY or tk_settings.EMIG_API_KEY
            if not api_key:
                return [], "API key not configured"
            
            client = EmigApiClient(api_key)
            raw_plants = client.get_plant_list()
            
            # Enrich with device details
            plants_with_details = []
            for p in raw_plants:
                uid = p.get('uid') or p.get('id') or p.get('plantUID')
                name = p.get('name') or p.get('plantName') or "Unknown"
                if uid:
                    details = client.get_plant_details(uid)
                    meters = details.get('meters', [])
                    inverters = [m.get('emigId') for m in meters if m.get('type') == 'INVERTER']
                    plants_with_details.append({
                        'uid': uid,
                        'name': name,
                        'inverter_ids': inverters,
                        'inverter_count': len(inverters)
                    })
            return plants_with_details, None
        except Exception as e:
            return [], str(e)

    # --- Check for New Plants ---
    with st.expander("🔍 Check for New Plants", expanded=True):
        col_btn, col_info = st.columns([1, 4])
        with col_btn:
            if st.button("🔄 Scan API for Updates", key="scan_api_btn", type="primary"):
                st.cache_data.clear()
                # Fetch and store in session state
                api_plants, api_error = fetch_api_plants()
                st.session_state['api_scan_results'] = api_plants
                st.session_state['api_scan_error'] = api_error
                
        scan_results = st.session_state.get('api_scan_results', [])
        scan_error = st.session_state.get('api_scan_error')
        
        if scan_error:
            render_alert(f"API Error: {scan_error}", "error")
        
        # Identify New vs Registered
        registered_uids = [p['plant_uid'] for p in plant_list]
        new_plants = [p for p in scan_results if p['uid'] not in registered_uids]
        
        with col_info:
            if scan_results:
                render_alert(f"Found {len(scan_results)} total plants. {len(new_plants)} are new.", "success")
            elif 'api_scan_results' in st.session_state:
                render_alert("No plants found in API.", "info")

        # --- Display New Plants ---
        if new_plants:
            render_section_header(f"Found {len(new_plants)} New Sites", icon="✨")
            st.markdown("Please review and confirm details for each new site to add it to the database.")
            
            for i, np in enumerate(new_plants):
                with st.expander(f"🆕 Found: {np['name']} ({np['uid']})", expanded=True):
                    with st.form(f"add_plant_form_{i}"):
                        col1, col2 = st.columns(2)
                        with col1:
                            new_alias = st.text_input("Alias (Short Name)", value=np['name'], key=f"new_alias_{i}")
                            _new_uid = st.text_input("Plant UID", value=np['uid'], disabled=True, key=f"new_uid_{i}")
                        with col2:
                            new_inv_ids = st.text_area("Inverters", value=", ".join(np['inverter_ids']), key=f"new_inv_{i}")
                            new_poa = st.text_input("POA Device ID", placeholder="Optional (e.g. POA:SITE)", key=f"new_poa_{i}")
                            new_dc = st.number_input("DC Size (kW)", value=1000.0, key=f"new_dc_{i}")
                        
                        submit_add = st.form_submit_button("✅ Add to Database")
                        
                        if submit_add:
                            try:
                                inv_list = [x.strip() for x in new_inv_ids.split(',')]
                                orch.save_plant(new_alias, np['uid'], inv_list, new_poa if new_poa else None, new_dc)
                                logger.info("Plant added: alias=%s, uid=%s", new_alias, np['uid'])
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
            render_alert("No sites registered yet.", "info")
        else:
            reg_df = pd.DataFrame(plant_list)
            st.dataframe(
                reg_df[['alias', 'plant_uid', 'dc_size_kw']].rename(columns={'alias':'Alias', 'plant_uid':'UID', 'dc_size_kw':'DC Size'}),
                use_container_width=True,
                hide_index=True
            )
            
            with st.expander("✏️ Edit Selected Site"):
                 edit_plant_alias = st.selectbox("Select Site", options=["-- Select --"] + plant_aliases)
                 if edit_plant_alias != "-- Select --":
                    edit_plant = next((p for p in plant_list if p['alias'] == edit_plant_alias), None)
                    if edit_plant:
                         with st.form("edit_existing_form"):
                            e_alias = st.text_input("Alias", edit_plant['alias'])
                            e_uid = st.text_input("UID", edit_plant['plant_uid'])
                            e_inv = st.text_area("Inverters", ", ".join(edit_plant.get('inverter_ids', [])))
                            e_poa = st.text_input("POA ID", edit_plant.get('weather_id', ''))
                            e_dc = st.number_input("DC Size", value=float(edit_plant.get('dc_size_kw', 0)))
                            
                            if st.form_submit_button("Update Site"):
                                logger.info("Plant updated: alias=%s, uid=%s", e_alias, e_uid)
                                orch.save_plant(e_alias, e_uid, e_inv.split(','), e_poa, e_dc)
                                st.rerun()
                                
    with tab_update:
        st.write("Fetch operational data from the API.")
        
        update_mode = st.radio("Update Mode", ["Bulk Smart Update (Recommended)", "Selective Fetch"], horizontal=True)
        
        if update_mode == "Bulk Smart Update (Recommended)":
            render_alert("Updates ALL registered sites. Automatically detects latest data timestamp for each site and appends new data.", "info")
            
            col_d1, col_d2 = st.columns(2)
            manual_start = col_d1.date_input("Default Start Date", value=datetime.today() - timedelta(days=30))
            manual_end = col_d2.date_input("End Date (All Sites)", value=datetime.today() - timedelta(days=1))
            
            if st.button("🔄 Update All Data", type="primary"):
                progress_bar = st.progress(0)
                status_log = st.empty()
                results = []
                
                for i, p in enumerate(plant_list):
                    alias = p['alias']
                    uid = p['plant_uid']
                    status_log.write(f"Processing {alias}...")
                    
                    last_ts = orch.get_latest_data_timestamp(uid)
                    if last_ts:
                        try:
                            last_dt = pd.to_datetime(last_ts).date()
                            start_fetch = last_dt + timedelta(days=1)
                        except (ValueError, TypeError):
                            start_fetch = manual_start
                    else:
                        start_fetch = manual_start
                    
                    if start_fetch > manual_end:
                        results.append(f"✅ {alias}: Up to date (Last: {last_ts})")
                    else:
                        try:
                            s_str = start_fetch.strftime("%Y%m%d")
                            e_str = manual_end.strftime("%Y%m%d")
                            count = orch.fetch_data(uid, s_str, e_str)
                            logger.info("Bulk fetch: %s (%s–%s) -> %s readings", alias, s_str, e_str, count)
                            results.append(f"✅ {alias}: Fetched {count} readings ({s_str}-{e_str})")
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
            render_alert("Manually select sites and date ranges. This forces a fetch for the specified period.", "warning")
            sel_plants = st.multiselect("Select Sites", options=plant_aliases, default=plant_aliases[:1] if plant_aliases else None)
            c1, c2 = st.columns(2)
            sel_start = c1.date_input("Start Date", value=datetime.today() - timedelta(days=7))
            sel_end = c2.date_input("End Date", value=datetime.today() - timedelta(days=1))
            
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
                        p = next((x for x in plant_list if x['alias'] == alias), None)
                        if p:
                            try:
                                count = orch.fetch_data(p['plant_uid'], s_str, e_str)
                                logger.info("Selective fetch: %s -> %s readings", alias, count)
                                st.toast(f"✅ {alias}: {count} readings fetched")
                            except Exception as e:
                                logger.error("Selective fetch failed for %s: %s", alias, e)
                                st.error(f"Failed to fetch {alias}: {e}")
                        progress.progress((i + 1) / len(sel_plants))
                    status.empty()
                    render_alert("Selective fetch complete.", "success")
