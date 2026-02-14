import sys, os
repo_root = os.path.dirname(__file__)
if repo_root not in sys.path: sys.path.insert(0, repo_root)

"""
Streamlit Web User Interface for Solar Toolkit.
Refactored from ui.py to use the central AnalysisOrchestrator.

To Run: streamlit run solar_toolkit/ui/app.py
"""
import streamlit as st
import pandas as pd
import os
import sys
import logging
import io
import tempfile
from datetime import datetime, timedelta
import altair as alt

# Import pipeline modules
try:
    # Assuming this script is run from the package root or the path is set
    from solar_toolkit.orchestrator import AnalysisOrchestrator
    from solar_toolkit.poa_bulk_importer import PREVIEW_LIMIT
    from solar_toolkit.config import settings
    from solar_toolkit.utils import setup_logging
    from solar_toolkit.data_viewer import DataViewer
    
    # Initialize the global logger instance
    logger = logging.getLogger("solar_toolkit")

except ImportError as e:
    st.error(f"Failed to import core modules. Please ensure all dependencies are installed and the package structure is correct. Error: {e}")
    st.stop()

# --- Setup ---
# Configure logging to capture output to a StringIO buffer
log_capture_string = io.StringIO()
# Use the package's logger but add the StreamHandler for capture
setup_logging(verbose=True, log_to_file=None)
capture_handler = logging.StreamHandler(log_capture_string)
capture_handler.setLevel(logging.INFO)
# Attach only to the main package logger or root logger
logging.getLogger("solar_toolkit").addHandler(capture_handler)
logging.getLogger().addHandler(capture_handler)


st.set_page_config(page_title="Solar Analytics Workbench", layout="wide", page_icon="âš¡")
st.title("âš¡ Solar Analytics Workbench")

# Initialize Orchestrator and state
@st.cache_resource
def get_orchestrator():
    """Initializes the Orchestrator (cached resource)."""
    return AnalysisOrchestrator(db_path=settings.DB_PATH)

orch = get_orchestrator()

def clear_logs():
    """Clears the captured log output."""
    log_capture_string.truncate(0)
    log_capture_string.seek(0)
    
def display_logs():
    """Displays the captured log output in an expander."""
    st.markdown("### ðŸ“œ Logs")
    with st.expander("Show Detailed Logs"):
        st.code(log_capture_string.getvalue())

# --- Sidebar for Plant Info ---
st.sidebar.header("Plant Registry")
plant_list = orch.get_plants()
plant_aliases = [p['alias'] for p in plant_list]

if not plant_aliases:
    st.sidebar.warning("No plants registered. Please use the 'Plants & Data Fetch' tab.")
    selected_alias = None
else:
    selected_alias = st.sidebar.selectbox("Select Plant", plant_aliases, key="selected_plant")
    
selected_plant = next((p for p in plant_list if p['alias'] == selected_alias), {})

if selected_plant:
    st.sidebar.markdown(f"**UID:** `{selected_plant.get('plant_uid')}`")
    st.sidebar.markdown(f"**DC Size:** `{selected_plant.get('dc_size_kw', 'N/A')} kW`")


# --- Main Application Tabs ---
tab_plants, tab_import, tab_fouling, tab_shading, tab_viewer = st.tabs([
    "Plants & Data Fetch", "POA Import", "Fouling Analysis", "Shading Analysis", "Database Viewer"
])


# --- TAB 1: Plants & Data Fetch (Combined) ---
with tab_plants:
    st.header("1. Plants & Data Fetch")
    
    # Initialize API client for plant discovery
    @st.cache_data(ttl=300)  # Cache for 5 minutes
    def fetch_api_plants():
        """Fetch plants from EMIG API."""
        try:
            import sys
            repo_root = os.path.dirname(__file__)
            if repo_root not in sys.path:
                sys.path.insert(0, repo_root)
            from juggle_crawler import EmigApiClient
            
            api_key = settings.JUGGLE_API_KEY or settings.EMIG_API_KEY
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
    
    # Create sub-sections
    col_discover, col_manage = st.columns([1, 1])
    
    with col_discover:
        st.subheader("🔍 Discover Plants from API")
        
        if st.button("🔄 Refresh API Plants", key="refresh_api"):
            st.cache_data.clear()
        
        api_plants, api_error = fetch_api_plants()
        
        if api_error:
            st.warning(f"Could not fetch from API: {api_error}")
        elif api_plants:
            st.success(f"Found {len(api_plants)} plants in API")
            
            # Display as selectable table
            api_df = pd.DataFrame(api_plants)
            api_df = api_df.rename(columns={
                'uid': 'Plant UID',
                'name': 'Plant Name',
                'inverter_count': 'Inverters'
            })
            
            # Callback to auto-populate registration form when plant is selected
            def on_api_plant_select():
                selection = st.session_state.get('api_plant_select', '-- Select --')
                if selection != "-- Select --":
                    selected_uid = selection.split("(")[-1].rstrip(")")
                    api_plant_info = next((p for p in api_plants if p['uid'] == selected_uid), None)
                    if api_plant_info:
                        # Set values directly on the form field keys so they update
                        st.session_state['reg_alias'] = api_plant_info['name']
                        st.session_state['reg_uid'] = api_plant_info['uid']
                        st.session_state['reg_inv_ids'] = ', '.join(api_plant_info['inverter_ids'])
            
            # Select plant from API - auto-populates form on selection
            selected_api_plant = st.selectbox(
                "Select plant to register/update",
                options=["-- Select --"] + [f"{p['name']} ({p['uid']})" for p in api_plants],
                key="api_plant_select",
                on_change=on_api_plant_select
            )
            
            # Show API plant details
            if selected_api_plant != "-- Select --":
                # Parse selection
                selected_uid = selected_api_plant.split("(")[-1].rstrip(")")
                api_plant_info = next((p for p in api_plants if p['uid'] == selected_uid), None)
                
                if api_plant_info:
                    st.markdown("**API Plant Details:**")
                    st.write(f"- UID: `{api_plant_info['uid']}`")
                    st.write(f"- Name: {api_plant_info['name']}")
                    st.write(f"- Inverters: {', '.join(api_plant_info['inverter_ids']) if api_plant_info['inverter_ids'] else 'None detected'}")
                    
                    # Check if already registered
                    existing = next((p for p in plant_list if p['plant_uid'] == api_plant_info['uid']), None)
                    if existing:
                        st.info(f"✅ Already registered as '{existing['alias']}'")
        else:
            st.info("Click 'Refresh API Plants' to discover available plants.")
    
    with col_manage:
        st.subheader("📝 Register / Edit Plant")
        
        # Form fields use session state keys directly - populated by API selection callback
        with st.form("register_form"):
            alias = st.text_input("Alias (Short Name/Key)", key="reg_alias")
            plant_uid = st.text_input("Plant UID (e.g., ERS:00001)", key="reg_uid")
            inverter_ids_str = st.text_area(
                "Inverter EMIG IDs (Comma Separated)", 
                help="e.g., INVERT:001, INVERT:002", 
                key="reg_inv_ids"
            )
            poa_id = st.text_input(
                "POA Device ID (for POA import)", 
                help="e.g., POA:SITENAME - Used to link SolarGIS POA data", 
                key="reg_poa_id"
            )
            dc_size_kw = st.number_input("DC Size (kW)", value=1000.0, min_value=1.0, key="reg_dc_size")
            
            submitted = st.form_submit_button("💾 Save Plant")
            
            if submitted:
                clear_logs()
                try:
                    if not alias or not plant_uid:
                        raise ValueError("Alias and Plant UID are required.")
                    
                    inverter_ids = [i.strip() for i in inverter_ids_str.split(',') if i.strip()] if inverter_ids_str else []
                    
                    # Save POA ID in place of weather_id (for compatibility with store)
                    orch.save_plant(alias, plant_uid, inverter_ids, poa_id if poa_id else None, dc_size_kw)
                    st.success(f"✅ Plant '{alias}' saved successfully!")
                    
                    # Set flag to show fetch section (form will be cleared on rerun)
                    st.session_state['show_fetch_for_plant'] = alias  # Track which plant was just saved
                    # Clear form fields for next entry
                    for key in ['reg_alias', 'reg_uid', 'reg_inv_ids', 'reg_poa_id']:
                        if key in st.session_state:
                            del st.session_state[key]
                    st.rerun()
                except Exception as e:
                    st.error(f"Error saving plant: {e}")
                finally:
                    display_logs()
    
    st.markdown("---")
    
    # --- Registered Plants Section ---
    st.subheader("📋 Registered Plants")
    
    if not plant_list:
        st.info("No plants registered yet. Use the form above to register plants from the API.")
    else:
        # Display registered plants in a table with edit capability
        reg_df = pd.DataFrame(plant_list)
        reg_df = reg_df.rename(columns={
            'alias': 'Alias',
            'plant_uid': 'Plant UID',
            'inverter_ids': 'Inverter IDs',
            'weather_id': 'POA ID',
            'dc_size_kw': 'DC Size (kW)'
        })
        # Format inverter IDs for display
        if 'Inverter IDs' in reg_df.columns:
            reg_df['Inverter IDs'] = reg_df['Inverter IDs'].apply(lambda x: ', '.join(x) if isinstance(x, list) else str(x))
        
        st.dataframe(reg_df, width='stretch', hide_index=True)
        
        # Edit existing plant
        with st.expander("✏️ Edit Existing Plant"):
            edit_plant_alias = st.selectbox(
                "Select plant to edit",
                options=["-- Select --"] + plant_aliases,
                key="edit_plant_select"
            )
            
            if edit_plant_alias != "-- Select --":
                edit_plant = next((p for p in plant_list if p['alias'] == edit_plant_alias), None)
                if edit_plant:
                    with st.form("edit_plant_form"):
                        edit_alias = st.text_input("Alias", value=edit_plant['alias'], key="edit_alias")
                        edit_uid = st.text_input("Plant UID", value=edit_plant['plant_uid'], key="edit_uid")
                        edit_inv = st.text_area(
                            "Inverter EMIG IDs (Comma Separated)",
                            value=', '.join(edit_plant.get('inverter_ids', [])) if isinstance(edit_plant.get('inverter_ids'), list) else '',
                            key="edit_inv_ids"
                        )
                        edit_poa = st.text_input("POA Device ID", value=edit_plant.get('weather_id', '') or '', key="edit_poa_id")
                        edit_dc = st.number_input("DC Size (kW)", value=float(edit_plant.get('dc_size_kw', 1000)), min_value=1.0, key="edit_dc_size")
                        
                        col_save, col_delete = st.columns(2)
                        save_edit = col_save.form_submit_button("💾 Update Plant")
                        delete_plant = col_delete.form_submit_button("🗑️ Delete Plant", type="secondary")
                        
                        if save_edit:
                            try:
                                inv_ids = [i.strip() for i in edit_inv.split(',') if i.strip()] if edit_inv else []
                                orch.save_plant(edit_alias, edit_uid, inv_ids, edit_poa if edit_poa else None, edit_dc)
                                st.success(f"✅ Plant '{edit_alias}' updated!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error updating plant: {e}")
                        
                        if delete_plant:
                            try:
                                orch.store.delete_plant(edit_plant_alias)
                                st.success(f"🗑️ Plant '{edit_plant_alias}' deleted.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error deleting plant: {e}")
    
    st.markdown("---")
    
    # --- Data Fetch Section ---
    st.subheader("📊 Fetch Operational Data")
    st.markdown("Download inverter readings from the EMIG API for registered plants.")
    
    # Check if a plant was just saved - show success message and highlight fetch section
    just_saved_plant = st.session_state.pop('show_fetch_for_plant', None)
    if just_saved_plant:
        st.success(f"✅ Plant '{just_saved_plant}' saved! You can now fetch data for it below.")
    
    # Check for registered plants
    if not plant_list:
        st.warning("No plants registered yet. Register a plant above first.")
    else:
        # Data source selection
        fetch_method = st.radio(
            "Data Source",
            ["API (Recommended)", "Web Crawler"],
            help="The EMIG API provides meter readings data. Web Crawler is available as a backup option.",
            horizontal=True
        )
        use_crawler = fetch_method == "Web Crawler"
        
        if use_crawler:
            if not settings.JUGGLE_USERNAME or not settings.JUGGLE_PASSWORD:
                st.warning("Crawler credentials missing. Please set `JUGGLE_USERNAME` and `JUGGLE_PASSWORD` in your environment or `.env` file.")
        else:
            if not settings.JUGGLE_API_KEY:
                st.warning("API key missing. Please set `JUGGLE_API_KEY` in your environment or `.env` file.")
        
        # Plant selection - single or all
        fetch_scope = st.radio(
            "Fetch Scope",
            ["Single Plant", "All Registered Plants"],
            horizontal=True
        )
        
        with st.form("data_fetch_form"):
            if fetch_scope == "Single Plant":
                # Pre-select the just-saved plant if applicable
                default_idx = 0
                if just_saved_plant and just_saved_plant in plant_aliases:
                    default_idx = plant_aliases.index(just_saved_plant)
                
                selected_fetch_plant = st.selectbox(
                    "Select Plant",
                    options=plant_aliases,
                    index=default_idx,
                    key="fetch_plant_select"
                )
                plants_to_fetch = [next(p for p in plant_list if p['alias'] == selected_fetch_plant)]
            else:
                st.info(f"Will fetch data for all {len(plant_list)} registered plants.")
                plants_to_fetch = plant_list
            
            col1, col2 = st.columns(2)
            start_date = col1.date_input("Start Date", value=datetime.today() - timedelta(days=30))
            end_date = col2.date_input("End Date", value=datetime.today() - timedelta(days=1))
            
            # Headless option for crawler
            headless = True
            if use_crawler:
                headless = st.checkbox("Run browser headless (no visible window)", value=True)
            
            submitted = st.form_submit_button("🚀 Fetch Data")
            
            if submitted:
                clear_logs()
                total_readings = 0
                results = {}
                
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                try:
                    start_str = start_date.strftime("%Y%m%d")
                    end_str = end_date.strftime("%Y%m%d")
                    
                    for i, plant in enumerate(plants_to_fetch):
                        plant_uid = plant['plant_uid']
                        plant_alias = plant['alias']
                        
                        status_text.text(f"Fetching {plant_alias} ({plant_uid})...")
                        progress_bar.progress((i + 1) / len(plants_to_fetch))
                        
                        try:
                            if use_crawler:
                                count = orch.fetch_data_crawl(
                                    plant_uid, 
                                    start_str, 
                                    end_str, 
                                    headless=headless
                                )
                            else:
                                # Fetch data directly to database (no temp CSV)
                                count = orch.fetch_data(plant_uid, start_str, end_str)
                            
                            results[plant_alias] = count
                            total_readings += count
                            
                        except Exception as e:
                            results[plant_alias] = f"Error: {str(e)}"
                            st.warning(f"Failed to fetch {plant_alias}: {e}")
                    
                    progress_bar.progress(1.0)
                    status_text.text("Fetch complete!")
                    
                    st.success(f"✅ Fetch complete! Total readings: {total_readings:,}")
                    
                    # Show results summary
                    st.markdown("**Results by Plant:**")
                    for alias, result in results.items():
                        if isinstance(result, int):
                            st.write(f"  ✓ {alias}: {result:,} readings")
                        else:
                            st.write(f"  ✗ {alias}: {result}")
                    
                except Exception as e:
                    st.error(f"Error during fetch: {e}")
                finally:
                    display_logs()

# --- TAB 2: POA Import ---
with tab_import:
    st.header("2. Import SolarGIS POA Data")
    st.markdown("""
    Import POA (Plane of Array) irradiance data from SolarGIS CSV files. 
    POA data covers the entire system and will be stored separately from inverter readings 
    but can be joined for analysis using aligned timestamps.
    """)
    
    # Create sub-tabs for single and bulk import
    import_mode = st.radio("Import Mode", ["Upload File(s)", "From Folder Path"], horizontal=True)
    
    if import_mode == "Upload File(s)":
        st.markdown("Upload one or more SolarGIS CSV files. Files will be auto-matched to registered plants based on filename.")
        
        # File uploader for POA data
        uploaded_poa_files = st.file_uploader(
            "Upload SolarGIS POA CSV File(s)", 
            type=["csv"], 
            accept_multiple_files=True,
            key="poa_file_upload",
            help="Select one or more SolarGIS CSV files containing POA/GTI irradiance data"
        )
        
        if uploaded_poa_files:
            st.info(f"📁 {len(uploaded_poa_files)} file(s) uploaded")
            
            # Initialize session state for file-plant mappings
            if 'poa_file_mappings' not in st.session_state:
                st.session_state.poa_file_mappings = {}
            
            # Auto-match files to plants using fuzzy matching
            from difflib import SequenceMatcher
            
            def fuzzy_match_to_plant(filename: str, plant_aliases: list, threshold: float = 0.5) -> str:
                """Find best matching plant alias for a filename."""
                base_name = os.path.splitext(filename)[0].lower().replace("_", " ").replace("-", " ")
                best_match = None
                best_score = 0.0
                
                for alias in plant_aliases:
                    alias_lower = alias.lower().replace("_", " ").replace("-", " ")
                    score = SequenceMatcher(None, base_name, alias_lower).ratio()
                    if score > best_score and score >= threshold:
                        best_score = score
                        best_match = alias
                
                return best_match
            
            st.subheader("File to Plant Mapping")
            st.markdown("Auto-matched based on filename. Override manually if needed. **All data in the file will be imported.**")
            
            # Display each file with preview and mapping
            file_mappings = {}
            
            for i, uploaded_file in enumerate(uploaded_poa_files):
                filename = uploaded_file.name
                
                # Auto-match
                auto_matched = fuzzy_match_to_plant(filename, plant_aliases)
                
                with st.expander(f"📄 {filename}" + (f" → {auto_matched}" if auto_matched else " ⚠️ No match"), expanded=(not auto_matched)):
                    # Preview file data
                    try:
                        df_preview = pd.read_csv(uploaded_file)
                        uploaded_file.seek(0)  # Reset for later reading
                        
                        col_info, col_map = st.columns([2, 1])
                        
                        with col_info:
                            st.markdown("**File Preview:**")
                            st.dataframe(df_preview.head(5), width='stretch')
                            st.caption(f"Total rows: {len(df_preview)} | Columns: {', '.join(df_preview.columns[:5])}...")
                            
                            # Detect timestamp format
                            time_cols = [c for c in df_preview.columns if any(t in c.lower() for t in ['time', 'date'])]
                            if time_cols:
                                sample_ts = df_preview[time_cols[0]].iloc[0] if len(df_preview) > 0 else "N/A"
                                st.caption(f"Timestamp column: `{time_cols[0]}` (sample: {sample_ts})")
                        
                        with col_map:
                            st.markdown("**Link to Plant:**")
                            # Manual plant selection with auto-match as default
                            default_idx = plant_aliases.index(auto_matched) if auto_matched and auto_matched in plant_aliases else 0
                            
                            selected_plant_alias = st.selectbox(
                                "Select Plant",
                                options=["-- Skip this file --"] + plant_aliases,
                                index=default_idx + 1 if auto_matched else 0,
                                key=f"poa_map_{i}",
                                label_visibility="collapsed"
                            )
                            
                            if selected_plant_alias and selected_plant_alias != "-- Skip this file --":
                                file_mappings[filename] = {
                                    'alias': selected_plant_alias,
                                    'file_obj': uploaded_file
                                }
                                st.success(f"✓ Will import as POA:{selected_plant_alias.replace(' ', '_').upper()}")
                            else:
                                st.warning("File will be skipped")
                                
                    except Exception as e:
                        st.error(f"Error reading file: {e}")
            
            # Import button
            if file_mappings:
                st.markdown("---")
                if st.button(f"🚀 Import {len(file_mappings)} POA File(s)", type="primary", key="import_poa_btn"):
                    clear_logs()
                    results = {}
                    
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    for idx, (filename, mapping) in enumerate(file_mappings.items()):
                        status_text.text(f"Importing {filename}...")
                        
                        try:
                            # Save uploaded file to temp location
                            with tempfile.NamedTemporaryFile(delete=False, suffix=".csv", prefix="poa_") as tmp:
                                mapping['file_obj'].seek(0)
                                tmp.write(mapping['file_obj'].read())
                                temp_path = tmp.name
                            
                            # Import using orchestrator's POA import with temp file (no date filtering)
                            count = orch.import_poa_from_file(
                                mapping['alias'], 
                                temp_path
                            )
                            results[filename] = count
                            
                            # Cleanup
                            os.unlink(temp_path)
                            
                        except Exception as e:
                            st.error(f"Error importing {filename}: {e}")
                            results[filename] = 0
                        
                        progress_bar.progress((idx + 1) / len(file_mappings))
                    
                    status_text.empty()
                    progress_bar.empty()
                    
                    # Show results
                    total_imported = sum(results.values())
                    if total_imported > 0:
                        st.success(f"✅ POA Import complete! Imported {total_imported} readings across {len([r for r in results.values() if r > 0])} files.")
                        for fname, count in results.items():
                            if count > 0:
                                st.write(f"  ✓ {fname}: {count} readings")
                    else:
                        st.warning("No readings were imported. Check the file format.")
                    
                    display_logs()
            else:
                st.info("Select at least one file and map it to a plant to enable import.")
    
    else:  # From Folder Path
        st.markdown("Import POA data from a local folder. Files will be auto-matched to registered plants.")
        
        with st.form("poa_folder_import_form"):
            folder_path = st.text_input(
                "Path to SolarGIS Folder", 
                value="",
                placeholder="C:/Users/YourName/Documents/SolarGIS_Data",
                help="Enter the full path to the folder containing SolarGIS CSV files"
            )
            col1, col2 = st.columns(2)
            start_date = col1.date_input("Data Start Date", value=datetime.today() - timedelta(days=365), key="poa_folder_start")
            end_date = col2.date_input("Data End Date", value=datetime.today(), key="poa_folder_end")
            
            col_btn1, col_btn2 = st.columns(2)
            preview_btn = col_btn1.form_submit_button("📋 Preview Matches")
            import_btn = col_btn2.form_submit_button("🚀 Import All Matched")
            
        if preview_btn or import_btn:
            clear_logs()
            
            if not folder_path or not folder_path.strip():
                st.error("Please enter a folder path.")
            elif not os.path.isdir(folder_path):
                st.error(f"Folder not found: {folder_path}")
            else:
                try:
                    start_str = start_date.strftime("%Y%m%d")
                    end_str = end_date.strftime("%Y%m%d")
                    
                    if preview_btn:
                        with st.spinner("Analyzing files in folder..."):
                            preview_data = orch.preview_bulk_poa_matches(folder_path)
                            
                            if preview_data['matched_files']:
                                st.success(f"Found {len(preview_data['matched_files'])} matched files")
                                
                                st.subheader("Auto-Matched Files")
                                for filename, alias in preview_data['matched_files'].items():
                                    st.write(f"✓ **{filename}** → {alias}")
                                
                                # Display linkage previews
                                st.subheader("Data Linkage Preview")
                                for linkage in preview_data['previews'][:PREVIEW_LIMIT]:
                                    with st.expander(f"📄 {linkage['file_info']['filename']} → {linkage['plant_alias']}"):
                                        col1, col2 = st.columns(2)
                                        
                                        with col1:
                                            st.markdown("**File Information**")
                                            st.write(f"Rows: {linkage['file_info']['total_rows']}")
                                            st.write(f"Date Range: {linkage['file_info']['date_range'][0]} to {linkage['file_info']['date_range'][1]}")
                                            st.write(f"POA Column: {linkage['file_info']['poa_column']}")
                                            
                                            if linkage['file_info'].get('is_multi_array'):
                                                num_arrays = linkage['file_info'].get('num_arrays', 0)
                                                total_cap = linkage['file_info'].get('total_capacity_kw', 0)
                                                st.markdown(f"**🔀 Multi-Array:** {num_arrays} arrays ({total_cap:.1f} kW)")
                                                arrays = linkage['file_info'].get('arrays', [])
                                                for arr in arrays:
                                                    weight = (arr['capacity_kw'] / total_cap * 100) if total_cap > 0 else 0
                                                    st.write(f"  • {arr['capacity_kw']:.0f} kW @ Az {arr['azimuth']}°, Tilt {arr['tilt']}° ({weight:.0f}%)")
                                            
                                            if linkage.get('poa_stats'):
                                                stats = linkage['poa_stats']
                                                st.write(f"POA Mean: {stats['mean']:.1f} W/m²")
                                                st.write(f"POA Max: {stats['max']:.1f} W/m²")
                                        
                                        with col2:
                                            st.markdown("**Will be linked to:**")
                                            st.write(f"Plant: {linkage['plant_alias']}")
                                            st.write(f"UID: {linkage['plant_uid']}")
                                            st.write(f"POA Device: {linkage['poa_emig_id']}")
                                            st.write(f"DC Size: {linkage['dc_size_kw']} kW" if linkage['dc_size_kw'] else "DC Size: Not set")
                                            st.markdown("**Existing devices:**")
                                            st.write(f"Inverters: {', '.join(linkage['inverter_ids']) if linkage['inverter_ids'] else 'None'}")
                            
                            if preview_data['unmatched_files']:
                                st.warning(f"⚠️ {len(preview_data['unmatched_files'])} unmatched files (will be skipped)")
                                for filename in preview_data['unmatched_files']:
                                    st.write(f"  - {filename}")
                            
                            if not preview_data['matched_files'] and not preview_data['unmatched_files']:
                                st.warning("No CSV files found in the specified folder.")
                    
                    elif import_btn:
                        with st.spinner("Importing POA data..."):
                            results = orch.bulk_import_poa(folder_path, start_str, end_str, auto_confirm=True)
                            
                            if results:
                                total = sum(results.values())
                                st.success(f"✅ Bulk import complete! Imported {total} readings across {len(results)} files.")
                                
                                for filename, count in results.items():
                                    st.write(f"  ✓ {filename}: {count} readings")
                            else:
                                st.warning("No files were imported. Check logs for details.")
                
                except Exception as e:
                    st.error(f"Error: {e}")
                finally:
                    display_logs()

# --- TAB 3: Fouling Analysis ---
with tab_fouling:
    st.header("3. Fouling (Soiling) Analysis")
    st.markdown("Computes the Fouling Index using the auto-clean period method (compares current PR to baseline PR).")
    
    uploaded_file = st.file_uploader("Upload Combined Operational Data CSV (Full Period)", type="csv")
    
    with st.form("fouling_form"):
        default_dc_size = selected_plant.get('dc_size_kw') if selected_plant.get('dc_size_kw') else 1000.0
        dc_size = st.number_input("DC Size (kW)", value=float(default_dc_size), min_value=1.0)
        auto_days = st.slider("Auto-Clean Period Length (days)", min_value=1, max_value=30, value=3)
        
        submitted = st.form_submit_button("Run Fouling Analysis")

        if submitted and uploaded_file is not None:
            clear_logs()
            temp_path = None
            try:
                # Save uploaded file temporarily for the orchestrator to read
                with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp_file:
                    tmp_file.write(uploaded_file.getbuffer())
                    temp_path = tmp_file.name
                
                with st.spinner(f"Running analysis (DC Size: {dc_size} kW)..."):
                    result = orch.run_fouling_auto(temp_path, dc_size, auto_days)
                    df_result = result['df_result']
                    
                    st.success(f"✅ Analysis complete! Used power column: `{result['power_col_used']}`")
                    
                    col_idx, col_lvl = st.columns(2)
                    col_idx.metric("Median Fouling Index", f"{result['fouling_index']:.4f}")
                    col_lvl.metric("Fouling Level", result['fouling_level'])
                    
                    # 
                    
                    st.markdown("### Performance Ratio Over Time")
                    
                    # Create the Altair chart
                    chart = alt.Chart(df_result).mark_point(opacity=0.3).encode(
                        x=alt.X('ts:T', title="Timestamp"),
                        y=alt.Y('fouling_index', title="Fouling Index (Actual PR / Baseline PR)"),
                        tooltip=['ts:T', 'fouling_index', 'pr', 'baseline_pr']
                    ).properties(
                        height=400
                    ).interactive() # Allows zooming/panning
                    
                    # Add median line for the overall index
                    median_line = alt.Chart(pd.DataFrame({'median_fouling_index': [result['fouling_index']]})).mark_rule(color='red').encode(
                        y='median_fouling_index'
                    )
                    
                    st.altair_chart(chart + median_line, width='stretch')
                    
            except Exception as e:
                st.error(f"Error during fouling analysis: {e}")
            finally:
                if temp_path and os.path.exists(temp_path):
                    os.remove(temp_path)
                display_logs()
    
    # Provide download button outside the form
    if 'df_result' in dir() and df_result is not None:
        st.download_button("Download Detailed Fouling Data", df_result.to_csv().encode('utf-8'), "fouling_detail.csv", "text/csv")


# --- TAB 4: Shading Analysis ---
with tab_shading:
    st.header("4. Shading Analysis")
    st.markdown("""
    Compares power profiles between a sun-high season (baseline) and a sun-low season (shaded) to identify angular shading.
    
    **Summer baseline** is automatically selected (Jun-Aug for Northern Hemisphere). 
    Select a **comparison period** (typically winter months) to analyze shading impact.
    """)
    
    # Data source selection
    data_source = st.radio(
        "Data Source",
        ["From Database", "Upload CSV Files (Backup)"],
        horizontal=True,
        key="shading_data_source"
    )
    
    if data_source == "From Database":
        # Get available plants with data
        viewer = DataViewer(db_path=settings.DB_PATH)
        available_plants = viewer.get_unique_plant_uids()
        
        if not available_plants:
            st.warning("No plant data in database. Please fetch data first or use CSV upload.")
        else:
            # Plant selection
            shading_plant = st.selectbox(
                "Select Plant",
                options=available_plants,
                key="shading_plant_select"
            )
            
            if shading_plant:
                # Get date range for selected plant
                date_range = viewer.get_date_range(plant_uid=shading_plant)
                
                if date_range[0] and date_range[1]:
                    min_date = datetime.fromisoformat(date_range[0][:10])
                    max_date = datetime.fromisoformat(date_range[1][:10])
                    
                    st.info(f"📅 Data available from **{min_date.strftime('%Y-%m-%d')}** to **{max_date.strftime('%Y-%m-%d')}**")
                    
                    # Helper to clamp dates to valid range
                    def clamp_date(d, min_d, max_d):
                        if d < min_d:
                            return min_d
                        if d > max_d:
                            return max_d
                        return d
                    
                    # Auto-detect summer baseline (Jun-Aug)
                    # Try current year first, then previous year
                    current_year = max_date.year
                    summer_start_candidate = None
                    summer_end_candidate = None
                    
                    # Try to find a valid summer period within the data range
                    for year in [current_year, current_year - 1]:
                        s_start = datetime(year, 6, 1)
                        s_end = datetime(year, 8, 31)
                        # Check if any part of summer overlaps with data range
                        if s_end >= min_date and s_start <= max_date:
                            summer_start_candidate = clamp_date(s_start, min_date, max_date)
                            summer_end_candidate = clamp_date(s_end, min_date, max_date)
                            break
                    
                    # Fallback: use first half of available data range
                    if summer_start_candidate is None:
                        data_range_days = (max_date - min_date).days
                        summer_start_candidate = min_date
                        summer_end_candidate = min_date + timedelta(days=max(data_range_days // 2, 7))
                        summer_end_candidate = clamp_date(summer_end_candidate, min_date, max_date)
                    
                    st.markdown("---")
                    st.subheader("☀️ Baseline Period (Summer)")
                    st.markdown("Summer period is automatically selected as baseline (highest sun angle).")
                    
                    col_s1, col_s2 = st.columns(2)
                    baseline_start = col_s1.date_input(
                        "Baseline Start",
                        value=summer_start_candidate,
                        min_value=min_date,
                        max_value=max_date,
                        key="shading_baseline_start"
                    )
                    baseline_end = col_s2.date_input(
                        "Baseline End",
                        value=summer_end_candidate,
                        min_value=min_date,
                        max_value=max_date,
                        key="shading_baseline_end"
                    )
                    
                    st.markdown("---")
                    st.subheader("❄️ Comparison Period (Winter/Shaded)")
                    st.markdown("Select the period you want to compare against the baseline (typically winter months with lower sun angle).")
                    
                    # Default comparison period: try Oct-Dec or just use second half of data
                    winter_start_default = None
                    winter_end_default = None
                    
                    # Try to find a fall/winter period (Oct-Dec)
                    for year in [current_year, current_year - 1]:
                        w_start = datetime(year, 10, 1)
                        w_end = datetime(year, 12, 31)
                        if w_end >= min_date and w_start <= max_date:
                            winter_start_default = clamp_date(w_start, min_date, max_date)
                            winter_end_default = clamp_date(w_end, min_date, max_date)
                            break
                    
                    # Fallback: use last portion of available data range
                    if winter_start_default is None:
                        data_range_days = (max_date - min_date).days
                        winter_start_default = max_date - timedelta(days=max(data_range_days // 3, 7))
                        winter_start_default = clamp_date(winter_start_default, min_date, max_date)
                        winter_end_default = max_date
                    
                    col_w1, col_w2 = st.columns(2)
                    compare_start = col_w1.date_input(
                        "Comparison Start",
                        value=winter_start_default,
                        min_value=min_date,
                        max_value=max_date,
                        key="shading_compare_start"
                    )
                    compare_end = col_w2.date_input(
                        "Comparison End",
                        value=winter_end_default,
                        min_value=min_date,
                        max_value=max_date,
                        key="shading_compare_end"
                    )
                    
                    output_base = st.text_input("Output Filename Base", "shading_report", key="shading_output_db")
                    
                    if st.button("🔍 Run Shading Analysis", key="run_shading_db", type="primary"):
                        clear_logs()
                        
                        try:
                            with st.spinner("Loading data and analyzing shading patterns..."):
                                # Get inverter devices for the plant
                                all_devices = viewer.get_unique_device_ids(shading_plant)
                                inverter_devices = [d for d in all_devices if d.startswith("INVERT:")]
                                
                                # Debug: Show all device types
                                st.info(f"📱 All device IDs: {all_devices}")
                                
                                if not inverter_devices:
                                    st.error("No inverter data found for this plant.")
                                else:
                                    # Load baseline (summer) data
                                    baseline_df, _ = viewer.get_readings_data(
                                        plant_uid=shading_plant,
                                        start_date=baseline_start.strftime("%Y-%m-%d"),
                                        end_date=baseline_end.strftime("%Y-%m-%d"),
                                        limit=100000
                                    )
                                    
                                    # Load comparison (winter) data
                                    compare_df, _ = viewer.get_readings_data(
                                        plant_uid=shading_plant,
                                        start_date=compare_start.strftime("%Y-%m-%d"),
                                        end_date=compare_end.strftime("%Y-%m-%d"),
                                        limit=100000
                                    )
                                    
                                    # Debug: Show columns available
                                    st.info(f"📊 Available columns: {list(baseline_df.columns)}")
                                    
                                    # Split into Inverter and Irradiance data
                                    # Irradiance data usually comes from POA devices or Weather stations
                                    
                                    # Helper to split - improved to also check for embedded irradiance
                                    def split_inv_irr(df):
                                        inv = df[df['emig_id'].str.startswith("INVERT:")].copy()
                                        # Look for POA or WETH or MET - broader matching
                                        irr = df[df['emig_id'].str.contains("POA|WETH|MET|PYRANO|SENSOR|WEATHER", case=False, regex=True)].copy()
                                        return inv, irr
                                    
                                    baseline_inv, baseline_irr = split_inv_irr(baseline_df)
                                    compare_inv, compare_irr = split_inv_irr(compare_df)
                                    
                                    if baseline_inv.empty:
                                        st.error("No baseline (summer) inverter data found.")
                                    elif compare_inv.empty:
                                        st.error("No comparison (winter) inverter data found.")
                                    else:
                                        st.success(f"✅ Loaded {len(baseline_inv):,} baseline readings and {len(compare_inv):,} comparison readings")
                                        
                                        # Check for embedded irradiance in inverter data
                                        irr_cols_in_inv = [c for c in baseline_inv.columns if any(x in c.lower() for x in ['irradiance', 'poa', 'gti'])]
                                        if irr_cols_in_inv:
                                            st.info(f"🌡️ Found potential irradiance columns in inverter data: {irr_cols_in_inv}")
                                        
                                        if not baseline_irr.empty and not compare_irr.empty:
                                            st.info(f"✅ Found irradiance data: {len(baseline_irr)+len(compare_irr):,} readings. Performing normalized analysis.")
                                        elif irr_cols_in_inv:
                                            st.info(f"✅ Will use embedded irradiance from inverter data: {irr_cols_in_inv}")
                                        else:
                                            st.error("""
                                            ❌ **No irradiance data found!** 
                                            
                                            Without POA irradiance data, shading analysis cannot distinguish between:
                                            - Seasonal differences in sunlight (normal)
                                            - Actual shading losses (problem)
                                            
                                            **To fix this:**
                                            1. Go to the **POA Import** tab
                                            2. Import SolarGIS or measured POA irradiance data for this plant
                                            3. Return here and re-run the analysis
                                            
                                            Raw power comparison will show winter at ~30-40% of summer due to seasonal differences - this is NOT indicative of shading.
                                            """)
                                        
                                        # Find power column
                                        power_col = None
                                        for candidate in ['apparentPower_value', 'activePower_value', 'exportEnergy_value', 'dcPower_value']:
                                            if candidate in baseline_inv.columns:
                                                power_col = candidate
                                                break
                                        
                                        # Find irradiance column - check in inverter data and separate irr data
                                        irr_col = None
                                        # Check in separate irradiance data first
                                        if not baseline_irr.empty:
                                            for candidate in ['poaIrradiance_value', 'poaIrradiance', 'GTI_value', 'GTI', 'POA_value', 'POA', 'gti_value', 'gti']:
                                                if candidate in baseline_irr.columns:
                                                    irr_col = candidate
                                                    break
                                        # Fallback: check in inverter data
                                        if irr_col is None and irr_cols_in_inv:
                                            irr_col = irr_cols_in_inv[0]
                                        if irr_col is None:
                                            irr_col = "poaIrradiance"  # Default fallback
                                        
                                        if power_col is None:
                                            st.error(f"Could not find power column. Available: {list(baseline_inv.columns)}")
                                        else:
                                            st.info(f"Using power column: `{power_col}`")
                                            st.info(f"Using irradiance column: `{irr_col}`")
                                            
                                            # DEBUG: Show sample data
                                            with st.expander("🔍 Debug: Sample Data", expanded=True):
                                                st.markdown("**Baseline Inverter Sample:**")
                                                st.write(f"Columns: {list(baseline_inv.columns)}")
                                                st.write(f"Sample ts values: {baseline_inv['ts'].head(3).tolist()}")
                                                st.write(f"Sample emig_id: {baseline_inv['emig_id'].unique()[:3].tolist()}")
                                                
                                                # Show irradiance values if embedded
                                                if irr_cols_in_inv:
                                                    st.markdown("**Embedded Irradiance in Inverter Data:**")
                                                    for ic in irr_cols_in_inv:
                                                        vals = baseline_inv[ic].dropna()
                                                        if len(vals) > 0:
                                                            st.write(f"  {ic}: min={vals.min():.4f}, max={vals.max():.4f}, mean={vals.mean():.4f}")
                                                            st.write(f"    Sample values: {vals.head(5).tolist()}")
                                                
                                                st.markdown("**Comparison Inverter Sample:**")
                                                st.write(f"Sample ts values: {compare_inv['ts'].head(3).tolist()}")
                                                st.write(f"Sample emig_id: {compare_inv['emig_id'].unique()[:3].tolist()}")
                                                
                                                if not baseline_irr.empty:
                                                    st.markdown("**Baseline Irradiance Sample:**")
                                                    st.write(f"Columns: {list(baseline_irr.columns)}")
                                                    st.write(f"Sample ts values: {baseline_irr['ts'].head(3).tolist()}")
                                                    st.write(f"Sample emig_id: {baseline_irr['emig_id'].unique()[:3].tolist()}")
                                                    if irr_col in baseline_irr.columns:
                                                        st.write(f"Sample {irr_col}: {baseline_irr[irr_col].head(3).tolist()}")
                                                    else:
                                                        st.warning(f"Column '{irr_col}' not found in baseline_irr. Available: {list(baseline_irr.columns)}")
                                                
                                                if not compare_irr.empty:
                                                    st.markdown("**Comparison Irradiance Sample:**")
                                                    st.write(f"Sample ts values: {compare_irr['ts'].head(3).tolist()}")
                                            
                                            # Calculate hourly profiles per inverter using the shading analysis module
                                            from solar_toolkit.shading_analysis import analyze_from_dataframes, ShadingSettings
                                            
                                            # Run analysis using the full methodology
                                            merged, summary = analyze_from_dataframes(
                                                summer_inv_df=baseline_inv,
                                                winter_inv_df=compare_inv,
                                                power_col=power_col,
                                                summer_irr_df=baseline_irr if not baseline_irr.empty else None,
                                                winter_irr_df=compare_irr if not compare_irr.empty else None,
                                                irr_col=irr_col,
                                                emig_id_col='emig_id',
                                                timestamp_col='ts'
                                            )
                                            
                                            if merged.empty:
                                                st.warning("No overlapping hourly data between periods.")
                                            else:
                                                st.markdown("### 📊 Shading Loss Ratio Summary")
                                                st.markdown("""
                                                **Ratio** = Winter Power / Summer Power (values < 1.0 indicate lower winter output)
                                                
                                                **Classification:**
                                                - 🟢 **No Shading**: Ratio ≥ 0.95
                                                - 🟡 **Mild Shading**: Ratio 0.85 - 0.95
                                                - 🟠 **Moderate Shading**: Ratio 0.70 - 0.85
                                                - 🔴 **Severe Shading**: Ratio < 0.70
                                                """)
                                                
                                                # Display summary with classification
                                                if not summary.empty:
                                                    display_summary = summary.copy()
                                                    
                                                    # Add color indicators based on classification column
                                                    def classify_color(row):
                                                        if row['classification'] == 'No Shading':
                                                            return '🟢'
                                                        elif row['classification'] == 'Mild Shading':
                                                            return '🟡'
                                                        elif row['classification'] == 'Moderate Shading':
                                                            return '🟠'
                                                        else:
                                                            return '🔴'
                                                    
                                                    display_summary['Status'] = display_summary.apply(classify_color, axis=1)
                                                    
                                                    # Rename columns for display
                                                    col_rename = {
                                                        'emig_id': 'Inverter ID',
                                                        'emigId': 'Inverter ID',
                                                        'ratio': 'Median Ratio',
                                                        'classification': 'Classification',
                                                        'estimated_loss_pct': 'Estimated Loss (%)',
                                                        'n_core_hours': 'Core Hours Data Points'
                                                    }
                                                    display_summary = display_summary.rename(columns=col_rename)
                                                    
                                                    # Select and order columns for display
                                                    display_cols = ['Status', 'Inverter ID', 'Classification', 'Median Ratio', 'Estimated Loss (%)']
                                                    available_cols = [c for c in display_cols if c in display_summary.columns]
                                                    display_summary = display_summary[available_cols].sort_values('Estimated Loss (%)', ascending=False)
                                                    
                                                    st.dataframe(display_summary, use_container_width=True, hide_index=True)
                                                    
                                                    # Highlight inverters with significant shading
                                                    severe = summary[summary['classification'] == 'Severe Shading']
                                                    moderate = summary[summary['classification'] == 'Moderate Shading']
                                                    
                                                    if not severe.empty:
                                                        st.error(f"🔴 {len(severe)} inverter(s) have SEVERE shading (>30% loss)")
                                                    if not moderate.empty:
                                                        st.warning(f"🟠 {len(moderate)} inverter(s) have MODERATE shading (15-30% loss)")
                                                
                                                # Hourly profile chart
                                                st.markdown("### 📈 Hourly Power Profile Comparison")
                                                
                                                # Aggregate across all inverters from merged data
                                                agg_profile = merged.groupby('hour_float').agg({
                                                    'eff_median_summer': 'mean',
                                                    'eff_median_winter': 'mean',
                                                    'ratio': 'mean'
                                                }).reset_index()
                                                
                                                chart_data = agg_profile.melt(
                                                    id_vars='hour_float', 
                                                    value_vars=['eff_median_summer', 'eff_median_winter'],
                                                    var_name='Period', 
                                                    value_name='Power'
                                                )
                                                chart_data['Period'] = chart_data['Period'].map({
                                                    'eff_median_summer': f'Summer ({baseline_start} to {baseline_end})',
                                                    'eff_median_winter': f'Winter ({compare_start} to {compare_end})'
                                                })
                                                
                                                chart = alt.Chart(chart_data).mark_line(point=True).encode(
                                                    x=alt.X('hour_float:Q', title='Hour of Day', scale=alt.Scale(domain=[5, 20])),
                                                    y=alt.Y('Power:Q', title='Average Power'),
                                                    color='Period:N',
                                                    tooltip=['hour_float', 'Power', 'Period']
                                                ).properties(height=400).interactive()
                                                
                                                st.altair_chart(chart, use_container_width=True)
                                                
                                                # Add ratio chart
                                                st.markdown("### 📉 Hourly Loss Ratio")
                                                st.markdown("Shows the winter/summer ratio by hour. Values below 1.0 indicate energy loss.")
                                                
                                                ratio_chart = alt.Chart(agg_profile).mark_bar().encode(
                                                    x=alt.X('hour_float:Q', title='Hour of Day', scale=alt.Scale(domain=[5, 20])),
                                                    y=alt.Y('ratio:Q', title='Ratio (Winter/Summer)', scale=alt.Scale(domain=[0, 1.2])),
                                                    color=alt.condition(
                                                        alt.datum.ratio < 0.85,
                                                        alt.value('red'),
                                                        alt.value('green')
                                                    ),
                                                    tooltip=['hour_float', alt.Tooltip('ratio:Q', format='.2f')]
                                                ).properties(height=300)
                                                
                                                # Add reference line at ratio = 1.0
                                                rule = alt.Chart(pd.DataFrame({'y': [1.0]})).mark_rule(
                                                    strokeDash=[4, 4], color='gray'
                                                ).encode(y='y:Q')
                                                
                                                st.altair_chart(ratio_chart + rule, use_container_width=True)
                                                
                                                # Download results
                                                csv_data = merged.to_csv(index=False).encode('utf-8')
                                                st.download_button(
                                                    "📥 Download Detailed Analysis CSV",
                                                    csv_data,
                                                    f"{output_base}_detail.csv",
                                                    "text/csv"
                                                )
                                                
                                                # Download summary
                                                if not summary.empty:
                                                    summary_csv = summary.to_csv(index=False).encode('utf-8')
                                                    st.download_button(
                                                        "📥 Download Summary CSV",
                                                        summary_csv,
                                                        f"{output_base}_summary.csv",
                                                        "text/csv"
                                                    )
                                                
                                                # Compute and display daily/monthly loss breakdown
                                                from solar_toolkit.shading_analysis import compute_daily_monthly_loss
                                                cfg = ShadingSettings()
                                                cfg.emigid_col = 'emig_id' if 'emig_id' in merged.columns else 'emigId'
                                                daily_loss, monthly_loss = compute_daily_monthly_loss(merged, cfg)
                                                
                                                if not daily_loss.empty or not monthly_loss.empty:
                                                    st.markdown("### 📅 Daily & Monthly Loss Breakdown")
                                                    
                                                    col_d, col_m = st.columns(2)
                                                    
                                                    with col_d:
                                                        if not daily_loss.empty:
                                                            st.markdown("**Daily Loss Summary (Core Hours)**")
                                                            daily_display = daily_loss.copy()
                                                            daily_display['loss_pct'] = daily_display['loss_pct'].round(1)
                                                            daily_display['ratio'] = daily_display['ratio'].round(3)
                                                            st.dataframe(daily_display.head(50), use_container_width=True, hide_index=True)
                                                            
                                                            daily_csv = daily_loss.to_csv(index=False).encode('utf-8')
                                                            st.download_button(
                                                                "📥 Download Daily Loss CSV",
                                                                daily_csv,
                                                                f"{output_base}_daily_loss.csv",
                                                                "text/csv"
                                                            )
                                                    
                                                    with col_m:
                                                        if not monthly_loss.empty:
                                                            st.markdown("**Monthly Loss Summary (Core Hours)**")
                                                            monthly_display = monthly_loss.copy()
                                                            monthly_display['loss_pct'] = monthly_display['loss_pct'].round(1)
                                                            monthly_display['ratio'] = monthly_display['ratio'].round(3)
                                                            monthly_display['year_month'] = monthly_display['year_month'].astype(str)
                                                            st.dataframe(monthly_display, use_container_width=True, hide_index=True)
                                                            
                                                            monthly_csv = monthly_loss.to_csv(index=False).encode('utf-8')
                                                            st.download_button(
                                                                "📥 Download Monthly Loss CSV",
                                                                monthly_csv,
                                                                f"{output_base}_monthly_loss.csv",
                                                                "text/csv"
                                                            )
                        
                        except Exception as e:
                            st.error(f"Error during shading analysis: {e}")
                            import traceback
                            st.code(traceback.format_exc())
                        finally:
                            display_logs()
                else:
                    st.warning("No data available for the selected plant.")
    
    else:  # Upload CSV Files (Backup)
        st.markdown("**Backup option:** Upload pre-exported CSV files if database data is not available.")
        
        col_sum, col_win = st.columns(2)
        with col_sum:
            summer_file = st.file_uploader("Upload Summer (Baseline) CSV", type="csv", key="summer_upload")
        with col_win:
            winter_file = st.file_uploader("Upload Winter (Shaded) CSV", type="csv", key="winter_upload")
            
        output_base = st.text_input("Output Filename Base", "shading_report", key="shading_output_csv")
            
        if st.button("Run Shading Analysis", key="run_shading_csv"):
            if summer_file is None or winter_file is None:
                st.error("Please upload both Summer and Winter data CSVs.")
            else:
                clear_logs()
                temp_sum_path = None
                temp_win_path = None
                
                try:
                    # Save files temporarily
                    with tempfile.NamedTemporaryFile(delete=False, suffix="_summer.csv") as tmp_sum:
                        tmp_sum.write(summer_file.getbuffer())
                        temp_sum_path = tmp_sum.name
                    with tempfile.NamedTemporaryFile(delete=False, suffix="_winter.csv") as tmp_win:
                        tmp_win.write(winter_file.getbuffer())
                        temp_win_path = tmp_win.name
                    
                    with st.spinner("Analyzing shading... (This may take a moment to generate plots)"):
                        df_result = orch.run_shading_analysis(temp_sum_path, temp_win_path, output_base)
                        st.success("✅ Analysis complete! PDF plots and detailed CSV have been generated.")
                        
                        st.markdown("### Shading Loss Ratio Summary")
                        
                        # Compute mean loss per inverter in the core window (9-15)
                        core_df = df_result[(df_result["hour_float"] >= 9) & (df_result["hour_float"] <= 15)].copy()
                        
                        if not core_df.empty:
                            summary = core_df.groupby('emigId')['ratio'].median().reset_index()
                            summary.columns = ['Inverter ID', 'Median Ratio (Winter/Summer)']
                            summary['Estimated Core Loss (%)'] = ((1 - summary['Median Ratio (Winter/Summer)']) * 100).round(2)
                            
                            st.dataframe(summary)
                        else:
                            st.warning("No valid data points found in the core analysis window (9:00 - 15:00).")

                except Exception as e:
                    st.error(f"Error during shading analysis: {e}")
                finally:
                    if temp_sum_path and os.path.exists(temp_sum_path): os.remove(temp_sum_path)
                    if temp_win_path and os.path.exists(temp_win_path): os.remove(temp_win_path)
                    display_logs() 
        # The CLI version saves the PDF directly.

# --- TAB 5: Database Viewer ---
with tab_viewer:
    st.header("5. Database Viewer")
    st.markdown("View, filter, edit, and delete data from the database with flexible filtering options.")
    
    # Initialize DataViewer
    viewer = DataViewer(db_path=settings.DB_PATH)
    
    # Create sub-tabs for Plants and Readings
    viewer_mode = st.radio("Data Type", ["Plants Registry", "Operational Readings"], horizontal=True)
    
    if viewer_mode == "Plants Registry":
        st.subheader("📋 Registered Plants")
        
        # Load and display plants data
        try:
            plants_df = viewer.get_plants_data()
            
            if plants_df.empty:
                st.info("No plants registered yet. Use the 'Plants & Data Fetch' tab to add plants.")
            else:
                st.markdown(f"**Total plants:** {len(plants_df)}")
                
                # Display plants table with editing capability
                st.dataframe(plants_df, width='stretch', height=400)
                
                # Download plants data
                csv = plants_df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    "📥 Download Plants Data (CSV)",
                    csv,
                    "plants_registry.csv",
                    "text/csv",
                    key='download-plants'
                )
                
                # Delete plant functionality
                st.markdown("---")
                st.subheader("🗑️ Delete Plant")
                st.warning("⚠️ Deleting a plant will remove it from the registry. This does NOT delete associated readings.")
                
                col1, col2 = st.columns([3, 1])
                with col1:
                    plant_to_delete = st.selectbox(
                        "Select plant to delete",
                        options=plants_df['alias'].tolist(),
                        key="delete_plant_select"
                    )
                with col2:
                    st.write("")  # Spacing
                    st.write("")  # Spacing
                    if st.button("🗑️ Delete Plant", key="delete_plant_btn", type="secondary"):
                        try:
                            viewer.delete_plant(plant_to_delete)
                            st.success(f"✅ Plant '{plant_to_delete}' deleted successfully!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error deleting plant: {e}")
        
        except Exception as e:
            st.error(f"Error loading plants data: {e}")
    
    else:  # Operational Readings
        st.subheader("📊 Operational Readings")
        
        # Get filter options
        try:
            available_plants = viewer.get_unique_plant_uids()
            stats = viewer.get_readings_stats()
            
            # Display overall statistics
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Readings", f"{stats['total_readings']:,}")
            col2.metric("Unique Plants", stats['unique_plants'])
            col3.metric("Unique Devices", stats['unique_devices'])
            
            if stats['earliest_reading'] and stats['latest_reading']:
                date_range_text = f"{stats['earliest_reading'][:10]} to {stats['latest_reading'][:10]}"
                col4.metric("Date Range", date_range_text)
            
            st.markdown("---")
            
            # Filtering options
            st.subheader("🔍 Filter Options")
            
            col1, col2 = st.columns(2)
            
            with col1:
                filter_plant = st.selectbox(
                    "Filter by Plant",
                    options=["All"] + available_plants,
                    key="filter_plant"
                )
                selected_plant = None if filter_plant == "All" else filter_plant
                
                # Device type filter (Inverter vs POA)
                device_type = st.selectbox(
                    "Device Type",
                    options=["All", "Inverters", "POA (Irradiance)"],
                    key="filter_device_type",
                    help="Filter by device type: Inverters (INVERT:*) or POA irradiance data (POA:*)"
                )
                
                # Get devices for selected plant, filtered by type
                if selected_plant:
                    all_devices = viewer.get_unique_device_ids(selected_plant)
                    date_range = viewer.get_date_range(plant_uid=selected_plant)
                else:
                    all_devices = viewer.get_unique_device_ids()
                    date_range = viewer.get_date_range()
                
                # Filter devices by type
                if device_type == "Inverters":
                    available_devices = [d for d in all_devices if d.startswith("INVERT:")]
                elif device_type == "POA (Irradiance)":
                    available_devices = [d for d in all_devices if d.startswith("POA:")]
                else:
                    available_devices = all_devices
                
                filter_device = st.selectbox(
                    "Filter by Device",
                    options=["All"] + available_devices,
                    key="filter_device"
                )
                selected_device = None if filter_device == "All" else filter_device
            
            with col2:
                # Date range filtering
                if date_range[0] and date_range[1]:
                    min_date = datetime.fromisoformat(date_range[0][:10])
                    max_date = datetime.fromisoformat(date_range[1][:10])
                    
                    filter_start_date = st.date_input(
                        "Start Date",
                        value=min_date,
                        min_value=min_date,
                        max_value=max_date,
                        key="filter_start_date"
                    )
                    
                    filter_end_date = st.date_input(
                        "End Date",
                        value=max_date,
                        min_value=min_date,
                        max_value=max_date,
                        key="filter_end_date"
                    )
                else:
                    filter_start_date = None
                    filter_end_date = None
                    st.info("No readings in database yet.")
                
                # Limit control
                display_limit = st.number_input(
                    "Display Limit",
                    min_value=10,
                    max_value=10000,
                    value=1000,
                    step=100,
                    help="Maximum number of rows to display",
                    key="display_limit"
                )
            
            # Load and display readings
            if st.button("🔄 Load Data", key="load_readings_btn", type="primary"):
                try:
                    with st.spinner("Loading readings..."):
                        start_date_str = filter_start_date.strftime("%Y-%m-%d") if filter_start_date else None
                        end_date_str = filter_end_date.strftime("%Y-%m-%d") if filter_end_date else None
                        
                        readings_df, total_count = viewer.get_readings_data(
                            plant_uid=selected_plant,
                            emig_id=selected_device,
                            start_date=start_date_str,
                            end_date=end_date_str,
                            limit=display_limit
                        )
                        
                        if readings_df.empty:
                            st.info("No readings found matching the selected filters.")
                        else:
                            st.success(f"✅ Loaded {len(readings_df)} readings (Total matching: {total_count:,})")
                            
                            if total_count > display_limit:
                                st.warning(f"⚠️ Showing {display_limit:,} of {total_count:,} matching readings. Adjust display limit to see more.")
                            
                            # Display the data
                            st.dataframe(readings_df, width='stretch', height=400)
                            
                            # Download option
                            csv = readings_df.to_csv(index=False).encode('utf-8')
                            st.download_button(
                                "📥 Download Readings Data (CSV)",
                                csv,
                                f"readings_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                                "text/csv",
                                key='download-readings'
                            )
                            
                            # Store data in session state for deletion
                            st.session_state['loaded_readings_filters'] = {
                                'plant_uid': selected_plant,
                                'emig_id': selected_device,
                                'start_date': start_date_str,
                                'end_date': end_date_str,
                                'total_count': total_count
                            }
                
                except Exception as e:
                    st.error(f"Error loading readings: {e}")
            
            # Delete readings functionality
            st.markdown("---")
            st.subheader("🗑️ Delete Readings")
            st.warning("⚠️ This action will permanently delete readings from the database. Use with caution!")
            
            if 'loaded_readings_filters' in st.session_state:
                filters = st.session_state['loaded_readings_filters']
                
                st.markdown("**Current filters will be used for deletion:**")
                if filters['plant_uid']:
                    st.write(f"- Plant: {filters['plant_uid']}")
                if filters['emig_id']:
                    st.write(f"- Device: {filters['emig_id']}")
                if filters['start_date']:
                    st.write(f"- Start Date: {filters['start_date']}")
                if filters['end_date']:
                    st.write(f"- End Date: {filters['end_date']}")
                
                st.write(f"- **Total readings to delete: {filters['total_count']:,}**")
                
                col1, col2 = st.columns([3, 1])
                with col1:
                    delete_confirm = st.checkbox(
                        "I understand this will permanently delete the data",
                        key="delete_confirm"
                    )
                with col2:
                    st.write("")  # Spacing
                    if st.button("🗑️ Delete Data", key="delete_readings_btn", type="secondary", disabled=not delete_confirm):
                        try:
                            deleted_count = viewer.delete_readings(
                                plant_uid=filters['plant_uid'],
                                emig_id=filters['emig_id'],
                                start_date=filters['start_date'],
                                end_date=filters['end_date']
                            )
                            st.success(f"✅ Deleted {deleted_count:,} readings successfully!")
                            # Clear session state
                            del st.session_state['loaded_readings_filters']
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error deleting readings: {e}")
            else:
                st.info("Load data first to see deletion options.")
        
        except Exception as e:
            st.error(f"Error: {e}")
