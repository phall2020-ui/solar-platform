"""
Data health monitoring component.
Displays data quality status and validation reports in the UI.
"""
import json

import streamlit as st

from solar_platform.services.incremental_etl import IncrementalETL


def render_data_health_badge(status: str = "unknown") -> str:
    """
    Render data health status badge.
    
    Args:
        status: Status string ("passed", "warning", "failed", "unknown")
        
    Returns:
        Formatted badge string
    """
    badges = {
        "passed": "🟢 HEALTHY",
        "warning": "🟡 WARNING",
        "failed": "🔴 FAILED",
        "unknown": "⚪ UNKNOWN"
    }
    return badges.get(status, "⚪ UNKNOWN")


def data_health_indicator(db_path: str, table_name: str):
    """
    Display data health indicator for a table.
    
    Args:
        db_path: Path to database
        table_name: Table name to check
    """
    etl = IncrementalETL(db_path)
    info = etl.get_last_ingestion_info(table_name)
    
    if not info:
        st.warning(f"⚠️ No ingestion data for `{table_name}`")
        return
    
    status = info.get("last_validation_status", "unknown")
    
    # Display badge
    st.markdown(f"**Data Health:** {render_data_health_badge(status)}")
    
    # Show last ingestion time
    if info.get("last_ingestion_timestamp"):
        st.caption(f"Last ingested: {info['last_ingestion_timestamp']}")
    
    # Show row count
    if info.get("total_rows"):
        st.caption(f"Total rows: {info['total_rows']:,}")


def data_health_dashboard(db_path: str):
    """
    Display comprehensive data health dashboard.
    
    Args:
        db_path: Path to database
    """
    st.subheader("🏥 Data Health Dashboard")
    
    etl = IncrementalETL(db_path)
    
    # Get all tables with metadata
    from solar_platform.db.utils import get_connection
    with get_connection(db_path, read_only=True) as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT table_name FROM {etl.metadata_table}")
        tables = [row[0] for row in cursor.fetchall()]
    
    if not tables:
        st.info("No data ingestion metadata available. Load data to see health status.")
        return
    
    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    
    healthy = 0
    warnings = 0
    failed = 0
    
    for table in tables:
        info = etl.get_last_ingestion_info(table)
        if info:
            status = info.get("last_validation_status", "unknown")
            if status == "passed":
                healthy += 1
            elif status == "warning":
                warnings += 1
            elif status == "failed":
                failed += 1
    
    with col1:
        st.metric("Total Tables", len(tables))
    with col2:
        st.metric("🟢 Healthy", healthy)
    with col3:
        st.metric("🟡 Warnings", warnings)
    with col4:
        st.metric("🔴 Failed", failed)
    
    # Table details
    st.divider()
    
    for table in tables:
        info = etl.get_last_ingestion_info(table)
        if not info:
            continue
        
        status = info.get("last_validation_status", "unknown")
        
        with st.expander(f"{render_data_health_badge(status)} {table}", expanded=(status == "failed")):
            col1, col2 = st.columns(2)
            
            with col1:
                st.text(f"Last Ingestion: {info.get('last_ingestion_timestamp', 'N/A')}")
                st.text(f"Total Rows: {info.get('total_rows', 0):,}")
                st.text(f"Max Date: {info.get('last_max_date', 'N/A')}")
            
            with col2:
                st.text(f"Status: {status.upper()}")
            
            # Show validation report if available
            if info.get("last_validation_report"):
                try:
                    report_dict = json.loads(info["last_validation_report"].replace("'", '"'))
                    
                    st.subheader("Validation Report")
                    
                    # Summary
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("✅ Passed", report_dict.get("passed", 0))
                    with col2:
                        st.metric("⚠️ Warnings", report_dict.get("warnings", 0))
                    with col3:
                        st.metric("❌ Failed", report_dict.get("failed", 0))
                    
                    # Individual checks
                    if report_dict.get("checks"):
                        st.subheader("Checks")
                        for check in report_dict["checks"]:
                            check_status = check.get("status", "unknown")
                            icon = {"passed": "✅", "warning": "⚠️", "failed": "❌"}.get(check_status, "ℹ️")
                            
                            st.markdown(f"{icon} **{check['name']}**: {check['message']}")
                            
                            # Show details if available
                            if check.get("details"):
                                with st.expander("Details"):
                                    st.json(check["details"])
                
                except Exception as e:
                    st.error(f"Error parsing validation report: {e}")


def data_quality_uploader(db_path: str, table_name: str):
    """
    File uploader with automatic data quality validation.
    
    Args:
        db_path: Path to database
        table_name: Target table name
    """
    st.subheader(f"📤 Upload Data to `{table_name}`")
    
    uploaded_file = st.file_uploader(
        "Choose a file (CSV or Excel)",
        type=["csv", "xlsx", "xls"],
        key=f"uploader_{table_name}"
    )
    
    if not uploaded_file:
        return
    
    # Load data
    try:
        import pandas as pd
        
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
        
        st.success(f"✅ Loaded {len(df)} rows, {len(df.columns)} columns")
        
        # Preview
        with st.expander("Preview Data"):
            st.dataframe(df.head(10))
        
        # Options
        col1, col2, col3 = st.columns(3)
        
        with col1:
            validate = st.checkbox("Validate data quality", value=True, key=f"validate_{table_name}")
        
        with col2:
            incremental = st.checkbox("Incremental load", value=True, key=f"incremental_{table_name}")
        
        with col3:
            block_on_failure = st.checkbox("Block on validation failure", value=True, key=f"block_{table_name}")
        
        # Load button
        if st.button(f"Load to {table_name}", key=f"load_{table_name}"):
            with st.spinner("Loading and validating data..."):
                etl = IncrementalETL(db_path)
                
                if incremental:
                    success, report = etl.load_incremental(
                        df,
                        table_name,
                        validate=validate,
                        block_on_failure=block_on_failure
                    )
                else:
                    # Full replace
                    if validate:
                        report = etl.validate_dataframe(df)
                        if not report.is_passed() and block_on_failure:
                            success = False
                        else:
                            from solar_platform.db.utils import get_connection as _dh_get_conn
                            with _dh_get_conn(db_path) as conn:
                                df.to_sql(table_name, conn, if_exists='replace', index=False)
                            success = True
                    else:
                        from solar_platform.db.utils import get_connection as _dh_get_conn
                        with _dh_get_conn(db_path) as conn:
                            df.to_sql(table_name, conn, if_exists='replace', index=False)
                        success = True
                        from solar_platform.services.incremental_etl import DataQualityReport
                        report = DataQualityReport()
                
                # Display results
                if success:
                    st.success("✅ Data loaded successfully!")
                else:
                    st.error("❌ Data load failed or blocked by validation")
                
                # Show validation report
                if validate:
                    st.subheader("Validation Report")
                    report_dict = report.to_dict()
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("✅ Passed", report_dict.get("passed", 0))
                    with col2:
                        st.metric("⚠️ Warnings", report_dict.get("warnings", 0))
                    with col3:
                        st.metric("❌ Failed", report_dict.get("failed", 0))
                    
                    # Show checks
                    for check in report_dict.get("checks", []):
                        check_status = check.get("status", "unknown")
                        icon = {"passed": "✅", "warning": "⚠️", "failed": "❌"}.get(check_status, "ℹ️")
                        
                        if check_status == "failed":
                            st.error(f"{icon} {check['name']}: {check['message']}")
                        elif check_status == "warning":
                            st.warning(f"{icon} {check['name']}: {check['message']}")
                        else:
                            st.info(f"{icon} {check['name']}: {check['message']}")
    
    except Exception as e:
        st.error(f"Error loading file: {e}")
