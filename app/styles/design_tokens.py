"""
Design token system for the AMPYR Solar Portfolio Manager.

SINGLE SOURCE OF TRUTH for all visual styling.
Import this — never hardcode colors, font sizes, or spacing.

DESIGN NOTES FOR EXTRACTION:
- When moving to React, these become CSS custom properties / design tokens
- Same values, different format (Python dict → CSS vars / Tailwind config)
"""

# ── Color Palette ────────────────────────────────────────────────────

# Primary brand colors
AMPYR_TEAL = "#1B4D5C"         # Primary teal (from official brand)
AMPYR_TEAL_LIGHT = "#5FBFA0"   # Light teal (secondary/accent)
AMPYR_GREEN = "#6B8E23"        # Olive green (charts)

# Semantic colors
STATUS_COLORS = {
    "excellent": "#2ECC71",     # Green — PR > 85%
    "good": "#5FBFA0",          # Teal — PR 70–85%
    "warning": "#F39C12",       # Amber — PR 50–70%
    "critical": "#E74C3C",      # Red — PR < 50%
    "offline": "#95A5A6",       # Gray — no data
    "unknown": "#BDC3C7",       # Light gray — cannot determine
}

# Chart palette (12 colors for multi-series)
CHART_COLORS = [
    "#1B4D5C",  # AMPYR teal
    "#5FBFA0",  # Light teal
    "#E74C3C",  # Red
    "#F39C12",  # Amber
    "#3498DB",  # Blue
    "#2ECC71",  # Green
    "#9B59B6",  # Purple
    "#E67E22",  # Orange
    "#1ABC9C",  # Turquoise
    "#34495E",  # Dark slate
    "#E91E63",  # Pink
    "#00BCD4",  # Cyan
]

# Background colors
BG_COLORS = {
    "page": "#FFFFFF",
    "card": "#F8F9FA",
    "sidebar": "#F0F2F6",
    "header": AMPYR_TEAL,
    "dark_page": "#0E1117",
    "dark_card": "#1E1E2E",
    "dark_sidebar": "#161625",
}

# ── Typography ──────────────────────────────────────────────────────

FONT_FAMILY = "'Inter', 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif"

FONT_SIZES = {
    "xs": "0.75rem",    # 12px — labels, captions
    "sm": "0.875rem",   # 14px — secondary text
    "base": "1rem",     # 16px — body text
    "lg": "1.125rem",   # 18px — subheadings
    "xl": "1.25rem",    # 20px — section titles
    "2xl": "1.5rem",    # 24px — page titles
    "3xl": "2rem",      # 32px — dashboard numbers
    "4xl": "2.5rem",    # 40px — hero KPIs
}

# ── Spacing ─────────────────────────────────────────────────────────

SPACING = {
    "xs": "0.25rem",    # 4px
    "sm": "0.5rem",     # 8px
    "md": "1rem",       # 16px
    "lg": "1.5rem",     # 24px
    "xl": "2rem",       # 32px
    "2xl": "3rem",      # 48px
}

# ── Plotly Chart Theme ──────────────────────────────────────────────

PLOTLY_TEMPLATE = {
    "layout": {
        "font": {"family": FONT_FAMILY, "color": "#2C3E50"},
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "colorway": CHART_COLORS,
        "title": {"font": {"size": 16, "color": AMPYR_TEAL}},
        "xaxis": {
            "gridcolor": "#E8E8E8",
            "linecolor": "#E8E8E8",
            "tickfont": {"size": 12},
        },
        "yaxis": {
            "gridcolor": "#E8E8E8",
            "linecolor": "#E8E8E8",
            "tickfont": {"size": 12},
        },
        "legend": {
            "bgcolor": "rgba(255,255,255,0.8)",
            "bordercolor": "#E8E8E8",
            "borderwidth": 1,
        },
        "margin": {"l": 60, "r": 20, "t": 40, "b": 40},
    },
}
