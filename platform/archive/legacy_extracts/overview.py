if selection == "Data Overview":
    from components.report_button import add_to_report_button
    st.header("Data Availability Overview")
    st.markdown("Heatmap of data availability per site and month. Select a row to take action on missing data.")

    # Fetch Data Summary
    with st.spinner("Loading data availability..."):
        df_summary = orch.get_data_availability_summary()
    
    if df_summary.empty:
        st.info("No data found in the database.")
    else:
        # --- Interactive Heatmap (Table) ---
        # Add visual indicators
        def make_status_col(val):
            return "✅" if val else "❌"

        df_display = df_summary.copy()
        df_display['API'] = df_display['API Data'].apply(make_status_col)
        df_display['POA'] = df_display['POA Data'].apply(make_status_col)
        
        # Display as interactive table
        st.dataframe(
            df_display[['Plant', 'Month', 'API', 'POA', 'api_count', 'poa_count']],
            use_container_width=True,
            selection_mode="single-row",
            on_select="rerun",
            key="data_overview_table"
        )

        # Add to Report button for data availability overview
        add_to_report_button(
            content=df_display[['Plant', 'Month', 'API', 'POA', 'api_count', 'poa_count']],
            title="Data Availability Overview",
            item_type='table',
            description=f"Data availability summary for {len(df_summary)} plant-month combinations",
            source_page="Data Overview",
            button_key="add_legacy_data_overview_table"
        )

        # --- Action Panel ---
        # Get selected row
        selection_state = st.session_state.get("data_overview_table")
        
        if selection_state and selection_state.get("selection") and selection_state["selection"]["rows"]:
            selected_idx = selection_state["selection"]["rows"][0]
            selected_row = df_display.iloc[selected_idx]
            
            st.divider()
            st.subheader(f"Actions for {selected_row['Plant']} - {selected_row['Month']}")
            
            # Action Tabs
            act_tab1, act_tab2 = st.tabs(["Force API Pull", "Manual POA Match"])
            
            plant_uid = selected_row['plant_uid']
            month_str = selected_row['Month'] # YYYY-MM
            
            # Helper to get start/end of month
            try:
                m_date = datetime.strptime(month_str, "%Y-%m")
                m_start = m_date
                # Last day of month
                if m_date.month == 12:
                    m_next = m_date.replace(year=m_date.year+1, month=1)
                else:
                    m_next = m_date.replace(month=m_date.month+1)
                m_end = m_next - timedelta(days=1)
            except:
                m_start = datetime.today()
                m_end = datetime.today()

            with act_tab1:
                st.markdown(f"**Missing API Data?** Force a refresh for this month.")
                c1, c2 = st.columns(2)
                f_start = c1.date_input("Start Date", value=m_start, key="force_start")
                f_end = c2.date_input("End Date", value=m_end, key="force_end")
                
                if st.button("📥 Fetch API Data", key="force_api_btn"):
                    try:
                        with st.spinner(f"Fetching data for {selected_row['Plant']}..."):
                            count = orch.fetch_data(plant_uid, f_start.strftime("%Y%m%d"), f_end.strftime("%Y%m%d"))
                            st.success(f"Fetched {count} readings.")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Error fetching data: {e}")

            with act_tab2:
                st.markdown(f"**Missing POA Data?** Manually assign a file.")
                if selected_row['POA Data']:
                    st.success("POA data is already present for this month.")
                
                st.markdown("Select an unmatched file from the scanned SolarGIS folders (configure in POA Import tab).")
                
                # We need to get unmatched files. 
                # Ideally, this should be cached or re-scanned. 
                # For responsiveness, let's try to reuse session state or quick scan if folder is known.
                root_folder_list = st.session_state.get('poa_folders', [])
                
                if root_folder_list:
                    # Quick scan for unmatched
                    files_info = orch.preview_bulk_poa_matches(root_folder_list, [])
                    unmatched_filenames = files_info.get('unmatched_files', [])
                    
                    if not unmatched_filenames:
                        st.info("No unmatched files found in current scan folder.")
                    else:
                        file_to_assign = st.selectbox("Select Unmatched File", options=["-- Select --"] + sorted([os.path.basename(f) for f in unmatched_filenames]))
                        
                        if file_to_assign != "-- Select --":
                            # Find full path
                            full_path = next((f for f in unmatched_filenames if os.path.basename(f) == file_to_assign), None)
                            if full_path:
                                st.markdown(f"Assigning **{file_to_assign}** to **{selected_row['Plant']}**")
                                if st.button("🚀 Import & Link File", key="manual_link_btn"):
                                    try:
                                        # Use bulk import logic for single file
                                        # Assuming file covers the needed range, or just import all of it
                                        mapping = {full_path: {'alias': selected_row['Plant'], 'folder': os.path.dirname(full_path)}}
                                        
                                        with st.spinner("Importing..."):
                                            # Dummy dates as import ignores them usually for file-based
                                            res = orch.bulk_import_poa(mapping, "20000101", "20301231")
                                            st.success(f"Imported {res.get(full_path, 0)} readings.")
                                            st.rerun()
                                    except Exception as e:
                                        st.error(f"Import failed: {e}")
                else:
                    st.warning("No POA folder selected. Go to 'POA Import' tab -> 'From Folder Path' and select a root folder first.")


# --- PAGE 5: Database Viewer ---
if selection == "Database Viewer":
    st.header("Database Viewer")
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
