"""Components package."""
from .data_health import data_health_dashboard, data_health_indicator, data_quality_uploader, render_data_health_badge
from .job_monitor import (
    auto_refresh_on_active_jobs,
    check_job_completion,
    job_monitor_sidebar,
    job_status_viewer,
    submit_background_job_button,
)
from .sidebar import get_navigation_state, render_sidebar
from .ux import (
    UndoRedoBuffer,
    drag_drop_uploader,
    render_breadcrumbs,
    render_empty_state,
    render_onboarding_tour,
)

# Phase 2 Components
from .kpi_cards import render_kpi_row, render_kpi_card_single, render_status_badge as render_status_badge_v2
from .breadcrumbs import render_breadcrumbs as render_breadcrumbs_v2
from .layouts import page_header, two_column_layout, card_grid, filter_bar, metric_section

# Phase 1 Components
try:
    from .preferences_ui import render_preferences_page, render_quick_preferences_sidebar  # noqa: F401
except ImportError:
    pass

try:
    from .global_search import render_search_bar_compact, render_search_dialog  # noqa: F401
except ImportError:
    pass

try:
    from .keyboard_shortcuts import init_shortcuts_in_session, inject_keyboard_handler  # noqa: F401
except ImportError:
    pass

try:
    from .contextual_help import render_contextual_help_sidebar, render_help_center  # noqa: F401
except ImportError:
    pass

__all__ = [
    'render_sidebar',
    'get_navigation_state',
    'job_monitor_sidebar',
    'submit_background_job_button',
    'job_status_viewer',
    'check_job_completion',
    'auto_refresh_on_active_jobs',
    'data_health_indicator',
    'data_health_dashboard',
    'data_quality_uploader',
    'render_data_health_badge',
    'render_breadcrumbs',
    'render_empty_state',
    'drag_drop_uploader',
    'render_onboarding_tour',
    'UndoRedoBuffer',
]
