"""Convenience re-exports for Streamlit UI components.

Several Streamlit pages import directly from the top-level `components` package
(`from components import ...`). Streamlit adds the directory containing the
entrypoint script (e.g. `app/`) to `sys.path`, so `components` resolves to
`app/components/`.

Keep this file lightweight: only re-export stable component helpers used across
pages to avoid circular imports and unnecessary startup cost.
"""

from __future__ import annotations

# Sidebar/navigation
from .sidebar import get_navigation_state, render_sidebar

# Background job monitoring
from .job_monitor import check_job_completion, job_status_viewer, submit_background_job_button

# Data health & validation
from .data_health import data_health_dashboard, data_quality_uploader

# UX helpers
from .ux import drag_drop_uploader

__all__ = [
    # Sidebar/navigation
    "get_navigation_state",
    "render_sidebar",
    # Background jobs
    "check_job_completion",
    "job_status_viewer",
    "submit_background_job_button",
    # Data health
    "data_health_dashboard",
    "data_quality_uploader",
    # UX
    "drag_drop_uploader",
]
