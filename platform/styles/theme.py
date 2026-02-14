"""
AMPYR brand theming and styling utilities.
"""
from typing import Optional
import streamlit as st
from unified_config import config


def apply_theme():
    """Apply AMPYR brand theme to the app."""
    st.markdown(config.get_css(), unsafe_allow_html=True)


def render_kpi_card(
    title: str,
    value: str,
    delta: Optional[str] = None,
    delta_positive: bool = True,
    icon: str = "📊"
):
    """
    Render a KPI card using native Streamlit components.
    """
    # Use native Streamlit metric for better compatibility
    delta_display = None
    delta_color = "normal"
    if delta:
        delta_display = delta
        delta_color = "normal" if delta_positive else "inverse"
    
    # Create a styled container
    with st.container():
        st.markdown(f'''<div class="kpi-card {'kpi-card-positive' if delta_positive else 'kpi-card-negative'}"><span style="font-size: 1.5rem;">{icon}</span></div>''', unsafe_allow_html=True)
        st.metric(
            label=title,
            value=value,
            delta=delta_display,
            delta_color=delta_color
        )


def render_section_header(title: str, icon: str = "", description: str = ""):
    """
    Render a section header using native Streamlit components.
    """
    # Build title with icon
    title_text = f"{icon} {title}" if icon else title
    
    # Use native Streamlit header
    st.markdown("---")
    st.subheader(title_text)
    if description:
        st.caption(description)


def render_status_badge(status: str, label: str = None):
    """
    Render a status badge.
    
    Args:
        status: Status type ('success', 'warning', 'error', 'info')
        label: Optional label text (defaults to status)
    """
    label = label or status.title()
    
    colors = {
        'success': config.BRAND_COLORS['positive'],
        'warning': config.BRAND_COLORS['warning'],
        'error': config.BRAND_COLORS['negative'],
        'info': config.BRAND_COLORS['secondary'],
    }
    
    color = colors.get(status, config.BRAND_COLORS['secondary'])
    
    html = f"""
<span style="
    background-color: {color};
    color: white;
    padding: 0.25rem 0.75rem;
    border-radius: 12px;
    font-size: 0.85rem;
    font-weight: 500;
    display: inline-block;
">
    {label}
</span>
"""
    st.markdown(html, unsafe_allow_html=True)


def render_metric_row(metrics: list):
    """
    Render a row of metrics.
    
    Args:
        metrics: List of dicts with keys: title, value, delta (optional), icon (optional)
    """
    cols = st.columns(len(metrics))
    
    for col, metric in zip(cols, metrics):
        with col:
            render_kpi_card(
                title=metric.get('title', ''),
                value=metric.get('value', ''),
                delta=metric.get('delta'),
                delta_positive=metric.get('delta_positive', True),
                icon=metric.get('icon', '📊')
            )


def get_chart_config():
    """Get standardized Plotly chart configuration for AMPYR branding."""
    return {
        'displayModeBar': True,
        'displaylogo': False,
        'modeBarButtonsToRemove': ['pan2d', 'lasso2d', 'select2d'],
    }


def get_chart_layout():
    """Get standardized Plotly chart layout for AMPYR branding."""
    return {
        'font': {
            'family': 'Lato, Arial, sans-serif',
            'size': 12,
            'color': config.BRAND_COLORS['text_secondary']
        },
        'plot_bgcolor': 'rgba(0,0,0,0)',
        'paper_bgcolor': 'rgba(0,0,0,0)',
        'xaxis': {
            'gridcolor': 'rgba(255,255,255,0.08)',
            'linecolor': config.BRAND_COLORS['border'],
            'zerolinecolor': 'rgba(255,255,255,0.1)',
        },
        'yaxis': {
            'gridcolor': 'rgba(255,255,255,0.08)',
            'linecolor': config.BRAND_COLORS['border'],
            'zerolinecolor': 'rgba(255,255,255,0.1)',
        },
        'colorway': config.CHART_COLORS,
        'legend': {
            'bgcolor': 'rgba(0,0,0,0)',
            'font': {'color': config.BRAND_COLORS['text_secondary']},
        },
    }


def render_divider():
    """Render a styled divider."""
    st.markdown(f"""
<hr style="
    margin: 2rem 0;
    border: 0;
    border-top: 1px solid {config.BRAND_COLORS['border']};
">
""", unsafe_allow_html=True)


def render_alert(message: str, current_type: str = "info", icon: str = None):
    """
    Render a styled alert box.
    
    Args:
        message: Content of the alert
        current_type: 'success', 'warning', 'error', 'info'
        icon: Optional custom icon
    """
    colors = {
        'success': config.BRAND_COLORS['positive'],
        'warning': config.BRAND_COLORS['warning'],
        'error': config.BRAND_COLORS['negative'],
        'info': config.BRAND_COLORS['secondary'],
    }
    
    # Dark mode compatible background colors (subtle tinted backgrounds)
    bg_colors = {
        'success': 'rgba(95, 191, 160, 0.15)',   # Teal tint
        'warning': 'rgba(242, 194, 101, 0.15)',  # Amber tint
        'error': 'rgba(230, 107, 107, 0.15)',    # Red tint
        'info': 'rgba(74, 158, 128, 0.15)',      # Secondary tint
    }
    
    default_icons = {
        'success': '✅',
        'warning': '⚠️',
        'error': '❌',
        'info': 'ℹ️',
    }
    
    color = colors.get(current_type, config.BRAND_COLORS['secondary'])
    bg_color = bg_colors.get(current_type, 'rgba(74, 158, 128, 0.15)')
    icon = icon or default_icons.get(current_type, 'ℹ️')
    
    html = f"""
<div style="
    background-color: {bg_color};
    border-left: 4px solid {color};
    padding: 1rem;
    border-radius: 4px;
    margin: 1rem 0;
    color: {config.BRAND_COLORS['text']};
">
    <div style="display: flex; align-items: start; gap: 0.75rem;">
        <span style="font-size: 1.25rem;">{icon}</span>
        <div style="flex: 1; font-size: 0.95rem; line-height: 1.5;">
            {message}
        </div>
    </div>
</div>
"""
    st.markdown(html, unsafe_allow_html=True)
