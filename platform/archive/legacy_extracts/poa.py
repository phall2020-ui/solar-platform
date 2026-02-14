if selection == "POA Import":
    st.header("Import SolarGIS POA Data")
    st.markdown("""
    Import POA (Plane of Array) irradiance data from SolarGIS CSV files. 
    POA data covers the entire system and will be stored separately from inverter readings 
    but can be joined for analysis using aligned timestamps.
    """)
    
    # Create sub-tabs for single and bulk import
    import_mode = st.radio("Import Mode", ["Upload File(s)", "From Folder Path"], horizontal=True)
    
    if import_mode == "Upload File(s)":
        with st.container(border=True):
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
    
    else:  # From Root Folder Path
        with st.container(border=True):
            st.markdown("""
            Import POA data from a single root folder. 
            1️⃣ Select the root folder – all sub‑folders will be scanned recursively.
            2️⃣ System automatically matches files to plants based on POA Device ID.
            3️⃣ Review matches (multiple files per plant are allowed) and confirm import.
            """)
        
        # Initialize session state for root folder (list for compatibility)
        col_browse, col_clear = st.columns([1, 1])
        with col_browse:
            if st.button("📂 Select Root Folder", use_container_width=True):
                try:
                    import subprocess
                    ps_script = """
                    Add-Type -AssemblyName System.Windows.Forms
                    $f = New-Object System.Windows.Forms.FolderBrowserDialog
                    $f.ShowNewFolderButton = $false
                    if ($f.ShowDialog() -eq 'OK') {
                        return $f.SelectedPath
                    }
                    """
                    result = subprocess.run([
                        "powershell",
                        "-Command",
                        ps_script], capture_output=True, text=True,
                        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
                    selected_path = result.stdout.strip()
                    if selected_path:
                        norm_path = os.path.normpath(selected_path)
                        if os.path.isdir(norm_path):
                            st.session_state['poa_folders'] = [norm_path]
                            st.rerun()
                        else:
                            st.error("Invalid folder path selected.")
                except Exception as e:
                    st.error(f"Error opening folder picker: {e}")
        with col_clear:
            if st.button("🗑️ Clear Folder", use_container_width=True):
                st.session_state['poa_folders'] = []
                for key in ['poa_preview_data', 'poa_import_ready', 'poa_matched_plants']:
                    if key in st.session_state:
                        del st.session_state[key]
                st.rerun()

        if st.session_state.get('poa_folders'):
            root_folder = st.session_state['poa_folders'][0]
            st.success(f"Root folder: {root_folder}")
        else:
            st.info("No root folder selected. Click **Select Root Folder** to begin.")
        # Plant selection
        st.subheader("🏭 Step 2: Select Plants to Match")
        if not plant_aliases:
            st.warning("No plants registered.")
        else:
            selected_plants = st.multiselect(
                "Select plants to match against",
                options=plant_aliases,
                default=plant_aliases,
                key="poa_selected_plants_multiselect"
            )

            st.markdown("---")
            st.subheader("📋 Step 3: Scan & Import")
            
            with st.form("poa_folder_import_form"):
                col1, col2 = st.columns(2)
                start_date = col1.date_input("Start Date (Optional override)", value=datetime.today() - timedelta(days=365))
                end_date = col2.date_input("End Date (Optional override)", value=datetime.today())
                
                scan_btn = st.form_submit_button("🔎 Scan for Matches")
            
            if scan_btn:
                clear_logs()
                if not root_folder:
                     st.error("Select a root folder first.")
                elif not selected_plants:
                     st.error("Select at least one plant.")
                else:
                    with st.spinner("Scanning subfolders..."):
                        # Pass list containing the single root folder
                        preview_data = orch.preview_bulk_poa_matches([root_folder], selected_plants)
                        st.session_state['poa_preview_data'] = preview_data
                        st.session_state['poa_import_ready'] = True

    # Confirmation UI
    if st.session_state.get('poa_import_ready') and 'poa_preview_data' in st.session_state:
        preview_data = st.session_state['poa_preview_data']
        # matched_files now contains ALL files, some with alias=None
        matched_files = preview_data.get('matched_files', {})
        matched_plants = preview_data.get('plants_matched_against', plant_aliases)
        
        # Calculate stats
        total_files = len(matched_files)
        auto_matched = sum(1 for info in matched_files.values() if info.get('alias'))
        unmatched_count = total_files - auto_matched

        st.divider()
        st.subheader("Match Confirmation")
        
        col_stat1, col_stat2 = st.columns(2)
        col_stat1.metric("Files Found", total_files)
        col_stat2.metric("Auto-Matched", auto_matched)

        if not matched_files:
            st.warning("No CSV files found in the selected folder.")
        else:
            # Flatten matched_files (keyed by full_path) into list
            all_files = []
            for full_path, info in matched_files.items():
                short_filename = info.get('filename', os.path.basename(full_path))
                current_alias = info.get('alias')
                all_files.append({
                    'filename': short_filename,
                    'full_path': full_path,
                    'alias': current_alias,
                    'folder': info['folder'],
                    'poa_device_id': info.get('poa_device_id', '') if current_alias else ''
                })
            
            # Sort: Unmatched first, then by filename
            all_files.sort(key=lambda x: (0 if x['alias'] is None else 1, x['filename']))

            with st.form("poa_final_confirm"):
                st.write(f"Review matches. Use the dropdown to manually assign plants for unmatched files or correct auto-matches.")
                
                # Display matches table-style
                for i, f in enumerate(all_files):
                    c1, c2, c3 = st.columns([3, 2, 2])
                    
                    fname = f['filename']
                    current_alias = f['alias']
                    folder = f['folder']
                    
                    with c1:
                        icon = "✅" if current_alias else "⚠️"
                        # Highlight unmatched files
                        if not current_alias:
                            st.markdown(f"**{icon} {fname}**")
                        else:
                            st.write(f"{icon} {fname}")
                        st.caption(f"📁 ...{folder[-30:] if len(folder)>30 else folder}")
                    
                    with c2:
                        st.markdown("→")
                        
                    with c3:
                        # Dropdown to select/change plant
                        options = ["-- Skip --"] + matched_plants
                        default_idx = 0
                        if current_alias and current_alias in matched_plants:
                            default_idx = matched_plants.index(current_alias) + 1
                        
                        selected = st.selectbox(
                            "Assign Plant", 
                            options=options, 
                            index=default_idx, 
                            key=f"confirm_map_{i}",
                            label_visibility="collapsed"
                        )
                    
                    # Store selected alias in f for processing later (though form submit handles real logic)
                    
                    # Separator
                    if i < len(all_files) - 1:
                        st.divider()

                st.markdown("---")
                if st.form_submit_button("🚀 Import Confirmed Files", type="primary"):
                     final_map = {}
                     for i, f in enumerate(all_files):
                         # Get value from widget key
                         selected = st.session_state.get(f"confirm_map_{i}")
                         
                         if selected and selected != "-- Skip --":
                             final_map[f['full_path']] = {
                                 'alias': selected,
                                 'folder': f['folder']
                             }
                     
                     if final_map:
                         with st.spinner("Importing..."):
                             s_str = start_date.strftime("%Y%m%d")
                             e_str = end_date.strftime("%Y%m%d")
                             results = orch.bulk_import_poa(final_map, s_str, e_str)
                             
                             total = sum(results.values())
                             st.success(f"✅ Imported {total} readings from {len(results)} files.")
                             with st.expander("Details"):
                                 for k, v in results.items():
                                     st.write(f"{os.path.basename(k)}: {v} readings")
                             
                             # Cleanup
                             del st.session_state['poa_preview_data']
                             del st.session_state['poa_import_ready']
                             st.rerun()
                     else:
                         st.warning("No files selected.")
# --- PAGE 3: Fouling Analysis ---
