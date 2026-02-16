"""Convenience re-exports for Streamlit UI components."""
from __future__ import annotations

# Sidebar/navigation — always needed at startup
from .sidebar import get_navigation_state, render_sidebar

# Lazy-loaded module references (populated on first access)
_lazy_cache: dict = {}

def __getattr__(name: str):
    """Lazy-load component helpers on first access."""
    if name in _lazy_cache:
        return _lazy_cache[name]

    if name in ("check_job_completion", "job_status_viewer", "submit_background_job_button"):
        from .job_monitor import check_job_completion, job_status_viewer, submit_background_job_button
        _lazy_cache.update({
            "check_job_completion": check_job_completion,
            "job_status_viewer": job_status_viewer,
            "submit_background_job_button": submit_background_job_button,
        })
        return _lazy_cache[name]

    if name in ("data_health_dashboard", "data_quality_uploader"):
        from .data_health import data_health_dashboard, data_quality_uploader
        _lazy_cache.update({
            "data_health_dashboard": data_health_dashboard,
            "data_quality_uploader": data_quality_uploader,
        })
        return _lazy_cache[name]

    if name == "drag_drop_uploader":
        from .ux import drag_drop_uploader
        _lazy_cache["drag_drop_uploader"] = drag_drop_uploader
        return drag_drop_uploader

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "get_navigation_state",
    "render_sidebar",
    "check_job_completion",
    "job_status_viewer",
    "submit_background_job_button",
    "data_health_dashboard",
    "data_quality_uploader",
    "drag_drop_uploader",
]
