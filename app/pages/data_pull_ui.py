"""
Data Pull — Streamlit module for Juggle/EMIG data ingestion.

Provides UI to:
  - Discover plants from the Juggle API
  - View registered plants and their data status
  - Trigger background data pulls (all plants or individual)
  - Monitor pull progress and results
"""

import logging

import streamlit as st

from app.components.job_monitor import (
    auto_refresh_on_active_jobs,
    job_status_viewer,
    render_job_status_badge,
)
from solar_platform.services.background_jobs import JobStatus, get_job_manager, submit_background_job

logger = logging.getLogger(__name__)


def _get_service():
    """Lazily import and create the data pull service."""
    from solar_platform.services.data_pull import JuggleDataPullService
    return JuggleDataPullService()


def render():
    """Main entry point for the Data Pull page."""
    st.title("📡 Juggle Data Pull")
    st.caption("Fetch inverter & weather data from the Juggle/EMIG API into the platform database.")

    # Auto-refresh if jobs are running
    auto_refresh_on_active_jobs(interval=3)

    # Tabs
    tab_pull, tab_status, tab_jobs = st.tabs(["⬇️ Pull Data", "📊 Data Status", "🔧 Jobs"])

    with tab_pull:
        _render_pull_tab()

    with tab_status:
        _render_status_tab()

    with tab_jobs:
        job_status_viewer()


def _render_pull_tab():
    """Render the data pull controls."""
    svc = _get_service()

    # Check API key
    if not svc.api_key:
        st.error(
            "**No API key configured.** Set `JUGGLE_API_KEY` or `EMIG_API_KEY` "
            "in your `.env` file or environment variables."
        )
        st.code("# Add to platform/.env\nJUGGLE_API_KEY=your-api-key-here", language="bash")
        return

    st.success(f"✅ API key configured (ends …{svc.api_key[-6:]})")

    # ── Section 1: Plant Discovery ──────────────────────────────
    st.subheader("1️⃣ Discover & Register Plants")
    st.caption(
        "Connect to the Juggle API to discover all accessible plants "
        "and cross-reference with the Notion asset register (source of "
        "truth for names and DC capacities)."
    )

    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("🔍 Discover Plants", use_container_width=True, type="primary"):
            from solar_platform.services.data_pull import bg_discover_plants

            job_id = submit_background_job(
                bg_discover_plants, "Discover Juggle Plants"
            )
            st.session_state["last_discover_job"] = job_id
            st.toast("Plant discovery started…")
            st.rerun()

    # Show result of last discovery
    if "last_discover_job" in st.session_state:
        manager = get_job_manager()
        job = manager.get_job(st.session_state["last_discover_job"])
        if job:
            if job.status == JobStatus.COMPLETED and isinstance(job.result, dict):
                plants = job.result.get("plants", [])
                st.success(f"Found **{len(plants)}** plants")
                if plants:
                    import pandas as pd
                    df = pd.DataFrame(plants)
                    # Highlight name differences between API and Notion
                    renamed = [p for p in plants if p.get("name") != p.get("api_name")]
                    if renamed:
                        st.info(
                            f"🔗 **{len(renamed)}** plant(s) renamed to match Notion asset register"
                        )
                    st.dataframe(df, use_container_width=True, hide_index=True)
            elif job.status == JobStatus.FAILED:
                st.error(f"Discovery failed: {job.error}")
            elif job.status == JobStatus.RUNNING:
                st.info(f"🔄 Discovery in progress… {job.progress_message}")
                st.progress(job.progress)

    st.divider()

    # ── Section 2: Data Pull ────────────────────────────────────
    st.subheader("2️⃣ Pull Readings Data")

    plants = svc.get_registered_plants()
    if not plants:
        st.warning(
            "No plants registered yet. Click **Discover Plants** above first."
        )
        return

    st.caption(f"**{len(plants)}** plants registered in the database.")

    # Pull controls
    col_days, col_scope, col_action = st.columns([1, 2, 1])

    with col_days:
        days_back = st.number_input(
            "Days to pull",
            min_value=1,
            max_value=365,
            value=7,
            help="How many days of historical data to fetch (from today backwards).",
        )

    with col_scope:
        scope = st.radio(
            "Scope",
            ["All plants", "Single plant"],
            horizontal=True,
        )
        selected_plant_uid = None
        if scope == "Single plant":
            plant_options = {p["alias"]: p["plant_uid"] for p in plants}
            selected_alias = st.selectbox("Select plant", list(plant_options.keys()))
            selected_plant_uid = plant_options.get(selected_alias)

    with col_action:
        st.write("")  # Spacing
        st.write("")
        pull_clicked = st.button(
            "🚀 Start Pull",
            use_container_width=True,
            type="primary",
        )

    if pull_clicked:
        from solar_platform.services.data_pull import bg_pull_all_plants, bg_pull_single_plant

        if scope == "All plants":
            job_id = submit_background_job(
                bg_pull_all_plants, "Pull All Plants", days_back=days_back
            )
            st.toast(f"Data pull started for all {len(plants)} plants…")
        else:
            job_id = submit_background_job(
                bg_pull_single_plant, f"Pull {selected_alias}",
                plant_uid=selected_plant_uid, days_back=days_back
            )
            st.toast(f"Data pull started for {selected_alias}…")

        st.session_state["last_pull_job"] = job_id
        st.rerun()

    # Show result of last pull
    if "last_pull_job" in st.session_state:
        _render_pull_result(st.session_state["last_pull_job"])

    # Rate limiting info
    st.divider()
    with st.expander("ℹ️ Rate Limiting & API Details"):
        st.markdown("""
        **Rate limits applied:**
        - **60 requests/minute** sliding window
        - **1.2 second** minimum gap between requests
        - Automatic retry with exponential backoff on errors
        - Date ranges chunked to ≤90 days per request

        **API endpoint:** `https://www.emig.co.uk/p/api`

        **Data resolution:** Half-hourly (1800s intervals)

        Large portfolios may take several minutes to complete. The pull runs
        entirely in the background — you can navigate away and check back later.
        """)


def _render_pull_result(job_id: str):
    """Show the result of a data pull job."""
    manager = get_job_manager()
    job = manager.get_job(job_id)
    if not job:
        return

    if job.status == JobStatus.RUNNING:
        st.info(f"🔄 Pull in progress… {job.progress_message}")
        st.progress(job.progress)

    elif job.status == JobStatus.COMPLETED and isinstance(job.result, dict):
        result = job.result
        duration = result.get("duration_s", 0)

        if result.get("error"):
            st.error(result["error"])
            return

        # Summary metrics
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Plants", f"{result.get('plants_succeeded', 0)}/{result.get('plants_attempted', 0)}")
        with c2:
            st.metric("Readings Fetched", f"{result.get('total_readings', result.get('readings_fetched', 0)):,}")
        with c3:
            st.metric("Stored", f"{result.get('total_stored', result.get('readings_stored', 0)):,}")
        with c4:
            st.metric("Duration", f"{duration:.0f}s")

        # Per-plant details
        plant_results = result.get("plant_results", [])
        if plant_results:
            import pandas as pd
            df = pd.DataFrame([
                {
                    "Plant": r["alias"],
                    "Devices": r["devices"],
                    "Readings": r["readings_fetched"],
                    "Stored": r["readings_stored"],
                    "Errors": len(r.get("errors", [])),
                }
                for r in plant_results
            ])
            st.dataframe(df, use_container_width=True, hide_index=True)

        # Show errors if any
        errors = result.get("errors", [])
        if errors:
            with st.expander(f"⚠️ {len(errors)} error(s)", expanded=False):
                for err in errors:
                    st.warning(err)

    elif job.status == JobStatus.FAILED:
        st.error(f"Pull failed: {job.error}")

    elif job.status == JobStatus.PENDING:
        st.info("⏳ Pull job queued, waiting for worker…")


def _render_status_tab():
    """Render the data status overview."""
    svc = _get_service()
    status = svc.get_data_status()

    if status.get("error"):
        st.error(f"Error reading database: {status['error']}")
        return

    # Overview metrics
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Registered Plants", status["plant_count"])
    with col2:
        st.metric("Total Readings", f"{status['total_readings']:,}")

    # Per-plant breakdown
    plants = status.get("plants", [])
    if plants:
        import pandas as pd
        df = pd.DataFrame([
            {
                "Plant": p["alias"],
                "UID": p["plant_uid"],
                "Readings": f"{p['reading_count']:,}",
                "Earliest": p["earliest"] or "—",
                "Latest": p["latest"] or "—",
            }
            for p in plants
        ])
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No plants registered yet. Use the **Pull Data** tab to discover and register plants.")

    # Refresh button
    if st.button("🔄 Refresh Status"):
        st.rerun()
