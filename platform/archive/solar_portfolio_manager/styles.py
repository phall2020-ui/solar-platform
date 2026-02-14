"""
AMPYR brand theming and styling for Reflex.
Replaces styles/theme.py Streamlit CSS injection with Reflex-compatible styles.
"""

# Import brand colors from unified config
try:
    from unified_config import config
    # We maintain the primary teal but adjust surrounding colors for light mode
    COLORS = {
        'primary': config.BRAND_COLORS.get('primary', '#5FBFA0'),
        'secondary': '#334155',      # Slate 700
        'accent': '#8FE0C5',         # Mint accent
        'background': '#FFFFFF',     # Pure white
        'surface': '#F8FAFC',        # Light slate surface
        'border': '#E2E8F0',         # Light slate border
        'text': '#0F172A',           # Slate 900
        'text_secondary': '#64748B', # Slate 500
        'positive': '#10B981',       # Emerald 500
        'negative': '#EF4444',       # Red 500
        'warning': '#F59E0B',        # Amber 500
    }
    CHART_COLORS = config.CHART_COLORS
except ImportError:
    # Fallback colors if config not available
    COLORS = {
        'primary': '#5FBFA0',
        'secondary': '#334155',
        'accent': '#8FE0C5',
        'background': '#FFFFFF',
        'surface': '#F8FAFC',
        'border': '#E2E8F0',
        'text': '#0F172A',
        'text_secondary': '#64748B',
        'positive': '#10B981',
        'negative': '#EF4444',
        'warning': '#F59E0B',
    }
    CHART_COLORS = [
        '#5FBFA0', '#8E44AD', '#3498DB', '#F59E0B', 
        '#EF4444', '#10B981', '#6366F1', '#EC4899'
    ]


# ===== Common Style Dictionaries =====

# KPI Card styles
card_style = {
    "background_color": COLORS["background"],
    "border": f"1px solid {COLORS['border']}",
    "border_radius": "12px",
    "padding": "1.25rem",
    "margin": "0.5rem 0",
    "box_shadow": "0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1)",
    "transition": "transform 0.2s ease, box-shadow 0.2s ease",
}

card_positive_style = {
    **card_style,
    "border_top": f"3px solid {COLORS['positive']}",
}

card_negative_style = {
    **card_style,
    "border_top": f"3px solid {COLORS['negative']}",
}

card_neutral_style = {
    **card_style,
    "border_top": f"3px solid {COLORS['primary']}",
}

# Sidebar styles
sidebar_style = {
    "background_color": "#F8FAFC",
    "border_right": f"1px solid {COLORS['border']}",
    "height": "100vh",
    "width": "260px",
    "position": "fixed",
    "left": "0",
    "top": "0",
    "padding": "1.5rem 1rem",
    "overflow_y": "auto",
    "z_index": "100",
}

# Main content area
main_content_style = {
    "margin_left": "260px",
    "padding": "2rem 3rem",
    "width": "calc(100% - 260px)",
    "min_height": "100vh",
    "background_color": COLORS["background"],
}

# Typography styles
heading_style = {
    "font_family": "'Inter', 'Segoe UI', sans-serif",
    "color": COLORS["text"],
    "font_weight": "700",
}

text_secondary_style = {
    "color": COLORS["text_secondary"],
    "font_size": "0.95rem",
}

# Button styles
button_primary_style = {
    "background_color": COLORS["primary"],
    "color": "white",
    "border_radius": "8px",
    "padding": "0.6rem 1.25rem",
    "font_weight": "600",
    "cursor": "pointer",
    "transition": "opacity 0.2s ease",
}

button_secondary_style = {
    "background_color": COLORS["background"],
    "color": COLORS["text"],
    "border_radius": "8px",
    "border": f"1px solid {COLORS['border']}",
    "padding": "0.6rem 1.25rem",
    "cursor": "pointer",
}

# Alert styles
alert_success_style = {
    "background_color": "#F0FDF4",
    "border": "1px solid #BBF7D0",
    "color": "#15803D",
    "padding": "0.75rem 1rem",
    "border_radius": "8px",
    "margin": "1rem 0",
}

alert_error_style = {
    "background_color": "#FEF2F2",
    "border": "1px solid #FECACA",
    "color": "#B91C1C",
    "padding": "0.75rem 1rem",
    "border_radius": "8px",
    "margin": "1rem 0",
}

alert_warning_style = {
    "background_color": "#FFFBEB",
    "border": "1px solid #FEF3C7",
    "color": "#B45309",
    "padding": "0.75rem 1rem",
    "border_radius": "8px",
    "margin": "1rem 0",
}

alert_info_style = {
    "background_color": "#F0F9FF",
    "border": "1px solid #BAE6FD",
    "color": "#0369A1",
    "padding": "0.75rem 1rem",
    "border_radius": "8px",
    "margin": "1rem 0",
}

# Divider style
divider_style = {
    "margin": "1.5rem 0",
    "border": "0",
    "border_top": f"1px solid {COLORS['border']}",
}

# Navigation button styles
nav_button_base_style = {
    "width": "100%",
    "text_align": "left",
    "padding": "0.6rem 0.75rem",
    "border_radius": "8px",
    "cursor": "pointer",
    "font_size": "0.9rem",
    "transition": "all 0.15s ease",
}

nav_button_active_style = {
    **nav_button_base_style,
    "background_color": f"{COLORS['primary']}15", # Very light primary
    "color": COLORS["primary"],
    "font_weight": "600",
}

nav_button_inactive_style = {
    **nav_button_base_style,
    "background_color": "transparent",
    "color": COLORS["text_secondary"],
    "border": "none",
}

# Logo/branding styles
logo_glyph_style = {
    "width": "32px",
    "height": "32px",
    "border_radius": "8px",
    "background_color": COLORS["primary"],
}

logo_wordmark_style = {
    "font_weight": "800",
    "font_size": "1.2rem",
    "letter_spacing": "-0.02em",
    "color": COLORS["text"],
}


# ===== Global Stylesheet =====

GLOBAL_STYLES = f"""
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

:root {{
    --ampyr-bg: {COLORS['background']};
    --ampyr-surface: {COLORS['surface']};
    --ampyr-border: {COLORS['border']};
    --ampyr-primary: {COLORS['primary']};
    --ampyr-text: {COLORS['text']};
    --ampyr-text-secondary: {COLORS['text_secondary']};
}}

* {{
    box-sizing: border-box;
}}

body {{
    background-color: var(--ampyr-bg);
    color: var(--ampyr-text);
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    margin: 0;
    padding: 0;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
}}

h1, h2, h3, h4 {{
    color: var(--ampyr-text);
    margin-top: 0;
}}

/* Custom scrollbar */
::-webkit-scrollbar {{
    width: 6px;
}}
::-webkit-scrollbar-track {{
    background: transparent;
}}
::-webkit-scrollbar-thumb {{
    background: #CBD5E1;
    border_radius: 10px;
}}
::-webkit-scrollbar-thumb:hover {{
    background: #94A3B8;
}}
"""
