"""Database Viewer (Legacy Wrapper)."""
from datetime import datetime
from pathlib import Path

import streamlit as st
from solar_toolkit.config import settings

from components.report_button import add_to_report_button
from services import legacy_toolkit
from styles import render_alert, render_divider, render_metric_row, render_section_header


def _log_deletion(action: str, detail: str):
    """Append a deletion/audit entry to a local journal."""
    try:
        log_dir = Path("reports")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "deletion_journal.log"
        timestamp = datetime.now().isoformat()
        log_path.write_text(
            f"{timestamp} | {action} | {detail}\n",
            encoding="utf-8",
            errors="ignore",
            append=True  # type: ignore[arg-type]
        )
    except TypeError:
        # Python <3.11 compatibility: manual append
        with open(log_dir / "deletion_journal.log", "a", encoding="utf-8", errors="ignore") as fh:
            fh.write(f"{datetime.now().isoformat()} | {action} | {detail}\n")
    except Exception:
        pass  # Logging should never break the UI

def render():
    """Render the legacy Database Viewer page."""
    orch = legacy_toolkit.get_orchestrator()
    if not orch:
        st.error("Orchestrator not available.")
        return

    # Import dependencies
    try:
        from solar_toolkit.data_viewer import DataViewer
    except ImportError:
        st.error("Could not import DataViewer.")
        return

    st.header("Database Viewer")
    st.markdown("View, filter, edit, and delete data from the database with flexible filtering options.")
    
    # Initialize DataViewer
    viewer = DataViewer(db_path=settings.DB_PATH)
    
    # Create sub-tabs for Plants and Readings
    viewer_mode = st.radio("Data Type", ["Plants Registry", "Operational Readings"], horizontal=True)
    
    if viewer_mode == "Plants Registry":
        render_section_header("Registered Plants", icon="📋")
        try:
            plants_df = viewer.get_plants_data()
            if plants_df.empty:
                render_alert("No plants registered yet.", "info")
            else:
                st.markdown(f"**Total plants:** {len(plants_df)}")
                st.dataframe(plants_df, width=None, height=400, use_container_width=True)

                # Add to Report button for plants registry
                add_to_report_button(
                    content=plants_df,
                    title="Plants Registry",
                    item_type='table',
                    description=f"Complete registry of {len(plants_df)} registered plants",
                    source_page="Database Viewer",
                    button_key="add_db_viewer_plants_registry"
                )

                # Download
                csv = plants_df.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Download Plants Data (CSV)", csv, "plants_registry.csv", "text/csv")
                
                # Delete
                render_divider()
                render_section_header("Delete Plant", icon="🗑️")
                render_alert("Deleting a plant will remove it from the registry. This does NOT delete associated readings.", "warning")
                
                c1, c2 = st.columns([3, 1])
                plant_to_delete = c1.selectbox("Select plant to delete", options=plants_df['alias'].tolist(), key="delete_plant_select")
                confirm_text = st.text_input("Type the alias to confirm deletion", key="delete_plant_confirm")
                delete_disabled = confirm_text.strip() != plant_to_delete
                
                if c2.button("🗑️ Delete Plant", key="delete_plant_btn", disabled=delete_disabled):
                    try:
                        viewer.delete_plant(plant_to_delete)
                        _log_deletion("plant_delete", f"alias={plant_to_delete}")
                        st.success(f"✅ Plant '{plant_to_delete}' deleted successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error deleting plant: {e}")
        except Exception as e:
            st.error(f"Error loading plants: {e}")
    
    else:  # Operational Readings
        render_section_header("Operational Readings", icon="📊")
        try:
            available_plants = viewer.get_unique_plant_uids()
            stats = viewer.get_readings_stats()
            
            metrics = [
                {'title': 'Total Readings', 'value': f"{stats['total_readings']:,}", 'icon': '📊'},
                {'title': 'Unique Plants', 'value': str(stats['unique_plants']), 'icon': '🏭'},
                {'title': 'Unique Devices', 'value': str(stats['unique_devices']), 'icon': '🔌'},
            ]
            if stats['earliest_reading'] and stats['latest_reading']:
                metrics.append({
                    'title': 'Date Range', 
                    'value': f"{stats['earliest_reading'][:10]}...{stats['latest_reading'][:10]}",
                    'icon': '📅'
                })
            
            render_metric_row(metrics)
            
            render_divider()
            render_section_header("Filter Options", icon="🔍")
            
            col1, col2 = st.columns(2)
            
            with col1:
                filter_plant = st.selectbox("Filter by Plant", options=["All"] + available_plants, key="filter_plant")
                selected_plant = None if filter_plant == "All" else filter_plant
                
                device_type = st.selectbox("Device Type", options=["All", "Inverters", "POA (Irradiance)"], key="filter_device_type")
                
                if selected_plant:
                    all_devices = viewer.get_unique_device_ids(selected_plant)
                    date_range = viewer.get_date_range(plant_uid=selected_plant)
                else:
                    all_devices = viewer.get_unique_device_ids()
                    date_range = viewer.get_date_range()
                
                if device_type == "Inverters":
                    available_devices = [d for d in all_devices if d.startswith("INVERT:")]
                elif device_type == "POA (Irradiance)":
                    available_devices = [d for d in all_devices if d.startswith("POA:")]
                else:
                    available_devices = all_devices
                
                filter_device = st.selectbox("Filter by Device", options=["All"] + available_devices, key="filter_device")
                selected_device = None if filter_device == "All" else filter_device
            
            with col2:
                if date_range[0] and date_range[1]:
                    min_date = datetime.fromisoformat(date_range[0][:10])
                    max_date = datetime.fromisoformat(date_range[1][:10])
                    f_start = st.date_input("Start Date", value=min_date, min_value=min_date, max_value=max_date)
                    f_end = st.date_input("End Date", value=max_date, min_value=min_date, max_value=max_date)
                else:
                    f_start, f_end = None, None
                    st.info("No readings yet.")
                
                display_limit = st.number_input("Display Limit", min_value=10, max_value=10000, value=1000, step=100)
            
            if st.button("🔄 Load Data", type="primary"):
                with st.spinner("Loading..."):
                    s_str = f_start.strftime("%Y-%m-%d") if f_start else None
                    e_str = f_end.strftime("%Y-%m-%d") if f_end else None
                    
                    df, total = viewer.get_readings_data(selected_plant, selected_device, s_str, e_str, limit=display_limit)
                    
                    if df.empty:
                        st.info("No readings found.")
                    else:
                        st.success(f"✅ Loaded {len(df)} readings (Total matching: {total:,})")
                        st.dataframe(df, use_container_width=True)

                        # Add to Report button for readings
                        add_to_report_button(
                            content=df,
                            title=f"Operational Readings ({len(df)} records)",
                            item_type='table',
                            description=f"Filtered operational readings data ({len(df)} of {total:,} total matching records)",
                            source_page="Database Viewer",
                            button_key=f"add_db_viewer_readings_{filter_plant.replace(' ', '_')}"
                        )

                        csv = df.to_csv(index=False).encode('utf-8')
                        st.download_button("📥 Download (CSV)", csv, "readings.csv", "text/csv")
                        
                        st.session_state['del_filters'] = {'plant': selected_plant, 'device': selected_device, 'start': s_str, 'end': e_str, 'count': total}

            # Delete
            render_divider()
            render_section_header("Delete Readings", icon="🗑️")
            if 'del_filters' in st.session_state:
                f = st.session_state['del_filters']
                st.write(f"Targets: Plant={f['plant']}, Device={f['device']}, Range={f['start']} to {f['end']}")
                st.write(f"**Total to delete (dry-run): {f['count']:,}**")
                
                c1, c2 = st.columns([3,1])
                confirm_phrase = c1.text_input("Type DELETE to confirm", key="del_confirm_phrase")
                confirm = confirm_phrase.strip().upper() == "DELETE"
                if c2.button("🗑️ Delete Data", disabled=not confirm):
                    deleted = viewer.delete_readings(f['plant'], f['device'], f['start'], f['end'])
                    _log_deletion(
                        "readings_delete",
                        f"plant={f['plant']} device={f['device']} start={f['start']} end={f['end']} deleted={deleted}"
                    )
                    st.success(f"Deleted {deleted:,} readings.")
                    del st.session_state['del_filters']
                    st.rerun()
            else:
                render_alert("Load data to see delete options.", "info")

        except Exception as e:
            st.error(f"Error: {e}")
