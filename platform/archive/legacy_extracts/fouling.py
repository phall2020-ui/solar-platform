if selection == "Fouling Analysis":
    from components.report_button import add_to_report_button
    st.header("Fouling (Soiling) Analysis")
    st.markdown("Computes the Fouling Index using the auto-clean period method (compares current PR to baseline PR).")
    
    # Data Source Selection
    fouling_source = st.radio("Data Source", ["Use Database Data", "Upload CSV"], horizontal=True)
    
    with st.form("fouling_form", border=True):
        col_cfg1, col_cfg2 = st.columns(2)
        
        with col_cfg1:
            if fouling_source == "Use Database Data":
                # Plant Selection
                f_plant_alias = st.selectbox(
                    "Select Plant", 
                    options=plant_aliases,
                    index=plant_aliases.index(selected_alias) if selected_alias in plant_aliases else 0
                )
                f_plant_uid = next((p['plant_uid'] for p in plant_list if p['alias'] == f_plant_alias), None)
                
                # Date Range
                f_start_date = st.date_input("Analysis Start Date", value=datetime.today() - timedelta(days=90))
                f_end_date = st.date_input("Analysis End Date", value=datetime.today())
                
                uploaded_file = None
            else:
                uploaded_file = st.file_uploader("Upload Combined Operational Data CSV", type="csv")
                f_plant_uid = None
                f_start_date = None
                f_end_date = None

        with col_cfg2:
            default_dc_size = 1000.0
            if fouling_source == "Use Database Data" and f_plant_alias:
                p_rec = next((p for p in plant_list if p['alias'] == f_plant_alias), None)
                if p_rec and p_rec.get('dc_size_kw'):
                    default_dc_size = float(p_rec['dc_size_kw'])
            
            dc_size = st.number_input("DC Size (kW)", value=default_dc_size, min_value=1.0)
            
            # Clean Period Configuration
            clean_mode = st.radio("Clean Period Selection", ["Manual Range", "Auto-Detect"], horizontal=True)
            
            if clean_mode == "Auto-Detect":
                auto_days = st.slider("Auto-Clean Period Length (days)", min_value=1, max_value=30, value=3)
                manual_clean_start = None
                manual_clean_end = None
            else:
                auto_days = 3
                c_col1, c_col2 = st.columns(2)
                manual_clean_start = c_col1.date_input("Clean Start", value=datetime.today() - timedelta(days=80))
                manual_clean_end = c_col2.date_input("Clean End", value=datetime.today() - timedelta(days=77))

        submitted = st.form_submit_button("Run Fouling Analysis")

        if submitted:
            clear_logs()
            try:
                result = None
                with st.spinner(f"Running analysis (DC Size: {dc_size} kW)..."):
                    if fouling_source == "Upload CSV":
                        if uploaded_file is None:
                            st.error("Please upload a CSV file.")
                        else:
                            # Save uploaded file temporarily
                            with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp_file:
                                tmp_file.write(uploaded_file.getbuffer())
                                temp_path = tmp_file.name
                            result = orch.run_fouling_auto(temp_path, dc_size, auto_days)
                            os.unlink(temp_path)
                    else: # Database
                        if not f_plant_uid:
                            st.error("Please select a valid plant.")
                        else:
                            # Format dates
                            s_str = f_start_date.strftime("%Y%m%d")
                            e_str = f_end_date.strftime("%Y%m%d")
                            c_start_str = manual_clean_start.strftime("%Y%m%d") if manual_clean_start else None
                            c_end_str = manual_clean_end.strftime("%Y%m%d") if manual_clean_end else None
                            result = orch.run_fouling_analysis_from_db(
                                plant_uid=f_plant_uid,
                                start_date=s_str,
                                end_date=e_str,
                                dc_size=dc_size,
                                auto_days=auto_days,
                                clean_start=c_start_str,
                                clean_end=c_end_str
                            )
                if result:
                    st.success(f"✅ Analysis complete! Used power column: `{result['power_col_used']}`")
                    # Metrics
                    col_idx, col_lvl = st.columns(2)
                    col_idx.metric("Median Fouling Index", f"{result['fouling_index']:.4f}")
                    col_lvl.metric("Fouling Level", result['fouling_level'])
                    
                    df_res = result['df_result']
                    
                    # Create tabs for different visualizations
                    tab_trend, tab_scatter, tab_daily = st.tabs(["📈 Trend Over Time", "🔵 PR vs Irradiance", "📊 Daily Summary"])
                    
                    with tab_trend:
                        st.subheader("Fouling Index Trend")
                        # Sort by timestamp for time series
                        df_trend = df_res.copy().sort_values('ts')
                        
                        # Rolling average for smoother trend
                        df_trend['fouling_index_rolling'] = df_trend['fouling_index'].rolling(window=20, min_periods=1).mean()
                        
                        # Sample if too large
                        if len(df_trend) > 5000:
                            df_trend = df_trend.iloc[::len(df_trend)//5000 + 1]
                        
                        # Calculate dynamic Y-axis range based on data
                        y_min = max(0, df_trend['fouling_index'].min() - 0.1)
                        y_max = min(2.5, df_trend['fouling_index'].max() + 0.1)
                        
                        # Line chart with rolling average
                        trend_line = alt.Chart(df_trend).mark_line(color='#1f77b4', strokeWidth=2).encode(
                            x=alt.X('ts:T', title='Date'),
                            y=alt.Y('fouling_index_rolling:Q', title='Fouling Index (Rolling Avg)', scale=alt.Scale(domain=[y_min, y_max]))
                        )
                        
                        # Scatter points (lighter)
                        trend_points = alt.Chart(df_trend).mark_circle(size=20, opacity=0.3).encode(
                            x=alt.X('ts:T'),
                            y=alt.Y('fouling_index:Q', scale=alt.Scale(domain=[y_min, y_max])),
                            color=alt.Color('fouling_index:Q', scale=alt.Scale(scheme='redyellowgreen', domain=[0.5, 1.2]), legend=None)
                        )
                        
                        # Reference line at 1.0 (no fouling)
                        rule = alt.Chart(pd.DataFrame({'y': [1.0]})).mark_rule(strokeDash=[5,5], color='green').encode(y='y:Q')
                        
                        trend_chart = trend_line + trend_points + rule
                        st.altair_chart(trend_chart, use_container_width=True)
                        st.caption("🟢 Green dashed line = No fouling (Index = 1.0). Values below indicate performance loss.")

                        # Add to Report button for trend chart
                        add_to_report_button(
                            content=trend_chart,
                            title="Fouling Index Trend Over Time",
                            item_type='chart',
                            description="Rolling average trend of fouling index with daily scatter points",
                            source_page="Fouling Analysis",
                            width=10.0,
                            height=5.0,
                            button_key=f"add_fouling_trend_{f_plant_alias.replace(' ', '_')}"
                        )
                    
                    with tab_scatter:
                        st.subheader("PR vs Irradiance")
                        df_scatter = df_res.copy()
                        # Sample if too large for Altair
                        if len(df_scatter) > 5000:
                            df_scatter = df_scatter.sample(5000)
                        scatter = alt.Chart(df_scatter).mark_circle(size=60).encode(
                            x=alt.X('poaIrradiance:Q', title='POA Irradiance (W/m²)'),
                            y=alt.Y('pr:Q', title='Performance Ratio'),
                            color=alt.Color('fouling_index:Q', scale=alt.Scale(scheme='redyellowgreen'), title='Fouling Index')
                        ).properties(title="PR vs Irradiance")
                        st.altair_chart(scatter, use_container_width=True)

                        # Add to Report button for scatter plot
                        add_to_report_button(
                            content=scatter,
                            title="PR vs Irradiance Correlation",
                            item_type='chart',
                            description="Scatter plot showing relationship between POA irradiance and performance ratio with fouling index coloring",
                            source_page="Fouling Analysis",
                            width=10.0,
                            height=5.0,
                            button_key=f"add_fouling_scatter_{f_plant_alias.replace(' ', '_')}"
                        )
                    
                    with tab_daily:
                        st.subheader("Daily Fouling Summary")
                        # Aggregate by date
                        df_daily = df_res.copy()
                        df_daily['date'] = pd.to_datetime(df_daily['ts']).dt.date
                        daily_summary = df_daily.groupby('date').agg({
                            'fouling_index': ['mean', 'min', 'max', 'count'],
                            'pr': 'mean',
                            'poaIrradiance': 'mean'
                        }).reset_index()
                        daily_summary.columns = ['date', 'fouling_mean', 'fouling_min', 'fouling_max', 'data_points', 'pr_mean', 'irradiance_mean']
                        
                        # Bar chart of daily fouling
                        daily_chart = alt.Chart(daily_summary).mark_bar().encode(
                            x=alt.X('date:T', title='Date'),
                            y=alt.Y('fouling_mean:Q', title='Daily Avg Fouling Index', scale=alt.Scale(domain=[0, 1.2])),
                            color=alt.Color('fouling_mean:Q', scale=alt.Scale(scheme='redyellowgreen'), title='Fouling')
                        )
                        
                        rule = alt.Chart(pd.DataFrame({'y': [1.0]})).mark_rule(strokeDash=[5,5], color='green').encode(y='y:Q')

                        daily_combined = daily_chart + rule
                        st.altair_chart(daily_combined, use_container_width=True)

                        # Add to Report button for daily chart
                        add_to_report_button(
                            content=daily_combined,
                            title="Daily Average Fouling Index",
                            item_type='chart',
                            description="Bar chart of daily average fouling index with reference line at no fouling",
                            source_page="Fouling Analysis",
                            width=10.0,
                            height=5.0,
                            button_key=f"add_fouling_daily_chart_{f_plant_alias.replace(' ', '_')}"
                        )

                        # Show summary table
                        st.dataframe(
                            daily_summary.style.format({
                                'fouling_mean': '{:.3f}',
                                'fouling_min': '{:.3f}',
                                'fouling_max': '{:.3f}',
                                'pr_mean': '{:.3f}',
                                'irradiance_mean': '{:.1f}'
                            }),
                            use_container_width=True
                        )

                        # Add to Report button for daily summary table
                        add_to_report_button(
                            content=daily_summary,
                            title="Daily Fouling Summary Statistics",
                            item_type='table',
                            description="Daily fouling index statistics including mean, min, max, PR and irradiance averages",
                            source_page="Fouling Analysis",
                            button_key=f"add_fouling_daily_table_{f_plant_alias.replace(' ', '_')}"
                        )
            except Exception as e:
                st.error(f"Error during fouling analysis: {e}")
                import traceback
                st.code(traceback.format_exc())

# --- PAGE 4: Shading Analysis ---
