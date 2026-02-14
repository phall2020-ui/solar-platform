"""Monthly Reporting page (High-Fidelity Legacy Wrapper)."""
import datetime
import logging
import sys

import pandas as pd
import streamlit as st

from components.report_button import add_to_report_button
from unified_config import config

logger = logging.getLogger(__name__)

# --- Legacy Import Setup ---
# Ensure Monthly Reporting directory is in path to allow importing legacy modules
LEGACY_AVAILABLE = False
legacy_app = None
ui_tabs = None
data_access = None

if config.MONTHLY_REPORTING_PATH.exists():
    if str(config.MONTHLY_REPORTING_PATH) not in sys.path:
        sys.path.insert(0, str(config.MONTHLY_REPORTING_PATH))
    
    try:
        # Import legacy modules - avoid importing 'app' to prevent circular import
        import data_access as _data_access
        import ui_tabs as _ui_tabs
        ui_tabs = _ui_tabs
        data_access = _data_access
        
        # Try to import app module carefully (not the Unified app!)
        try:
            import importlib.util
            app_path = config.MONTHLY_REPORTING_PATH / "app.py"
            if app_path.exists():
                spec = importlib.util.spec_from_file_location("legacy_app", app_path)
                legacy_app = importlib.util.module_from_spec(spec)
                # Don't execute the module to avoid Streamlit duplicate key issues
                # spec.loader.exec_module(legacy_app)
        except Exception:
            pass
        
        LEGACY_AVAILABLE = True
    except ImportError as e:
        # Legacy modules not available - this is fine, just means Monthly Reporting project is not set up
        logger.warning("Legacy reporting modules not importable: %s", e)
        pass

import plotly.express as px

from services import toolkit
from services.reporting_bridge import reporting

# Column Mapping for Bridge
COLMAP = {
    'Site': 'Site',
    'Date': 'Date',
    'PR': 'Actual PR (%)',
    'Availability': 'Availability (%)',
    'Gen_Budget_kWh': 'Forecast Gen (kWh)',
    'Gen_Actual_kWh': 'Actual Gen (kWh)',
    'Irr_Global_Horizontal_kWh_m2': 'Actual Irr (kWh/m2)',  # Best guess for Irr
}


from modules import chart_utils
from modules.report_generator import PDFReportGenerator


def render_monthly_report_tab(tab_container, extractor):
    """Render the new Monthly Report tab."""
    with tab_container:
        logger.info("Rendering Monthly Report tab")
        st.header("📊 Monthly Executive Report")
        
        # --- State for PDF Data Collection ---
        if 'pdf_report' not in st.session_state:
            st.session_state.pdf_report = {}
        
        pdf_data = {
            "top_5": None,
            "bottom_5": None,
            "heatmap": None,
            "shading_summary": None,
            "soiling_summary": None,
            "figures": []
        }
        
        # --- UI State Initialization ---
        sh_site = None
        soiling_site = None
        base = None
        comp = None
        plant_uid = None
        soil_start = None
        soil_end = None
        
        # --- Configuration ---
        with st.expander("📝 Report Configuration", expanded=True):
            c1, c2, c3 = st.columns(3)
            
            # 1. Date Selection
            with c1:
                try:
                    df = reporting.get_table_data("solar_data")
                    dates = []
                    if df is not None and not df.empty and 'Date' in df.columns:
                        # robust sort without lambda pd issue
                        unique_dates = df['Date'].unique()
                        date_objs = []
                        for d in unique_dates:
                            try:
                                dt = datetime.datetime.strptime(str(d), '%b-%y')
                            except (ValueError, TypeError):
                                dt = datetime.datetime.min
                            date_objs.append((d, dt))
                        
                        # Sort by dt desc
                        date_objs.sort(key=lambda x: x[1], reverse=True)
                        dates = [x[0] for x in date_objs]
                except Exception as e:
                    logger.error("Data fetch error in monthly report config: %s", e)
                    st.error(f"Data Fetch Error: {e}")
                    dates = []

                selected_month = st.selectbox("Select Reporting Month", dates if dates else ["No Data"])
            
            # 2. Section Selection
            with c2:
                available_sections = [
                    "Performance Ranking (Top/Bottom 5)",
                    "Technical Loss Heatmap (Last 12 Months)",
                    "Shading Analysis",
                    "Soiling Analysis"
                ]
                selected_sections = st.multiselect("Include Sections", available_sections, default=available_sections[:2])
            
            # 3. Site Filter (Global)
            with c3:
                sites = sorted(df['Site'].unique()) if (df is not None and not df.empty) else []
                selected_sites = st.multiselect("Filter Sites (Optional)", sites, default=None) # Empty means all
                
                # Context info
                st.caption(f"Generating report for: {selected_month}")

        if not selected_month or selected_month == "No Data":
            st.warning("No data available.")
            return

        # Prepare filtered DF for the specific month
        month_df = df[df['Date'] == selected_month].copy()
        if selected_sites:
            month_df = month_df[month_df['Site'].isin(selected_sites)]
        
        st.divider()

        # --- Calculate Technical Loss (if missing) ---
        # User indicates this is a Key KPI. If not in DB, we must calculate it.
        # Logic: Technical Loss = Weather Adjusted Expectation - Actual Comparison
        # Preferred: 'Calculated Exp (kWh)' - 'Actual Gen (kWh)'
        # Fallback: 'Forecast Gen (kWh)' - 'Actual Gen (kWh)'
        
        target_loss_col = 'Loss_Total_Tech_kWh'
        if target_loss_col not in month_df.columns:
            # Helper to calculate loss safely - Vectorized approach to avoid scope issues
            if 'Calculated Exp (kWh)' in month_df.columns and 'Actual Gen (kWh)' in month_df.columns:
                 # Logic: If Exp is 0 or NaN -> 0, else Exp - Act
                 exp = month_df['Calculated Exp (kWh)'].fillna(0)
                 act = month_df['Actual Gen (kWh)'].fillna(0)
                 # Use vectorized logic: where exp == 0, result is 0, else exp - act
                 # We can use pd.Series.where or list comprehension if simple
                 # But standard pandas subtract is easiest, then overwrite 0s
                 loss = exp - act
                 loss[exp == 0] = 0.0
                 month_df[target_loss_col] = loss
            elif 'Forecast Gen (kWh)' in month_df.columns and 'Actual Gen (kWh)' in month_df.columns:
                 exp = month_df['Forecast Gen (kWh)'].fillna(0)
                 act = month_df['Actual Gen (kWh)'].fillna(0)
                 loss = exp - act
                 loss[exp == 0] = 0.0
                 month_df[target_loss_col] = loss
            else:
                 month_df[target_loss_col] = 0.0

        # --- 1. Top & Bottom 5 Sites ---
        if "Performance Ranking (Top/Bottom 5)" in selected_sections:
            st.subheader(f"🏆 Performance Ranking ({selected_month})")
            
            m_col, _ = st.columns([1, 3])
            with m_col:
                metric = st.selectbox("Rank By", ["PR", "Availability", "Technical Loss"], index=0)
            
            # Handle mapping
            if metric == "Technical Loss":
                # Need to find the loss column. 
                # Assuming 'Loss_Total_Tech_kWh' exists or we need to calculate it.
                # 'get_waterfall_components' returns a dict.
                # If column doesn't exist in month_df, we try to map it.
                # Existing COLMAP doesn't have it.
                target_col = 'Loss_Total_Tech_kWh'
                if target_col not in month_df.columns:
                     # 1. Try case-insensitive search
                     candidates = [c for c in month_df.columns if 'loss' in c.lower() and 'tech' in c.lower()]
                     if candidates:
                         target_col = candidates[0]
                     else:
                         # 2. Try calculate or fallback
                         # For now, let's use 'Gen_Budget_kWh' - 'Gen_Actual_kWh' (rough proxy if tech loss missing)
                         if 'Gen_Budget_kWh' in month_df.columns and 'Gen_Actual_kWh' in month_df.columns:
                             month_df['Total Loss'] = month_df['Gen_Budget_kWh'] - month_df['Gen_Actual_kWh']
                             target_col = 'Total Loss'
            else:
                target_col = COLMAP.get(metric, metric)

            if target_col in month_df.columns:
                 # Sort locally
                 sorted_df = month_df.sort_values(by=target_col, ascending=(metric != "Technical Loss")) # Low loss is good? High loss is usually "Bottom"? 
                 # Usually Top Performers = High PR, High Avail.
                 # Top Performers = LOW Loss? 
                 # Let's stick to High Value = Top for consistency, but for Loss, High = Bad.
                 # Bridge 'get_top_bottom_sites' does descending sort.
                 
                 _ascending = False
                 if metric == "Technical Loss":
                     _ascending = False # High loss = Top of the list (Worst performers?)
                     # Typically "Top 5" means Best. Best sites have LOW loss.
                     # Let's label explicitly.
                     pass
                 
                 sorted_df = sorted_df.sort_values(by=target_col, ascending=False)
                 
                 top_n = sorted_df.head(5)[['Site', target_col]]
                 bot_n = sorted_df.tail(5)[['Site', target_col]]
                 
                 # Store for PDF
                 pdf_data["top_5"] = top_n
                 pdf_data["bottom_5"] = bot_n
                 
                 c1, c2 = st.columns(2)
                 with c1:
                     st.markdown("**Top 5 (Highest Values)**")
                     st.dataframe(top_n.style.format({target_col: "{:.2f}"}), use_container_width=True)
                     add_to_report_button(
                         content=top_n,
                         title=f"Top 5 Sites - {metric} ({selected_month})",
                         item_type='table',
                         description=f"Top 5 performing sites for {metric}",
                         source_page="Monthly Performance",
                         button_key=f"add_top5_{metric}_{selected_month}"
                     )
                 with c2:
                    st.markdown("**Bottom 5 (Lowest Values)**")
                    st.dataframe(bot_n.style.format({target_col: "{:.2f}"}), use_container_width=True)
                    add_to_report_button(
                        content=bot_n,
                        title=f"Bottom 5 Sites - {metric} ({selected_month})",
                        item_type='table',
                        description=f"Bottom 5 performing sites for {metric}",
                        source_page="Monthly Performance",
                        button_key=f"add_bottom5_{metric}_{selected_month}"
                    )
            else:
                st.warning(f"Metric '{metric}' data not found in database.")
                with st.expander("Debug Info - Available Columns"):
                     st.write(month_df.columns.tolist())

            st.divider()

        # --- 2. Technical Loss Heatmap ---
        if "Technical Loss Heatmap (Last 12 Months)" in selected_sections:
            st.subheader("🔥 Technical Loss Heatmap (Last 12 Months)")
            
            # Logic: Filter df for last 12 months based on selected_month
             # Convert selected_month ('Jan-24') to date
            try:
                curr_date = datetime.datetime.strptime(selected_month, '%b-%y')
            except (ValueError, TypeError):
                curr_date = datetime.datetime.now()

            start_date = curr_date - datetime.timedelta(days=365)
            
            # Filter main df
            # Need to parse 'Date' col
            # Assuming 'Date' is 'Mb-YY' string
            def parse_date(x):
                try:
                    return datetime.datetime.strptime(x, '%b-%y')
                except (ValueError, TypeError):
                    return None
            
            mask = df['Date'].apply(parse_date).between(start_date, curr_date)
            hist_df = df[mask].copy()
            
            if selected_sites:
                hist_df = hist_df[hist_df['Site'].isin(selected_sites)]
            
            # Check for loss column and calculate if missing
            loss_col = 'Loss_Total_Tech_kWh'
            if loss_col not in hist_df.columns:
                 # Helper - Vectorized
                 if 'Calculated Exp (kWh)' in hist_df.columns and 'Actual Gen (kWh)' in hist_df.columns:
                     exp = hist_df['Calculated Exp (kWh)'].fillna(0)
                     act = hist_df['Actual Gen (kWh)'].fillna(0)
                     loss = exp - act
                     loss[exp == 0] = 0.0
                     hist_df[loss_col] = loss
                 elif 'Forecast Gen (kWh)' in hist_df.columns and 'Actual Gen (kWh)' in hist_df.columns:
                     exp = hist_df['Forecast Gen (kWh)'].fillna(0)
                     act = hist_df['Actual Gen (kWh)'].fillna(0)
                     loss = exp - act
                     loss[exp == 0] = 0.0
                     hist_df[loss_col] = loss
                 else:
                     hist_df[loss_col] = 0.0
            
            if loss_col in hist_df.columns:
                # Pivot
                heatmap_data = hist_df.pivot_table(index='Site', columns='Date', values=loss_col)
                
                # Sort columns by date
                cols = sorted(heatmap_data.columns, key=lambda x: parse_date(x) or datetime.datetime.min)
                heatmap_data = heatmap_data[cols]
                
                heatmap_data = heatmap_data.fillna(0) # Fill NaNs
                
                # Store for PDF (as figure)
                fig_heat = chart_utils.create_heatmap_chart(heatmap_data, "Technical Losses")
                st.plotly_chart(fig_heat, use_container_width=True)
                add_to_report_button(
                    content=fig_heat,
                    title="Technical Loss Heatmap (Last 12 Months)",
                    item_type='chart',
                    description=f"12-month technical loss trends ending {selected_month}",
                    source_page="Monthly Performance",
                    button_key=f"add_heatmap_{selected_month}"
                )
                pdf_data["figures"].append(fig_heat) 
            else:
                st.warning("Technical Loss data not available for heatmap.")
            
            st.divider()

        # --- 3. Shading Analysis ---
        if "Shading Analysis" in selected_sections:
            st.subheader("🌓 Shading Analysis")
            
            c_s1, c_s2 = st.columns([1, 1])
            with c_s1:
                # Helper to determine valid shading sites
                valid_shading_sites = []
                all_candidates = selected_sites if selected_sites else sites
                
                # Check which candidates have a resolvable UID
                for s in all_candidates:
                    if toolkit.resolve_plant_uid(s):
                        valid_shading_sites.append(s)
                
                # Fallback to all if matching fails completely (or just show empty with warning)
                sh_options = valid_shading_sites if valid_shading_sites else all_candidates
                
                # Site selector (single)
                sh_site = st.selectbox("Site for Shading", sh_options, key="sh_site")
            
            # Resolve plant UID using valid method via bridge
            plant_uid = toolkit.resolve_plant_uid(sh_site)

            if not plant_uid:
                st.warning(f"Could not resolve UID for site '{sh_site}'. Shading analysis may fail.")

            # Dynamic Dates based on toolkit data availability
            start_dt_str, end_dt_str = toolkit.get_date_range(plant_uid) if plant_uid else (None, None)
            
            if start_dt_str and end_dt_str:
                try:
                    min_date = datetime.datetime.fromisoformat(start_dt_str[:10])
                    max_date = datetime.datetime.fromisoformat(end_dt_str[:10])
                except (ValueError, TypeError):
                    # Fallback
                    now = datetime.datetime.now()
                    min_date = now - datetime.timedelta(days=365*2)
                    max_date = now
            else:
                # Fallback
                now = datetime.datetime.now()
                min_date = now - datetime.timedelta(days=365*2)
                max_date = now

            # Generate month options from min_date to max_date
            month_options = []
            curr = min_date.replace(day=1)
            while curr <= max_date:
                month_options.append(curr.strftime("%Y-%m"))
                # Next month
                if curr.month == 12:
                    curr = curr.replace(year=curr.year+1, month=1)
                else:
                    curr = curr.replace(month=curr.month+1)
            
            # Reverse sort for better UX? No, chronological is better for range picking.
            # But usually we want recent.
            month_options = sorted(month_options, reverse=True)

            # Defaults: Last summer available, Last winter available
            _current_year = max_date.year
            
            default_base = [m for m in month_options if m.endswith("-06") or m.endswith("-07") or m.endswith("-08")]
            if len(default_base) > 3: default_base = default_base[:3] # Take most recent 3
            
            default_comp = [m for m in month_options if m.endswith("-11") or m.endswith("-12") or m.endswith("-01")]
            if len(default_comp) > 3: default_comp = default_comp[:3]
            
            with st.expander("Shading Period Settings", expanded=True):
                base = st.multiselect("Baseline (Summer)", month_options, default=default_base)
                comp = st.multiselect("Comparison (Winter)", month_options, default=default_comp)

            if st.button("Run Shading Analysis"):
                 if sh_site and base and comp:
                    with st.spinner("Analyzing Shading..."):
                        # plant_uid already resolved above
                        pass
                        
                        merged, sum_df = toolkit.run_shading_analysis(plant_uid, base, comp)
                        
                        if not sum_df.empty:
                            st.subheader(f"Shading Results: {sh_site}")
                            st.dataframe(sum_df)
                            pdf_data["shading_summary"] = sum_df
                            
                            if not merged.empty and 'shading_ratio' in merged.columns and 'power_ac_baseline' in merged.columns:
                                fig_sh = px.scatter(merged, x='power_ac_baseline', y='power_ac_compare', color='shading_ratio', title=f"Shading Analysis ({sh_site})")
                                st.plotly_chart(fig_sh)
                                add_to_report_button(
                                    content=fig_sh,
                                    title=f"Shading Analysis - {sh_site}",
                                    item_type='chart',
                                    description="Baseline vs Comparison period power analysis",
                                    source_page="Monthly Performance",
                                    button_key=f"add_shading_{sh_site}_{selected_month}".replace(' ', '_')
                                )
                                pdf_data["figures"].append(fig_sh)
                        else:
                            st.error("No data returned for shading analysis.")

            st.divider()

        # --- 4. Soiling Analysis ---
        if "Soiling Analysis" in selected_sections:
            st.subheader("🍂 Soiling (Fouling) Analysis")
            
            c_f1, _ = st.columns([1, 1])
            with c_f1:
                soiling_site = st.selectbox("Site for Soiling", selected_sites if selected_sites else sites, key="soil_site")
            
            # Date Range for Soiling
            d_col1, d_col2 = st.columns(2)
            with d_col1:
                soil_start = st.date_input("Start Date", value=now - datetime.timedelta(days=90))
            with d_col2:
                soil_end = st.date_input("End Date", value=now)
            
            if st.button("Run Soiling Analysis"):
                if soiling_site:
                     with st.spinner("Analyzing Soiling..."):
                        # Resolve UID
                        p_uid = toolkit.resolve_plant_uid(soiling_site) or soiling_site
                        # Need DC size for analysis? Wrapper usually handles it if omitted but bridge needs logic
                        # Bridge run_fouling_analysis signature: (plant_uid, start_date, end_date, dc_size_kw, ...)
                        # We need DC size from plant registry
                        dc_size = 1000.0 # Default
                        
                        try:
                            # Try to get DC size implies finding the plant object
                            # If direct lookup fails, we might miss DC size, but we have UID now
                            plant_data = toolkit.get_plant(soiling_site) 
                            if plant_data:
                                dc_size = plant_data.get('dc_capacity', 1000.0)
                        except Exception:
                            pass
                        
                        try:
                            res = toolkit.run_fouling_analysis(
                                plant_uid=p_uid,
                                start_date=str(soil_start),
                                end_date=str(soil_end),
                                dc_size_kw=dc_size
                            )
                            # res is dict with 'timeseries', 'daily', 'metrics' usually
                            if res and 'daily' in res and not res['daily'].empty:
                                st.subheader(f"Soiling Results: {soiling_site}")
                                
                                # Metrics
                                if 'metrics' in res:
                                    m = res['metrics']
                                    c1, c2 = st.columns(2)
                                    c1.metric("Soiling Loss", f"{m.get('total_soiling_loss_kwh', 0):.1f} kWh")
                                    c2.metric("Avg Soiling Ratio", f"{m.get('avg_soiling_ratio', 1.0):.1%}")
                                
                                # Plot
                                daily_df = res['daily']
                                # Usually has 'soiling_loss' or 'daily_loss'
                                cols_to_plot = [c for c in daily_df.columns if 'loss' in c.lower()]
                                if cols_to_plot:
                                    fig_soil = px.line(daily_df, y=cols_to_plot, title=f"Soiling Loss: {soiling_site}")
                                    st.plotly_chart(fig_soil)
                                    add_to_report_button(
                                        content=fig_soil,
                                        title=f"Soiling Loss - {soiling_site}",
                                        item_type='chart',
                                        description=f"Daily soiling loss trends from {soil_start} to {soil_end}",
                                        source_page="Monthly Performance",
                                        button_key=f"add_soiling_chart_{soiling_site}".replace(' ', '_')
                                    )
                                    pdf_data["figures"].append(fig_soil)
                                    pdf_data["soiling_summary"] = daily_df.describe() # Summary stats for PDF table
                                else:
                                    st.dataframe(daily_df)
                                    add_to_report_button(
                                        content=daily_df,
                                        title=f"Soiling Data - {soiling_site}",
                                        item_type='table',
                                        description=f"Soiling analysis data from {soil_start} to {soil_end}",
                                        source_page="Monthly Performance",
                                        button_key=f"add_soiling_table_{soiling_site}".replace(' ', '_')
                                    )

                            else:
                                st.warning("No results found for soiling analysis.")

                        except Exception as e:
                            st.error(f"Soiling Error: {e}")

        st.divider()
        
        st.divider()
        
        # --- 5. Report Composer (Flexible Generator) ---
        st.subheader("📄 Report Composer")
        
        with st.expander("Configure Report Content", expanded=True):
            st.write("Select additional charts to include in the PDF report:")
            
            c_rep1, c_rep2 = st.columns(2)
            with c_rep1:
                include_perf_table = st.checkbox("Top/Bottom 5 Sites", value=True)
                include_heatmap = st.checkbox("Technical Loss Heatmap", value=True)
            
            with c_rep2:
                # Shading selection
                include_shading = st.checkbox(f"Include Shading Charts ({len([s for s in selected_sites if s])} selected)", value=False)
                # Soiling selection
                include_soiling = st.checkbox("Include Soiling Analysis (for selected site)", value=False)

        if st.button("Generate Custom Report", type="primary"):
            with st.spinner("Compiling Report..."):
                try:
                    pdf_gen = PDFReportGenerator(
                        title=f"Monthly Executive Report - {selected_month}",
                        subtitle="Detailed Performance & Technical Analysis"
                    )
                    
                    # 1. Ranking Table
                    if include_perf_table and pdf_data["top_5"] is not None:
                        pdf_gen.add_section_header("Performance Ranking")
                        pdf_gen.add_table(pdf_data["top_5"], "Top 5 Sites")
                        pdf_gen.add_table(pdf_data["bottom_5"], "Bottom 5 Sites")
                    
                    # 2. Heatmap
                    if include_heatmap:
                        # Regenerate heatmap headlessly
                        hm_df = month_df.copy()
                        loss_col = 'Loss_Total_Tech_kWh' # Ensure this matches logic above
                        if loss_col not in hm_df.columns:
                             # Try to find it again or recalculate if needed (assuming logic above ran)
                             pass
                        
                        if loss_col in hm_df.columns:
                             hm_pivot = hm_df.pivot_table(index="Site", columns="Date", values=loss_col)
                             fig_hm = chart_utils.create_heatmap_chart(hm_pivot, "Technical Loss")
                             if fig_hm:
                                 pdf_gen.add_section_header("Technical Loss Heatmap")
                                 pdf_gen.add_plot(fig_hm)
                    
                    # 3. Shading Charts (Loop through sites or use current UI selection?)
                    # For "Staged" approach, we should ideally loop through selected sites.
                    # But for now, let's use the explicit Shading UI selection if active, or just the current site
                    if include_shading:
                        # Logic: If user selected multiple sites in global filter, run for all?
                        # Or just the one in the Shading tab? 
                        # User wants flexibility. Let's run for the site selected in Shading Tab for now.
                        target_site = sh_site
                        if target_site:
                            # We need to re-run or fetch from state? Re-running ensures freshness
                            uid = plant_uid # Context from shading section
                            if uid and base and comp:
                                m, s = toolkit.run_shading_analysis(uid, base, comp)
                                fig_s = chart_utils.create_shading_chart(m, target_site)
                                if fig_s:
                                    pdf_gen.add_section_header(f"Shading Analysis: {target_site}")
                                    pdf_gen.add_plot(fig_s)
                                    if not s.empty:
                                        pdf_gen.add_table(s.reset_index(), "Shading Metrics")

                    # 4. Soiling Charts
                    if include_soiling and soiling_site:
                        # Re-run soiling
                        p_uid_soil = toolkit.resolve_plant_uid(soiling_site) or soiling_site
                        # Need DC size... reusing logic or assuming default
                        try: 
                            dc = 1000.0
                            pd = toolkit.get_plant(soiling_site)
                            if pd: dc = pd.get('dc_capacity', 1000.0)
                            
                            res_s = toolkit.run_fouling_analysis(p_uid_soil, str(soil_start), str(soil_end), dc)
                            if res_s and 'daily' in res_s:
                                fig_soil = chart_utils.create_soiling_chart(res_s['daily'], soiling_site)
                                if fig_soil:
                                    pdf_gen.add_section_header(f"Soiling Analysis: {soiling_site}")
                                    pdf_gen.add_plot(fig_soil)
                        except Exception as e:
                             st.warning(f"Skipping soiling for PDF: {e}")

                    # 5. Existing Figures (if any manually added)
                    # pdf_data["figures"] stores interactively generated ones. Keep?
                    # Maybe clear them to avoid dupes, or append? 
                    # Let's trust the "Composer" logic above primarily.
                    
                    pdf_bytes = pdf_gen.generate()
                    
                    st.success("Report Compiled!")
                    st.download_button(
                        label="📥 Download Custom PDF",
                        data=pdf_bytes,
                        file_name=f"Executive_Report_{selected_month}_Custom.pdf",
                        mime="application/pdf"
                    )
                    
                except Exception as e:
                    logger.error("PDF generation failed: %s", e, exc_info=True)
                    st.error(f"PDF Generation Failed: {e}")
                    import traceback
                    st.code(traceback.format_exc())





def render():
    """Render the monthly reporting page using legacy components."""
    logger.info("Rendering monthly reporting page")
    st.title("📊 Monthly Performance")
    
    if not LEGACY_AVAILABLE:
        st.warning("Legacy reporting modules not found.")
        return

    # (Legacy session state handled in sidebar to ensure int type)

    # Initialize Legacy Session State
    if hasattr(legacy_app, 'init_session_state'):
        legacy_app.init_session_state()

    # Initialize session state for legacy modules
    # Legacy modules use SQLite, not DuckDB - use the legacy database path
    legacy_db_path = str(config.MONTHLY_REPORTING_PATH / "solar_assets.db")
    if 'db_name' not in st.session_state:
        st.session_state.db_name = legacy_db_path
    
    # Initialize Extractor (Database Connection)
    try:
        # Use the legacy SQLite database path
        extractor = data_access.SolarDataExtractor(legacy_db_path)
    except Exception as e:
        logger.error("Monthly reporting database connection failed: %s", e)
        st.error(f"Database Error: {e}")
        return

    # Create Tabs matching the Original App
    # "Upload Data", "Tables", "Calculations", "Waterfall Analysis", "ExCom Report"
    _tab_names = [
        "📊 Monthly Report",
        "📤 Upload Data", 
        "📋 Tables", 
        "🧮 Calculations", 
        "📉 Waterfall Analysis", 
        "📑 ExCom Report"
    ]
    
    tabs = st.tabs([
        "📤 Upload Data", 
        "📋 Tables", 
        "🧮 Calculations", 
        "📉 Waterfall Analysis", 
        "📑 ExCom Report"
    ])
    
    (tab_upload, tab_tables, tab_calc, tab_waterfall, tab_excom) = tabs

    
    
    # Render Legacy Components into Tabs
    
    # 0. Monthly Report (New) - REMOVED
    # render_monthly_report_tab(tab_report, extractor)
    
    # 1. Upload Tab
    with tab_upload:
        if hasattr(ui_tabs, 'render_upload_tab'):
            ui_tabs.render_upload_tab(tab_upload, extractor)
        else:
            st.error("Legacy 'render_upload_tab' not found.")

    # 2. Tables Tab
    with tab_tables:
        # Add Override Control for Data Cleaning
        with st.expander("🗑️ Database Management (Unified App Override)", expanded=False):
            st.warning("This action will delete ALL data from the Monthly Reporting database.")
            if st.button("Delete All Data", type="primary"):
                try:
                    import sqlite3
                    legacy_db = str(config.MONTHLY_REPORTING_PATH / "solar_assets.db")
                    with sqlite3.connect(legacy_db) as conn:
                        cursor = conn.cursor()
                        for t in ["solar_data"]:
                            cursor.execute(f"DELETE FROM '{t}'")
                        conn.commit()
                    st.success("✅ Database cleared successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to clear database: {e}")

        if hasattr(ui_tabs, 'render_tables_tab'):
            ui_tabs.render_tables_tab(tab_tables, extractor)
        else:
            st.error("Legacy 'render_tables_tab' not found.")

    # 3. Calculations Tab
    with tab_calc:
        # Temporary patch so any heatmaps created inside the legacy calculations tab
        # use a symmetric, 0-centered scale with a light-green tint at zero.
        original_px_imshow = px.imshow

        def _imshow_zero_green(*args, **kwargs):
            fig = original_px_imshow(*args, **kwargs)
            try:
                # Extract numeric matrix from the first positional arg if possible
                if args:
                    data = args[0]
                else:
                    data = kwargs.get("img", None)

                df = pd.DataFrame(data) if data is not None else None
                min_val = df.min().min() if df is not None and not df.empty else 0
                max_val = df.max().max() if df is not None and not df.empty else 0
                abs_max = max(abs(min_val), abs(max_val))
                if pd.isna(abs_max) or abs_max == 0:
                    abs_max = 1

                zero_tint = "#e3f5eb"

                # Respect caller-provided scale direction; only inject the zero tint and symmetric range
                provided_scale = kwargs.get("color_continuous_scale")
                start_color = config.BRAND_COLORS["positive"]
                end_color = config.BRAND_COLORS["negative"]

                if provided_scale:
                    # Handle both ["red", "white", "green"] and [[0,"red"], [0.5,"white"], [1,"green"]] forms
                    if isinstance(provided_scale, list) and len(provided_scale) > 0:
                        first = provided_scale[0]
                        last = provided_scale[-1]
                        if isinstance(first, (list, tuple)) and len(first) >= 2:
                            start_color = first[1]
                            end_color = last[1] if isinstance(last, (list, tuple)) and len(last) >= 2 else end_color
                        else:
                            start_color = first
                            end_color = last

                diverging_scale = [
                    (0.0, start_color),
                    (0.45, zero_tint),
                    (0.55, zero_tint),
                    (1.0, end_color),
                ]

                coloraxis = fig.layout.coloraxis
                cmin_set = coloraxis.cmin is not None
                cmax_set = coloraxis.cmax is not None
                cmid_set = coloraxis.cmid is not None

                fig.update_coloraxes(
                    cmin=coloraxis.cmin if cmin_set else -abs_max,
                    cmax=coloraxis.cmax if cmax_set else abs_max,
                    cmid=coloraxis.cmid if cmid_set else 0,
                    colorscale=diverging_scale,
                )
            except Exception:
                # If anything goes wrong, fall back to the original figure unmodified
                return fig

            return fig

        px.imshow = _imshow_zero_green

        try:
            # Check if legacy_app has the v2 function, otherwise fall back
            if hasattr(legacy_app, 'render_calculations_v2_tab'):
                # Inject report button into legacy module if available
                try:
                    import ui_calculations_v2
                    ui_calculations_v2.REPORT_BUTTON_AVAILABLE = True
                    ui_calculations_v2.add_to_report_button = add_to_report_button
                except (ImportError, AttributeError):
                    pass
                legacy_app.render_calculations_v2_tab(tab_calc, extractor)
            elif hasattr(ui_tabs, 'render_calculations_tab'):
                ui_tabs.render_calculations_tab(tab_calc, extractor)
            else:
                st.error("Legacy calculations tab not found.")
        finally:
            px.imshow = original_px_imshow

    # 4. Waterfall Analysis
    with tab_waterfall:
        if hasattr(legacy_app, 'render_waterfall_tab_v2'):
            legacy_app.render_waterfall_tab_v2(tab_waterfall, extractor)
        elif hasattr(ui_tabs, 'render_waterfall_tab'):
            ui_tabs.render_waterfall_tab(tab_waterfall, extractor)
        else:
            st.error("Legacy waterfall tab not found.")

    # 5. ExCom Report
    with tab_excom:
        # Inject report button into legacy module
        try:
            import ui_excom_report
            ui_excom_report.add_to_report_button = add_to_report_button
        except (ImportError, AttributeError):
            pass

        if hasattr(legacy_app, 'render_excom_report_tab'):
            legacy_app.render_excom_report_tab(tab_excom, extractor)
        elif hasattr(ui_tabs, 'render_excom_report_tab'):
            # Only if ui_tabs has it (inspect said ui_excom_report has it primarily)
            ui_tabs.render_excom_report_tab(tab_excom, extractor)
        else:
            # Fallback to direct import if app doesn't expose it
            try:
                import ui_excom_report
                ui_excom_report.render_excom_report_tab(tab_excom, extractor)
            except ImportError:
                st.error("Legacy ExCom report tab not found.")
