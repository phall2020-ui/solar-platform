"""Styles package."""
from .theme import (
    apply_theme,
    render_kpi_card,
    render_section_header,
    render_status_badge,
    render_metric_row,
    get_chart_config,
    get_chart_layout,
    render_divider,
    render_alert,
)

# Phase 2: Design token system (single source of truth for colors, fonts, spacing)
from .design_tokens import (
    AMPYR_TEAL,
    AMPYR_TEAL_LIGHT,
    AMPYR_GREEN,
    STATUS_COLORS,
    CHART_COLORS,
    BG_COLORS,
    FONT_FAMILY,
    FONT_SIZES,
    SPACING,
    PLOTLY_TEMPLATE,
)

__all__ = [
    'apply_theme',
    'render_kpi_card',
    'render_section_header',
    'render_status_badge',
    'render_metric_row',
    'get_chart_config',
    'get_chart_layout',
    'render_divider',
    'render_alert',
    # Design tokens
    'AMPYR_TEAL',
    'AMPYR_TEAL_LIGHT',
    'AMPYR_GREEN',
    'STATUS_COLORS',
    'CHART_COLORS',
    'BG_COLORS',
    'FONT_FAMILY',
    'FONT_SIZES',
    'SPACING',
    'PLOTLY_TEMPLATE',
]
