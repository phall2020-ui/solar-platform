"""
Streamlit component for background job monitoring and management.
Provides UI to trigger, monitor, and view results of background jobs.
"""
import time
from collections.abc import Callable
from typing import Any

import streamlit as st

from services.background_jobs import Job, JobStatus, get_job_manager


def render_job_status_badge(status: JobStatus) -> str:
    """Render a colored status badge."""
    colors = {
        JobStatus.PENDING: "🟡",
        JobStatus.RUNNING: "🔵",
        JobStatus.COMPLETED: "🟢",
        JobStatus.FAILED: "🔴",
        JobStatus.CANCELLED: "⚫"
    }
    return f"{colors.get(status, '⚪')} {status.value.upper()}"


def job_monitor_sidebar():
    """Display job monitor in sidebar."""
    manager = get_job_manager()
    jobs = manager.get_all_jobs()
    
    if not jobs:
        return
    
    with st.sidebar:
        st.divider()
        st.subheader("🔧 Background Jobs")
        
        # Count jobs by status
        pending = sum(1 for j in jobs.values() if j.status == JobStatus.PENDING)
        running = sum(1 for j in jobs.values() if j.status == JobStatus.RUNNING)
        completed = sum(1 for j in jobs.values() if j.status == JobStatus.COMPLETED)
        failed = sum(1 for j in jobs.values() if j.status == JobStatus.FAILED)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Running", running)
        with col2:
            st.metric("Pending", pending)
        with col3:
            st.metric("Done", completed)
        
        if failed > 0:
            st.error(f"⚠️ {failed} job(s) failed")
        
        # Show active jobs
        active_jobs = [j for j in jobs.values() if j.status in [JobStatus.PENDING, JobStatus.RUNNING]]
        if active_jobs:
            for job in active_jobs[:3]:  # Show up to 3 active jobs
                with st.container():
                    st.caption(f"{render_job_status_badge(job.status)} {job.name}")
                    if job.status == JobStatus.RUNNING and job.progress > 0:
                        st.progress(job.progress)
                        if job.progress_message:
                            st.caption(job.progress_message)


def submit_background_job_button(
    label: str,
    func: Callable,
    job_name: str,
    *args,
    key: str | None = None,
    on_complete: Callable[[Any], None] | None = None,
    **kwargs
) -> str | None:
    """
    Render a button that submits a background job.
    
    Args:
        label: Button label
        func: Function to execute in background
        job_name: Human-readable job name
        *args: Arguments to pass to func
        key: Streamlit widget key
        on_complete: Callback to execute when job completes (receives result)
        **kwargs: Keyword arguments to pass to func
        
    Returns:
        Job ID if submitted, None otherwise
    """
    if st.button(label, key=key):
        manager = get_job_manager()
        job_id = manager.submit_job(func, job_name, *args, **kwargs)
        st.success(f"✅ Job '{job_name}' submitted!")
        st.info(f"Job ID: `{job_id}`")
        
        # Store job ID in session state for tracking
        if "background_jobs" not in st.session_state:
            st.session_state.background_jobs = []
        st.session_state.background_jobs.append({
            "job_id": job_id,
            "name": job_name,
            "on_complete": on_complete
        })
        
        return job_id
    return None


def job_status_viewer():
    """Display detailed job status viewer."""
    st.subheader("📋 Background Jobs")
    
    manager = get_job_manager()
    jobs = manager.get_all_jobs()
    
    if not jobs:
        st.info("No background jobs running or completed.")
        return
    
    # Tabs for different job statuses
    tab1, tab2, tab3, tab4 = st.tabs(["Active", "Completed", "Failed", "All"])
    
    with tab1:
        active_jobs = [j for j in jobs.values() if j.status in [JobStatus.PENDING, JobStatus.RUNNING]]
        if not active_jobs:
            st.info("No active jobs.")
        else:
            for job in sorted(active_jobs, key=lambda j: j.created_at, reverse=True):
                _render_job_card(job)
    
    with tab2:
        completed_jobs = [j for j in jobs.values() if j.status == JobStatus.COMPLETED]
        if not completed_jobs:
            st.info("No completed jobs.")
        else:
            for job in sorted(completed_jobs, key=lambda j: j.completed_at or j.created_at, reverse=True):
                _render_job_card(job)
    
    with tab3:
        failed_jobs = [j for j in jobs.values() if j.status == JobStatus.FAILED]
        if not failed_jobs:
            st.info("No failed jobs.")
        else:
            for job in sorted(failed_jobs, key=lambda j: j.completed_at or j.created_at, reverse=True):
                _render_job_card(job)
    
    with tab4:
        for job in sorted(jobs.values(), key=lambda j: j.created_at, reverse=True):
            _render_job_card(job)
    
    # Cleanup button
    if st.button("🧹 Clear Completed Jobs"):
        manager.cleanup_old_jobs(max_age_hours=0)
        st.rerun()


def _render_job_card(job: Job):
    """Render a job information card."""
    with st.expander(f"{render_job_status_badge(job.status)} {job.name}", expanded=(job.status == JobStatus.RUNNING)):
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.text(f"Job ID: {job.job_id}")
            st.text(f"Created: {job.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
            
            if job.started_at:
                st.text(f"Started: {job.started_at.strftime('%Y-%m-%d %H:%M:%S')}")
            
            if job.completed_at:
                st.text(f"Completed: {job.completed_at.strftime('%Y-%m-%d %H:%M:%S')}")
                
                # Calculate duration
                if job.started_at:
                    duration = (job.completed_at - job.started_at).total_seconds()
                    st.text(f"Duration: {duration:.1f}s")
        
        with col2:
            if job.status == JobStatus.RUNNING:
                st.progress(job.progress)
                if job.progress_message:
                    st.caption(job.progress_message)
        
        # Show error if failed
        if job.status == JobStatus.FAILED and job.error:
            st.error(f"Error: {job.error}")
        
        # Show result if completed (only for simple types)
        if job.status == JobStatus.COMPLETED and job.result is not None:
            if isinstance(job.result, (str, int, float, bool)):
                st.success(f"Result: {job.result}")
            elif isinstance(job.result, dict):
                st.json(job.result)
            else:
                st.info(f"Result type: {type(job.result).__name__}")


def check_job_completion():
    """Check for completed jobs and trigger callbacks."""
    if "background_jobs" not in st.session_state:
        return
    
    manager = get_job_manager()
    completed_jobs = []
    
    for tracked_job in st.session_state.background_jobs:
        job_id = tracked_job["job_id"]
        job = manager.get_job(job_id)
        
        if job and job.status == JobStatus.COMPLETED:
            # Trigger callback if provided
            if tracked_job["on_complete"] and job.result is not None:
                try:
                    tracked_job["on_complete"](job.result)
                except Exception as e:
                    st.error(f"Callback error for job '{tracked_job['name']}': {e}")
            
            completed_jobs.append(tracked_job)
    
    # Remove completed jobs from tracking
    for completed in completed_jobs:
        st.session_state.background_jobs.remove(completed)


def auto_refresh_on_active_jobs(interval: int = 2):
    """
    Auto-refresh page if there are active background jobs.
    
    Args:
        interval: Refresh interval in seconds
    """
    manager = get_job_manager()
    jobs = manager.get_all_jobs()
    
    active_count = sum(
        1 for j in jobs.values()
        if j.status in [JobStatus.PENDING, JobStatus.RUNNING]
    )
    
    if active_count > 0:
        # Use a placeholder with automatic refresh
        placeholder = st.empty()
        with placeholder.container():
            st.info(f"🔄 {active_count} active job(s) - auto-refreshing...")
        time.sleep(interval)
        st.rerun()
