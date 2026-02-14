"""Clipping Analysis (Legacy Wrapper)."""

import streamlit as st

from components.report_button import add_to_report_button
from services import legacy_toolkit


def render():
    """Render the legacy Clipping Analysis page."""
    orch = legacy_toolkit.get_orchestrator()
    if not orch:
        st.error("Orchestrator not available.")
        return

    # Context
    plant_list = orch.get_plants()
    plant_aliases = [p['alias'] for p in plant_list]

    st.header("Inverter Clipping Loss Analysis")
    st.markdown("Estimate clipping losses using **Twin Simulations** (Constrained vs Unconstrained) via NREL PSM3 weather data.")

    # 1. Plant Selection
    selected_alias = st.selectbox("Select Plant", options=plant_aliases, index=0 if plant_aliases else None)
    
    if selected_alias:
        # Load plant data from store (legacy method)
        plant_data = orch.store.load(selected_alias) if hasattr(orch, 'store') else next((p for p in plant_list if p['alias'] == selected_alias), {})
        
        # 2. Configuration Check (Location)
        with st.expander("📍 Location & Orientation Settings", expanded=True):
            c1, c2, c3, c4 = st.columns(4)
            lat = c1.number_input("Latitude", value=float(plant_data.get('latitude') or 51.5), format="%.4f")
            lon = c2.number_input("Longitude", value=float(plant_data.get('longitude') or -0.1), format="%.4f")
            tilt = c3.number_input("Tilt (°)", value=float(plant_data.get('tilt') or 30.0), format="%.1f")
            azimuth = c4.number_input("Azimuth (°)", value=float(plant_data.get('azimuth') or 180.0), help="180=South, 90=East", format="%.1f")
            
            if st.button("💾 Save Location Settings"):
                try:
                    orch.save_plant(
                        alias=selected_alias,
                        uid=plant_data['plant_uid'],
                        inv_ids=plant_data.get('inverter_ids', []),
                        weth_id=plant_data.get('weather_id'),
                        dc_size=plant_data.get('dc_size_kw'),
                        latitude=lat, longitude=lon, tilt=tilt, azimuth=azimuth
                    )
                    st.success("Settings saved!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error saving: {e}")

        # 3. System Parameters
        with st.expander("⚙️ System Parameters (Model)", expanded=False):
            st.info("Define the generic inverter and module parameters for the simulation.")
            
            c_inv, c_mod = st.columns(2)
            
            default_dc = float(plant_data.get('dc_size_kw', 100.0))
            
            with c_inv:
                st.markdown("**Inverter Specs**")
                p_ac = st.number_input("Rated AC Power (kW)", value=default_dc*0.8, min_value=1.0)
                p_dc_lim = st.number_input("Max DC Input (kW)", value=default_dc*1.2, help="Used for Pdco")
                _eff_ref = st.number_input("Ref Efficiency (%)", value=98.0)
                
            with c_mod:
                st.markdown("**Module Specs**")
                st.markdown(f"Using site total DC size: **{default_dc} kW**")
                temp_coeff = st.number_input("Temp Coeff (%/C)", value=-0.35, step=0.01)

            # Build generic params dictionaries
            inv_params = {
                'Paco': p_ac * 1000, 
                'Pdco': p_dc_lim * 1000,
                'Vdco': 600,
                'Pso': p_ac * 1000 * 0.01,
                'C0': 0, 'C1': 0, 'C2': 0, 'C3': 0, 'Pnt': 0 
            }
            
            mod_params = {
                'Name': 'Generic Module', 'BIPV': 'N', 'Date': '10/5/2020', 'T_NOCT': 45, 'A_c': 1.7, 'N_s': 60,
                'I_sc_ref': 10, 'V_oc_ref': 40, 'I_mp_ref': 9, 'V_mp_ref': 34, 'alpha_sc': 0.003, 'beta_oc': -0.12,
                'a_ref': 1.5, 'I_L_ref': 10.1, 'I_o_ref': 1e-10, 'R_s': 0.3, 'R_sh_ref': 500, 'Adjust': 10,
                'gamma_r': temp_coeff, 'Version': 'MM106',
                'PTC': 0.9 * (default_dc * 1000), 
                'Technology': 'Mono-c-Si',
                'STC': default_dc * 1000 
            }

        # 4. Simulation Settings
        c_yr, c_api = st.columns([1, 2])
        sim_year = c_yr.selectbox("Year (NREL PSM3)", options=[2022, 2021, 2020], index=0)
        nrel_key = c_api.text_input("NREL API Key", value="DEMO_KEY", type="password", help="Sign up at developer.nrel.gov")
        nrel_email = c_api.text_input("NREL Email", value="user@example.com")
        
        # 5. Run
        if st.button("🚀 Run Twin Simulation", type="primary"):
            with st.spinner("Fetching weather data and simulating..."):
                try:
                    res_df, report = orch.run_clipping_analysis(
                        plant_alias=selected_alias,
                        year=sim_year,
                        module_params=mod_params,
                        inverter_params=inv_params,
                        api_key=nrel_key,
                        email=nrel_email
                    )
                    
                    # Display Results
                    st.divider()
                    st.subheader("Analysis Results")
                    
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Unconstrained Energy", f"{report['total_energy_real_kwh'] + report['total_energy_loss_kwh']:.0f} kWh")
                    m2.metric("Actual (Clipped) Energy", f"{report['total_energy_real_kwh']:.0f} kWh")
                    m3.metric("Clipping Loss", f"{report['clipping_loss_pct']:.2f}%", f"-{report['total_energy_loss_kwh']:.0f} kWh", delta_color="inverse")
                    
                    # Chart
                    st.subheader("Clipping Events")
                    loss_days = res_df[res_df['Clipping_Loss_Power'] > 0].index.normalize().unique()
                    
                    if len(loss_days) > 0:
                        st.info(f"Detected clipping on {len(loss_days)} days.")
                        top_loss_day = res_df.groupby(res_df.index.date)['Clipping_Loss_Power'].sum().idxmax()

                        day_view = res_df[res_df.index.date == top_loss_day]

                        st.line_chart(day_view[['Real_AC_Power', 'Unclipped_Potential_AC']])
                        st.caption(f"Profile for {top_loss_day} (Day with max clipping)")

                        # Add to Report button for clipping simulation results
                        add_to_report_button(
                            content=res_df.reset_index() if hasattr(res_df, 'reset_index') else res_df,
                            title=f"Clipping Analysis Results - {selected_alias}",
                            item_type='table',
                            description=f"Twin simulation results showing real AC power, unclipped potential, and clipping losses for {sim_year}",
                            source_page="Clipping Loss Analysis",
                            button_key=f"add_clipping_loss_results_{selected_alias.replace(' ', '_')}"
                        )
                    else:
                        st.success("No significant clipping detected with these settings.")
                        
                except Exception as e:
                    st.error(f"Simulation failed: {str(e)}")
