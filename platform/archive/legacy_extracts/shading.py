if selection == "Shading Analysis":
    from components.report_button import add_to_report_button
    st.header("Shading Analysis")
    st.markdown("""
    **Summer baseline** is automatically selected (Jun-Aug for Northern Hemisphere). 
    Select a **comparison period** (typically winter months) to analyze shading impact.
    """)
    
    # Data source selection
    with st.container(border=True):
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
                    
                    # Helper to get available months
                    def get_available_months(min_d, max_d):
                        months = []
                        curr = min_d.replace(day=1)
                        while curr <= max_d:
                            months.append(curr.strftime("%Y-%m"))
                            # Move to next month
                            next_month = curr.replace(day=28) + timedelta(days=4)
                            curr = next_month.replace(day=1)
                        return months

                    available_months = get_available_months(min_date, max_date)
                    
                    if not available_months:
                        st.error("Not enough data to select months.")
                    else:
                        # --- Month Selector Component ---
                        def render_month_selector(label, available_months_list, key_prefix, default_months=None):
                            st.subheader(label)
                            
                            # Get available years
                            years = sorted(list(set([m.split("-")[0] for m in available_months_list])))
                            
                            if not years:
                                st.warning("No data available.")
                                return []
                                
                            # Year selection
                            selected_year = st.selectbox(f"Select Year ({label})", years, key=f"{key_prefix}_year")
                            
                            # Month grid
                            st.markdown(f"**Select Months for {selected_year}:**")
                            
                            # Initialize session state for this selector if not exists
                            if f"{key_prefix}_selected" not in st.session_state:
                                st.session_state[f"{key_prefix}_selected"] = default_months if default_months else []
                            
                            # Create 3x4 grid
                            cols = st.columns(4)
                            month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
                            
                            current_selection = st.session_state[f"{key_prefix}_selected"]
                            
                            for i, m_name in enumerate(month_names):
                                month_num = i + 1
                                month_str = f"{selected_year}-{month_num:02d}"
                                
                                is_available = month_str in available_months_list
                                is_selected = month_str in current_selection
                                
                                with cols[i % 4]:
                                    # Checkbox for each month
                                    if st.checkbox(
                                        m_name, 
                                        value=is_selected, 
                                        disabled=not is_available,
                                        key=f"{key_prefix}_{month_str}"
                                    ):
                                        if month_str not in current_selection:
                                            current_selection.append(month_str)
                                    else:
                                        if month_str in current_selection:
                                            current_selection.remove(month_str)
                            
                            # Update session state
                            st.session_state[f"{key_prefix}_selected"] = sorted(list(set(current_selection)))
                            
                            # Display current selection across all years
                            if current_selection:
                                st.caption(f"Selected: {', '.join(sorted(current_selection))}")
                            else:
                                st.caption("No months selected.")
                                
                            return sorted(current_selection)

                        # Auto-detect defaults
                        current_year = max_date.year
                        
                        # Default Summer: Jun-Aug
                        default_summer = []
                        for y in [current_year, current_year - 1]:
                            s_months = [f"{y}-06", f"{y}-07", f"{y}-08"]
                            if any(m in available_months for m in s_months):
                                default_summer = [m for m in s_months if m in available_months]
                                break
                        
                        # Default Winter: Oct-Dec
                        default_winter = []
                        for y in [current_year, current_year - 1]:
                            w_months = [f"{y}-10", f"{y}-11", f"{y}-12"]
                            if any(m in available_months for m in w_months):
                                default_winter = [m for m in w_months if m in available_months]
                                break
                                
                        st.markdown("---")
                        with st.container(border=True):
                            baseline_months = render_month_selector(
                                "☀️ Baseline Period (Summer)", 
                                available_months, 
                                "baseline", 
                                default_months=default_summer
                            )
                        
                        st.markdown("---")
                        with st.container(border=True):
                            compare_months = render_month_selector(
                                "❄️ Comparison Period (Winter/Shaded)", 
                                available_months, 
                                "compare", 
                                default_months=default_winter
                            )
                        
                        if not baseline_months:
                            st.warning("Please select at least one baseline month.")
                        if not compare_months:
                            st.warning("Please select at least one comparison month.")
                        
                        if baseline_months and compare_months:
                            # Calculate overall start/end for display
                            all_selected = sorted(baseline_months + compare_months)
                            min_sel = all_selected[0]
                            max_sel = all_selected[-1]
                            st.info(f"Analysis will consider selected months between {min_sel} and {max_sel}.")
                    
                    output_base = st.text_input("Output Filename Base", "shading_report", key="shading_output_db")
                    
                    # Check for missing inverter data before analysis
                    with st.expander("⚙️ Data Completeness Check", expanded=False):
                        if st.button("🔎 Check for Missing Inverter Data", key="check_missing_inv"):
                            with st.spinner("Checking registered inverters vs database..."):
                                check_result = orch.check_missing_inverters_by_uid(
                                    plant_uid=shading_plant,
                                    auto_fetch=False
                                )
                                
                                if check_result.get('status') == 'error':
                                    st.error(check_result.get('error', 'Unknown error'))
                                elif check_result.get('status') == 'ok':
                                    st.success(f"✅ All {check_result['registered_count']} registered inverters have data in the database.")
                                else:
                                    st.warning(f"⚠️ Found {len(check_result['missing_inverters'])} inverter(s) without data:")
                                    st.code("\n".join(check_result['missing_inverters']))
                                    st.info(f"📊 {check_result['with_data_count']} of {check_result['registered_count']} inverters have data")
                                    
                                    # Store in session state for fetch button
                                    st.session_state['missing_inv_check'] = check_result
                        
                        # Show fetch button if missing inverters were detected
                        if st.session_state.get('missing_inv_check', {}).get('status') == 'missing':
                            if st.button("📥 Fetch Missing Inverter Data from API", key="fetch_missing_inv"):
                                with st.spinner("Fetching data from API... This may take a few minutes."):
                                    fetch_result = orch.check_missing_inverters_by_uid(
                                        plant_uid=shading_plant,
                                        auto_fetch=True
                                    )
                                    if fetch_result.get('fetched_count', 0) > 0:
                                        st.success(f"✅ Fetched {fetch_result['fetched_count']} readings for missing inverters!")
                                        st.session_state['missing_inv_check'] = {}  # Clear the check state
                                        st.rerun()
                                    else:
                                        st.error("Failed to fetch data. Check API key configuration and logs.")
                    
                    if st.button("🔍 Run Shading Analysis", key="run_shading_db", type="primary"):
                        clear_logs()
                        
                        try:
                            with st.spinner("Loading data and analyzing shading patterns..."):
                                # Check for missing inverters automatically and offer to fetch
                                check_result = orch.check_missing_inverters_by_uid(plant_uid=shading_plant, auto_fetch=False)
                                if check_result.get('status') == 'missing':
                                    missing_count = len(check_result['missing_inverters'])
                                    st.warning(f"⚠️ {missing_count} inverter(s) have no data in database. Use the 'Data Completeness Check' above to fetch missing data.")
                                
                                # Get inverter devices for the plant
                                all_devices = viewer.get_unique_device_ids(shading_plant)
                                inverter_devices = [d for d in all_devices if d.startswith("INVERT:")]
                                
                                # ...existing code...
                                
                                if not inverter_devices:
                                    st.error("No inverter data found for this plant.")
                                else:
                                    # Helper to filter dataframe by selected months
                                    def filter_by_months(df, selected_months, time_col='ts'):
                                        if df.empty:
                                            return df
                                        df = df.copy()  # Ensure we don't modify original
                                        
                                        # Convert to string first, handling NaN
                                        df[time_col] = df[time_col].fillna('').astype(str)
                                        # Remove trailing Z
                                        df[time_col] = df[time_col].str.replace('Z', '', regex=False)
                                        # Remove +00:00 timezone suffix
                                        df[time_col] = df[time_col].str.replace(r'\+00:00$', '', regex=True)
                                        
                                        # Replace empty strings with NaT
                                        df.loc[df[time_col] == '', time_col] = pd.NaT
                                        
                                        # Parse datetimes with format='mixed' to handle different formats 
                                        # (with/without microseconds)
                                        df[time_col] = pd.to_datetime(df[time_col], errors='coerce', format='mixed')
                                        
                                        # Drop rows where conversion failed
                                        df = df[df[time_col].notna()]
                                        
                                        # Create a mask for selected months
                                        mask = pd.Series(False, index=df.index)
                                        for m_str in selected_months:
                                            y, m = map(int, m_str.split('-'))
                                            mask |= ((df[time_col].dt.year == y) & (df[time_col].dt.month == m))
                                        return df[mask]

                                    # Load baseline (summer) data
                                    # We need to load the full range covered by selected months to be safe, then filter
                                    b_min = min(baseline_months)
                                    b_max = max(baseline_months)
                                    # Convert to dates for query
                                    b_start_date = datetime.strptime(b_min, "%Y-%m")
                                    # End date is end of max month
                                    b_max_dt = datetime.strptime(b_max, "%Y-%m")
                                    b_end_date = (b_max_dt.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
                                    
                                    baseline_df_raw, _ = viewer.get_readings_data(
                                        plant_uid=shading_plant,
                                        start_date=b_start_date.strftime("%Y-%m-%d"),
                                        end_date=b_end_date.strftime("%Y-%m-%d"),
                                        limit=100000
                                    )
                                    
                                    # Filter to exact selected months
                                    baseline_df = filter_by_months(baseline_df_raw.copy(), baseline_months)
                                    
                                    # Load comparison (winter) data
                                    c_min = min(compare_months)
                                    c_max = max(compare_months)
                                    c_start_date = datetime.strptime(c_min, "%Y-%m")
                                    c_max_dt = datetime.strptime(c_max, "%Y-%m")
                                    c_end_date = (c_max_dt.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
                                    
                                    compare_df_raw, _ = viewer.get_readings_data(
                                        plant_uid=shading_plant,
                                        start_date=c_start_date.strftime("%Y-%m-%d"),
                                        end_date=c_end_date.strftime("%Y-%m-%d"),
                                        limit=100000
                                    )
                                    
                                    # Filter to exact selected months
                                    compare_df = filter_by_months(compare_df_raw.copy(), compare_months)
                                    
                                    # ...existing code...
                                    
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
                                            
                                            # Calculate hourly profiles per inverter using the shading analysis module
                                            from solar_toolkit.shading_analysis import analyze_from_dataframes, ShadingSettings, generate_plots
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
                                            
                                            # Generate PDF report
                                            pdf_path = f"{output_base}.pdf"
                                            
                                            # Create config for plotting
                                            plot_cfg = ShadingSettings()
                                            plot_cfg.emigid_col = 'emig_id'
                                            plot_cfg.core_hours_start = 9.0
                                            plot_cfg.core_hours_end = 15.0
                                            # Look up plant alias from plant_uid for the report title
                                            plant_alias = orch.store.find_alias_by_uid(shading_plant)
                                            if plant_alias:
                                                plot_cfg.plant_name = plant_alias
                                            # Generate the plots
                                            generate_plots(merged, summary, pdf_path, plot_cfg)
                                            
                                            # PDF download button (after analysis, before plots)
                                            if os.path.exists(pdf_path):
                                                with open(pdf_path, "rb") as pdf_file:
                                                    st.download_button(
                                                        label="📥 Download Shading Analysis PDF",
                                                        data=pdf_file.read(),
                                                        file_name=os.path.basename(pdf_path),
                                                        mime="application/pdf"
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
                                                    # Round Estimated Loss (%) to 1 decimal place
                                                    if 'Estimated Loss (%)' in display_summary.columns:
                                                        display_summary['Estimated Loss (%)'] = display_summary['Estimated Loss (%)'].round(1)
                                                    display_summary = display_summary[available_cols].sort_values('Estimated Loss (%)', ascending=False)
                                                    
                                                    st.dataframe(display_summary, use_container_width=True, hide_index=True)

                                                    # Add to Report button for summary table
                                                    add_to_report_button(
                                                        content=display_summary,
                                                        title="Shading Loss Summary",
                                                        item_type='table',
                                                        description="Inverter-level shading loss summary with classification",
                                                        source_page="Shading Analysis",
                                                        button_key=f"add_shading_summary_{shading_plant}_{'-'.join(baseline_months[:2])}_to_{'-'.join(compare_months[-1:])}"
                                                    )

                                                    # Highlight inverters with significant shading
                                                    severe = summary[summary['classification'] == 'Severe Shading']
                                                    moderate = summary[summary['classification'] == 'Moderate Shading']

                                                    if not severe.empty:
                                                        st.error(f"🔴 {len(severe)} inverter(s) have SEVERE shading (>30% loss)")
                                                    if not moderate.empty:
                                                        st.warning(f"🟠 {len(moderate)} inverter(s) have MODERATE shading (15-30% loss)")

                                                    # --- Total Shading Loss and Percentage ---
                                                    if 'total_loss_kwh' in summary.columns and 'total_energy_kwh' in summary.columns:
                                                        total_loss = summary['total_loss_kwh'].sum()
                                                        total_gen = summary['total_energy_kwh'].sum()
                                                        # Calculate percentage, avoid division by zero
                                                        pct_loss = (total_loss / total_gen * 100) if total_gen > 0 else 0
                                                        st.info(f"**Total shading loss during the period:** {total_loss:,.1f} kWh\n**Percentage of total generation:** {pct_loss:.1f}%")
                                                        st.markdown("### ⚡ Estimated Daily kWh Loss per Inverter")
                                                        import matplotlib.pyplot as plt
                                                        import numpy as np
                                                        from solar_toolkit.shading_analysis import ShadingSettings
                                                        cfg = ShadingSettings()
                                                        cfg.emigid_col = 'emig_id' if 'emig_id' in summary.columns else 'emigId'
                                                        data = summary.dropna(subset=["estimated_loss_kwh_per_day"]).copy()
                                                        if not data.empty:
                                                            data = data.sort_values("estimated_loss_kwh_per_day", ascending=False)
                                                            # Round loss to 1 decimal place for display
                                                            data["estimated_loss_kwh_per_day"] = data["estimated_loss_kwh_per_day"].round(1)
                                                            fig, ax = plt.subplots(figsize=(12, 5))
                                                            ax.bar(
                                                                data[cfg.emigid_col].astype(str),
                                                                data["estimated_loss_kwh_per_day"]
                                                            )
                                                            ax.set_title("Estimated Daily kWh Loss per Inverter")
                                                            ax.set_xlabel("Inverter ID")
                                                            ax.set_ylabel("Estimated Loss [kWh/day]")
                                                            ax.grid(axis="y", linestyle="--", alpha=0.4)
                                                            plt.xticks(rotation=90)
                                                            plt.tight_layout()
                                                            st.pyplot(fig)

                                                            # Add to Report button for bar chart
                                                            add_to_report_button(
                                                                content=fig,
                                                                title="Estimated Daily kWh Loss per Inverter",
                                                                item_type='chart',
                                                                description="Bar chart showing daily energy loss due to shading per inverter",
                                                                source_page="Shading Analysis",
                                                                width=12.0,
                                                                height=5.0,
                                                                button_key=f"add_shading_loss_chart_{shading_plant}"
                                                            )

                                                            plt.close(fig)

                                                    # --- Matplotlib Graphs: Per-Inverter and Heatmap ---
                                                    import matplotlib.pyplot as plt
                                                    from matplotlib.backends.backend_pdf import PdfPages
                                                    import numpy as np
                                                    # --- Site-wide Heatmap ---
                                                    st.markdown("### 🌡️ Site-wide Ratio Heatmap")
                                                    cfg = ShadingSettings()
                                                    cfg.emigid_col = 'emig_id' if 'emig_id' in merged.columns else 'emigId'
                                                    if not merged.empty:
                                                        pivot = merged.pivot(index=cfg.emigid_col, columns="hour_float", values="ratio")
                                                        fig_h = max(4, len(pivot.index) * 0.3)
                                                        fig, ax = plt.subplots(figsize=(12, fig_h))
                                                        im = ax.imshow(pivot.values, aspect="auto", origin="lower", vmin=0.6, vmax=1.05)
                                                        ax.set_yticks(np.arange(len(pivot.index)))
                                                        ax.set_yticklabels(pivot.index)
                                                        ax.set_xticks(np.arange(len(pivot.columns)))
                                                        ax.set_xticklabels([f"{h:.1f}" for h in pivot.columns], rotation=90)
                                                        ax.set_xlabel("Hour of Day")
                                                        ax.set_ylabel("Inverter ID")
                                                        ax.set_title("Winter / Summer Efficiency Ratio Heatmap")
                                                        cbar = fig.colorbar(im, ax=ax)
                                                        cbar.set_label("Ratio (Winter / Summer)")
                                                        # Dynamically scale axes to show all data
                                                        if len(pivot.columns) > 0:
                                                            ax.set_xlim(-0.5, len(pivot.columns)-0.5)
                                                        if len(pivot.index) > 0:
                                                            ax.set_ylim(-0.5, len(pivot.index)-0.5)
                                                        st.pyplot(fig)

                                                        # Add to Report button for heatmap
                                                        add_to_report_button(
                                                            content=fig,
                                                            title="Winter / Summer Efficiency Ratio Heatmap",
                                                            item_type='chart',
                                                            description="Heatmap showing hourly efficiency ratios across all inverters",
                                                            source_page="Shading Analysis",
                                                            width=12.0,
                                                            height=6.0,
                                                            button_key=f"add_shading_heatmap_{shading_plant}"
                                                        )

                                                        plt.close(fig)

                                                st.markdown("### 📊 Per-Inverter Efficiency & Ratio Graphs")
                                                inverter_ids = merged[cfg.emigid_col].unique()
                                                for inv_id in inverter_ids:
                                                    inv_data = merged[merged[cfg.emigid_col] == inv_id]
                                                    if len(inv_data) < 4:
                                                        continue
                                                    fig, ax = plt.subplots(figsize=(10, 5))
                                                    ax.plot(inv_data["hour_float"], inv_data["eff_median_summer"], color='orange', marker='o', label='Summer (Baseline)', linewidth=2)
                                                    ax.plot(inv_data["hour_float"], inv_data["eff_median_winter"], color='blue', marker='x', linestyle='--', label='Winter (Observed)')
                                                    ax.fill_between(inv_data["hour_float"], inv_data["eff_median_summer"], inv_data["eff_median_winter"], where=(inv_data["eff_median_winter"] < inv_data["eff_median_summer"]), interpolate=True, color='red', alpha=0.2, label='Energy Loss')
                                                    
                                                    # Get kWh loss if available
                                                    loss_str = ""
                                                    if "estimated_loss_kwh_per_day" in summary.columns:
                                                        row = summary[summary[cfg.emigid_col] == inv_id]
                                                        if not row.empty and pd.notna(row.iloc[0]["estimated_loss_kwh_per_day"]):
                                                            loss_val = round(row.iloc[0]["estimated_loss_kwh_per_day"], 1)
                                                            loss_str = f" | Loss: ~{loss_val} kWh/day"
                                                    
                                                    ax.set_title(f"Inverter: {inv_id} - Efficiency Comparison{loss_str}")
                                                    ax.set_xlabel("Hour of Day (24h)")
                                                    ax.set_ylabel("Normalized Efficiency (W / W/m²)")
                                                    # Dynamically scale x and y axes to show all data
                                                    if len(inv_data["hour_float"]) > 0:
                                                        min_x = inv_data["hour_float"].min()
                                                        max_x = inv_data["hour_float"].max()
                                                        ax.set_xlim(min_x, max_x)
                                                    if len(inv_data[["eff_median_summer", "eff_median_winter"]].values.flatten()) > 0:
                                                        min_y = np.nanmin(inv_data[["eff_median_summer", "eff_median_winter"]].values)
                                                        max_y = np.nanmax(inv_data[["eff_median_summer", "eff_median_winter"]].values)
                                                        ax.set_ylim(min_y, max_y)
                                                    ax.grid(True, linestyle=':', alpha=0.6)
                                                    ax.legend()
                                                    st.pyplot(fig)

                                                    # Add to Report button for efficiency comparison chart
                                                    add_to_report_button(
                                                        content=fig,
                                                        title=f"Inverter {inv_id} - Efficiency Comparison",
                                                        item_type='chart',
                                                        description=f"Summer vs Winter efficiency comparison for inverter {inv_id}",
                                                        source_page="Shading Analysis",
                                                        width=10.0,
                                                        height=5.0,
                                                        button_key=f"add_shading_eff_{shading_plant}_{inv_id}"
                                                    )

                                                    plt.close(fig)
                                                    # Ratio plot
                                                    fig2, ax2 = plt.subplots(figsize=(10, 4))
                                                    ax2.plot(inv_data["hour_float"], inv_data["ratio"], color='red', marker='.', label='Winter/Summer Ratio')
                                                    ax2.axhline(1.0, color='green', linestyle='-', linewidth=1, label="No Loss (Ratio = 1.0)")
                                                    ax2.axhline(0.9, color='orange', linestyle='--', linewidth=1, label="10% Loss")
                                                    ax2.axhline(0.8, color='red', linestyle='--', linewidth=1, label="20% Loss")
                                                    ax2.set_title(f"Inverter: {inv_id} - Shading Loss Ratio (Winter/Summer)")
                                                    ax2.set_xlabel("Hour of Day (24h)")
                                                    ax2.set_ylabel("Efficiency Ratio")
                                                    # Dynamically scale x and y axes to show all data
                                                    if len(inv_data["hour_float"]) > 0:
                                                        min_x = inv_data["hour_float"].min()
                                                        max_x = inv_data["hour_float"].max()
                                                        ax2.set_xlim(min_x, max_x)
                                                    if len(inv_data["ratio"]) > 0:
                                                        min_y = np.nanmin(inv_data["ratio"].values)
                                                        max_y = np.nanmax(inv_data["ratio"].values)
                                                        ax2.set_ylim(min_y, max_y)
                                                    ax2.grid(True, linestyle=':', alpha=0.6)
                                                    ax2.legend()
                                                    st.pyplot(fig2)

                                                    # Add to Report button for ratio plot
                                                    add_to_report_button(
                                                        content=fig2,
                                                        title=f"Inverter {inv_id} - Shading Loss Ratio",
                                                        item_type='chart',
                                                        description=f"Winter/Summer ratio showing shading loss for inverter {inv_id}",
                                                        source_page="Shading Analysis",
                                                        width=10.0,
                                                        height=4.0,
                                                        button_key=f"add_shading_ratio_{shading_plant}_{inv_id}"
                                                    )

                                                    plt.close(fig2)

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
                        # PDF download button
                        pdf_path = f"{output_base}.pdf"
                        if os.path.exists(pdf_path):
                            with open(pdf_path, "rb") as pdf_file:
                                st.download_button(
                                    label="📥 Download Shading Analysis PDF",
                                    data=pdf_file.read(),
                                    file_name=os.path.basename(pdf_path),
                                    mime="application/pdf"
                                )

                except Exception as e:
                    st.error(f"Error during shading analysis: {e}")
                finally:
                    if temp_sum_path and os.path.exists(temp_sum_path): os.remove(temp_sum_path)
                    if temp_win_path and os.path.exists(temp_win_path): os.remove(temp_win_path)
                    display_logs() 
                    
# --- PAGE: Clipping Analysis ---
