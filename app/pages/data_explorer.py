"""
Data Explorer Module
Demonstrates new features: background jobs, incremental ETL, and caching.
"""
import time

import pandas as pd
import streamlit as st

from components import (
    check_job_completion,
    data_health_dashboard,
    data_quality_uploader,
    job_status_viewer,
    submit_background_job_button,
)
from solar_platform.services.cache_layer import get_cache_layer
from solar_platform.services.incremental_etl import IncrementalETL
from solar_platform.services.reporting_bridge import reporting
from app.config_compat import config


@st.cache_data(ttl=300)
def _load_available_plants() -> list:
    """Fetch distinct plant/site names from reporting data."""
    try:
        if reporting.is_available():
            ok, df = reporting.query_data("SELECT DISTINCT Site FROM solar_data ORDER BY Site")
            if ok and df is not None and 'Site' in df.columns:
                return df['Site'].dropna().astype(str).tolist()
    except Exception:
        pass
    return []


def render():
    """Render the Data Explorer page."""
    st.title("🔍 Data Explorer")
    st.markdown("Advanced data operations with background jobs, validation, and caching")
    
    # Check for job completions
    check_job_completion()
    
    # Create tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "📤 Data Upload",
        "🏥 Data Health",
        "📋 Background Jobs",
        "💾 Cache Management"
    ])
    
    with tab1:
        render_data_upload_tab()
    
    with tab2:
        render_data_health_tab()
    
    with tab3:
        render_background_jobs_tab()
    
    with tab4:
        render_cache_management_tab()
    
    # Plant selector
    available_plants = _load_available_plants()
    plant_options = available_plants if available_plants else ["No plants found"]
    _selected_plant = st.selectbox("Select Plant", options=plant_options)


def render_data_upload_tab():
    """Render data upload tab with validation."""
    st.header("📤 Data Upload & Validation")
    
    st.markdown("""
    Upload data with automatic quality validation and incremental loading:
    - **Schema validation** with pydantic
    - **Data quality checks** (nulls, duplicates, ranges)
    - **Incremental loading** by date
    - **Automatic blocking** on validation failures
    """)
    
    # Use the data quality uploader component
    data_quality_uploader(
        db_path=str(config.REPORTING_DB),
        table_name="Imported_Portfolio_Data"
    )
    
    st.divider()
    
    # Manual ETL demo
    with st.expander("🔧 Advanced: Manual ETL Operations"):
        st.subheader("ETL Metadata")
        
        etl = IncrementalETL(str(config.REPORTING_DB))
        
        table_name = st.text_input("Table Name", value="Imported_Portfolio_Data")
        
        if st.button("Get Ingestion Info"):
            info = etl.get_last_ingestion_info(table_name)
            if info:
                st.json(info)
            else:
                st.warning(f"No ingestion data for table '{table_name}'")


def render_data_health_tab():
    """Render data health monitoring tab."""
    st.header("🏥 Data Health Monitoring")
    
    st.markdown("""
    Monitor data quality across all tables with validation reports:
    - Real-time health status badges
    - Detailed validation check results
    - Historical ingestion tracking
    """)
    
    # Use the data health dashboard component
    data_health_dashboard(str(config.REPORTING_DB))


def render_background_jobs_tab():
    """Render background jobs management tab."""
    st.header("📋 Background Jobs")
    
    st.markdown("""
    Run long-running tasks in the background without blocking the UI:
    - API scans and data pulls
    - Report generation
    - Large aggregations
    """)
    
    st.divider()
    
    # Demo job submissions
    st.subheader("🚀 Submit Demo Jobs")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Quick job
        submit_background_job_button(
            label="Run Quick Job (5s)",
            func=demo_quick_job,
            job_name="Quick Demo Job",
            key="quick_job_btn"
        )
    
    with col2:
        # Long job
        submit_background_job_button(
            label="Run Long Job (20s)",
            func=demo_long_job,
            job_name="Long Demo Job",
            key="long_job_btn"
        )
    
    # Report generation example
    st.divider()
    st.subheader("📊 Generate Report (Background)")
    
    if reporting.is_available():
        tables = reporting.get_tables()
        if tables:
            table = st.selectbox("Select Table", options=tables)
            
            if submit_background_job_button(
                label="Generate Summary Report",
                func=generate_summary_report,
                job_name=f"Summary Report: {table}",
                table_name=table,
                key="report_job_btn"
            ):
                st.info("Report generation started in background. Check job status below.")
    else:
        st.warning("Reporting service not available")
    
    st.divider()
    
    # Job status viewer
    job_status_viewer()


def render_cache_management_tab():
    """Render cache management tab."""
    st.header("💾 Cache Management")
    
    st.markdown("""
    Centralized caching layer for expensive operations:
    - SQLite-backed persistent cache
    - Configurable TTL (time-to-live)
    - Cache warming on startup
    - Namespace-based organization
    """)
    
    cache = get_cache_layer(backend="sqlite", db_path=str(config.REPORTING_DB), default_ttl=300)
    
    # Cache stats
    st.subheader("📊 Cache Statistics")
    stats = cache.get_stats()
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Entries", stats.get("total_entries", 0))
    with col2:
        st.metric("Total Hits", stats.get("total_hits", 0))
    with col3:
        st.metric("Namespaces", len(stats.get("namespaces", [])))
    
    if stats.get("namespaces"):
        st.write("**Active Namespaces:**")
        for ns in stats["namespaces"]:
            st.code(ns)
    
    st.divider()
    
    # Cache operations
    st.subheader("🔧 Cache Operations")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🧹 Clear All Cache"):
            cache.clear()
            st.success("Cache cleared!")
            st.rerun()
    
    with col2:
        if st.button("♻️ Cleanup Expired"):
            deleted = cache.cleanup_expired()
            st.success(f"Removed {deleted} expired entries")
            st.rerun()
    
    with col3:
        namespace = st.text_input("Namespace to clear", placeholder="e.g., portfolio_summary")
        if namespace and st.button(f"Clear '{namespace}'"):
            cache.clear(namespace=namespace)
            st.success(f"Cleared namespace: {namespace}")
            st.rerun()
    
    st.divider()
    
    # Cache warming demo
    st.subheader("🔥 Cache Warming")
    
    st.markdown("""
    Pre-populate cache with frequently accessed data for faster first-page load.
    """)
    
    if st.button("Warm Portfolio Summary Cache"):
        with st.spinner("Warming cache..."):
            if reporting.is_available():
                tables = reporting.get_tables()
                data_tables = [t for t in tables if not t.startswith('_')]
                
                if data_tables:
                    # Warm cache for first table
                    table = data_tables[0]
                    colmap = {
                        'Site': 'Site',
                        'Gen_Budget_kWh': 'Gen_Budget_kWh',
                        'Gen_Actual_kWh': 'Gen_Actual_kWh',
                        'PR': 'PR',
                        'Availability': 'Availability'
                    }
                    
                    summary = reporting.get_portfolio_summary(table, colmap)
                    st.success(f"Cache warmed for table: {table}")
                    st.json(summary)
                else:
                    st.warning("No data tables available")
            else:
                st.error("Reporting service not available")


# Demo job functions
def demo_quick_job():
    """Quick demo job that completes in 5 seconds."""
    for i in range(5):
        time.sleep(1)
    return {"status": "completed", "duration": "5 seconds"}


def demo_long_job():
    """Long demo job that takes 20 seconds with progress updates."""
    import threading

    from solar_platform.services.background_jobs import get_job_manager
    
    job_id = None
    # Get current job ID from thread name
    _thread_name = threading.current_thread().name
    manager = get_job_manager()
    
    # Find job ID by matching thread (this is a workaround)
    # In production, you'd pass job_id as parameter
    for jid, job in manager.get_all_jobs().items():
        if job.name == "Long Demo Job" and job.status.value == "running":
            job_id = jid
            break
    
    for i in range(20):
        time.sleep(1)
        if job_id:
            progress = (i + 1) / 20
            manager.update_progress(job_id, progress, f"Processing step {i+1}/20")
    
    return {
        "status": "completed",
        "duration": "20 seconds",
        "message": "Long job finished successfully!"
    }


def generate_summary_report(table_name: str):
    """Generate a summary report for a table."""
    time.sleep(3)  # Simulate work
    
    # Get summary
    colmap = {
        'Site': 'Site',
        'Gen_Budget_kWh': 'Gen_Budget_kWh',
        'Gen_Actual_kWh': 'Gen_Actual_kWh',
        'PR': 'PR',
        'Availability': 'Availability'
    }
    
    summary = reporting.get_portfolio_summary(table_name, colmap)
    
    return {
        "table": table_name,
        "summary": summary,
        "generated_at": pd.Timestamp.now().isoformat()
    }
