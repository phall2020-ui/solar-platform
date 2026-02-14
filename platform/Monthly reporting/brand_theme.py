"""
AMPYR Brand Design System Module

This module provides brand styling and theming for the Solar Asset Data Manager
application. It includes:

- Brand color palette definition
- CSS injection for consistent styling across the application
- Plotly theme registration for charts and visualizations
- Helper functions for branded UI components

The design system ensures visual consistency with AMPYR branding while
maintaining clean, minimal styling that integrates well with Streamlit.
"""

import streamlit as st
import plotly.graph_objects as go
import plotly.io as pio
import pandas as pd
from typing import List, Optional, Union


# ═══════════════════════════════════════════════════════════════════════════════
# 1. BRAND COLOUR PALETTE
# ═══════════════════════════════════════════════════════════════════════════════

BRAND_COLOURS = {
    # Primary - AMPYR Dark Teal
    "primary": "#1B4D5C",
    "primary_dark": "#153D4A",
    "primary_light": "#2A6B7C",
    # Secondary - Teal
    "secondary": "#2D8B9E",
    "secondary_light": "#3BA3B8",
    # Accent - Gold
    "accent": "#D4A84B",
    # Status
    "positive": "#2D8B5F",
    "negative": "#C94A4A",
    "warning": "#D4A84B",
    # Neutral
    "background": "#F5F7F8",
    "surface": "#FFFFFF",
    "surface_alt": "#EEF2F4",
    "border": "#DCE4E8",
    "border_dark": "#B8C8CE",
    # Text
    "text": "#1B4D5C",
    "text_secondary": "#5A7A85",
    "muted_text": "#8DA4AD",
    "text_inverse": "#FFFFFF",
}

CHART_COLORWAY = [
    BRAND_COLOURS["primary"],
    BRAND_COLOURS["secondary"],
    BRAND_COLOURS["accent"],
    BRAND_COLOURS["positive"],
    "#7B68A6",
    "#5DADE2",
    "#48C9B0",
    BRAND_COLOURS["negative"],
]


# ═══════════════════════════════════════════════════════════════════════════════
# 2. CSS INJECTION - MINIMAL & SAFE
# ═══════════════════════════════════════════════════════════════════════════════


def inject_brand_css():
    """Inject minimal CSS that won't break Streamlit."""

    css = f"""
    <style>
        /* Background */
        .stApp {{
            background-color: {BRAND_COLOURS["background"]};
        }}

        /* Sidebar */
        section[data-testid="stSidebar"] {{
            background-color: {BRAND_COLOURS["primary_dark"]};
        }}

        section[data-testid="stSidebar"] h1,
        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3,
        section[data-testid="stSidebar"] h4,
        section[data-testid="stSidebar"] p,
        section[data-testid="stSidebar"] label,
        section[data-testid="stSidebar"] span,
        section[data-testid="stSidebar"] div {{
            color: {BRAND_COLOURS["text_inverse"]} !important;
        }}

        section[data-testid="stSidebar"] input,
        section[data-testid="stSidebar"] select {{
            color: {BRAND_COLOURS["text"]} !important;
            background-color: rgba(255, 255, 255, 0.9) !important;
        }}

        section[data-testid="stSidebar"] button {{
            color: {BRAND_COLOURS["text_inverse"]} !important;
            background-color: {BRAND_COLOURS["secondary"]} !important;
            border: 1px solid rgba(255, 255, 255, 0.3) !important;
        }}

        section[data-testid="stSidebar"] button:hover {{
            background-color: {BRAND_COLOURS["secondary_light"]} !important;
        }}

        section[data-testid="stSidebar"] .stSelectbox > div > div {{
            background-color: rgba(255, 255, 255, 0.15) !important;
            border-color: rgba(255, 255, 255, 0.3) !important;
            color: {BRAND_COLOURS["text_inverse"]} !important;
        }}

        /* Headers in main area */
        .main h1 {{
            color: {BRAND_COLOURS["primary"]} !important;
        }}

        .main h2, .main h3 {{
            color: {BRAND_COLOURS["primary"]} !important;
        }}

        /* Tabs */
        button[data-baseweb="tab"] {{
            color: {BRAND_COLOURS["muted_text"]} !important;
        }}

        button[data-baseweb="tab"][aria-selected="true"] {{
            color: {BRAND_COLOURS["secondary"]} !important;
        }}

        /* Metrics */
        [data-testid="stMetric"] {{
            background-color: {BRAND_COLOURS["surface"]};
            border: 1px solid {BRAND_COLOURS["border"]};
            border-radius: 8px;
            padding: 1rem;
        }}

        [data-testid="stMetricValue"] {{
            color: {BRAND_COLOURS["primary"]} !important;
        }}

        /* DataFrames */
        [data-testid="stDataFrame"] {{
            border: 1px solid {BRAND_COLOURS["border"]};
            border-radius: 8px;
        }}

        /* Charts */
        [data-testid="stPlotlyChart"] {{
            background-color: {BRAND_COLOURS["surface"]};
            border: 1px solid {BRAND_COLOURS["border"]};
            border-radius: 8px;
            padding: 0.5rem;
        }}

        /* Buttons */
        .stButton > button {{
            border-radius: 6px;
        }}

        /* File uploader */
        [data-testid="stFileUploader"] {{
            border: 2px dashed {BRAND_COLOURS["border"]};
            border-radius: 8px;
            padding: 1rem;
        }}

        /* Alerts */
        .stAlert {{
            border-radius: 8px;
        }}

    </style>
    """

    st.markdown(css, unsafe_allow_html=True)


def show_header():
    """Display the AMPYR branded header."""

    st.markdown(
        f"""
        <div style="
            display: flex;
            align-items: center;
            gap: 12px;
            padding-bottom: 1rem;
            margin-bottom: 0.5rem;
            border-bottom: 1px solid {BRAND_COLOURS["border"]};
        ">
            <div style="display: flex; align-items: center; gap: 8px;">
                <svg width="36" height="36" viewBox="0 0 100 100">
                    <polygon points="50,10 90,90 10,90" fill="{BRAND_COLOURS["primary"]}" />
                    <polygon points="50,28 75,78 25,78" fill="{BRAND_COLOURS["secondary"]}" />
                </svg>
                <div>
                    <div style="font-size: 1.1rem; font-weight: 700; color: {BRAND_COLOURS["primary"]}; letter-spacing: -0.02em;">
                        AMPYR
                    </div>
                    <div style="font-size: 0.6rem; color: {BRAND_COLOURS["muted_text"]}; text-transform: uppercase; letter-spacing: 0.08em;">
                        DISTRIBUTED ENERGY
                    </div>
                </div>
            </div>
            <div style="color: {BRAND_COLOURS["muted_text"]}; font-size: 0.85rem; padding-left: 12px; border-left: 1px solid {BRAND_COLOURS["border"]};">
                with local expertise
            </div>
        </div>
    """,
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 3. PLOTLY THEME
# ═══════════════════════════════════════════════════════════════════════════════


def register_plotly_theme():
    """Register AMPYR Plotly template."""

    ampyr_template = {
        "layout": {
            "colorway": CHART_COLORWAY,
            "paper_bgcolor": BRAND_COLOURS["surface"],
            "plot_bgcolor": BRAND_COLOURS["surface"],
            "font": {
                "family": "-apple-system, BlinkMacSystemFont, sans-serif",
                "size": 12,
                "color": BRAND_COLOURS["text"],
            },
            "title": {
                "font": {"size": 16, "color": BRAND_COLOURS["primary"]},
            },
            "xaxis": {
                "showgrid": True,
                "gridcolor": BRAND_COLOURS["border"],
                "linecolor": BRAND_COLOURS["border_dark"],
                "tickfont": {"color": BRAND_COLOURS["text_secondary"]},
            },
            "yaxis": {
                "showgrid": True,
                "gridcolor": BRAND_COLOURS["border"],
                "linecolor": BRAND_COLOURS["border_dark"],
                "tickfont": {"color": BRAND_COLOURS["text_secondary"]},
            },
            "legend": {
                "bgcolor": "rgba(255,255,255,0.9)",
                "bordercolor": BRAND_COLOURS["border"],
                "borderwidth": 1,
            },
            "hoverlabel": {
                "bgcolor": BRAND_COLOURS["primary"],
                "font": {"color": BRAND_COLOURS["text_inverse"]},
            },
        },
    }

    pio.templates["ampyr_brand"] = ampyr_template
    pio.templates.default = "ampyr_brand"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. WATERFALL CHART
# ═══════════════════════════════════════════════════════════════════════════════


def plot_waterfall_branded(
    budget: float,
    weather_var: float,
    wab: float,
    efficiency_loss: float,
    actual: float,
    title: str = "Solar Loss Waterfall",
) -> go.Figure:
    """Create branded waterfall chart."""

    labels = ["Budget", "Weather Δ", "WAB", "Efficiency Loss", "Actual"]
    measures = ["absolute", "relative", "total", "relative", "total"]
    values = [budget, weather_var, wab, -efficiency_loss, actual]

    fig = go.Figure(
        go.Waterfall(
            orientation="v",
            measure=measures,
            x=labels,
            y=values,
            text=[f"{v:,.0f}" for v in values],
            textposition="outside",
            connector={"line": {"color": BRAND_COLOURS["border_dark"], "width": 1, "dash": "dot"}},
            increasing={"marker": {"color": BRAND_COLOURS["positive"]}},
            decreasing={"marker": {"color": BRAND_COLOURS["negative"]}},
            totals={"marker": {"color": BRAND_COLOURS["primary"]}},
        )
    )

    fig.update_layout(
        template="ampyr_brand",
        title=title,
        yaxis_title="Energy (kWh)",
        showlegend=False,
        height=450,
    )

    return fig


# ═══════════════════════════════════════════════════════════════════════════════
# 5. CHART HELPERS
# ═══════════════════════════════════════════════════════════════════════════════


def get_variance_color(value: float, inverse: bool = False) -> str:
    """Get green/red color based on value."""
    if inverse:
        return BRAND_COLOURS["positive"] if value <= 0 else BRAND_COLOURS["negative"]
    return BRAND_COLOURS["positive"] if value >= 0 else BRAND_COLOURS["negative"]


def create_branded_bar_chart(
    df: pd.DataFrame,
    x: str,
    y: Union[str, List[str]],
    title: str = "",
    barmode: str = "group",
    height: int = 400,
    variance_coloring: bool = False,
) -> go.Figure:
    """Create branded bar chart."""

    if isinstance(y, str):
        y = [y]

    fig = go.Figure()

    for i, y_col in enumerate(y):
        if variance_coloring:
            colors = [get_variance_color(v) for v in df[y_col]]
        else:
            colors = CHART_COLORWAY[i % len(CHART_COLORWAY)]

        fig.add_trace(
            go.Bar(
                name=y_col,
                x=df[x],
                y=df[y_col],
                marker_color=colors,
            )
        )

    fig.update_layout(
        template="ampyr_brand",
        title=title,
        barmode=barmode,
        height=height,
    )

    return fig


def create_branded_line_chart(
    df: pd.DataFrame,
    x: str,
    y: Union[str, List[str]],
    title: str = "",
    height: int = 400,
    add_zero_line: bool = False,
) -> go.Figure:
    """Create branded line chart."""

    if isinstance(y, str):
        y = [y]

    fig = go.Figure()

    for i, y_col in enumerate(y):
        fig.add_trace(
            go.Scatter(
                name=y_col,
                x=df[x],
                y=df[y_col],
                mode="lines+markers",
                line={"color": CHART_COLORWAY[i % len(CHART_COLORWAY)], "width": 2},
                marker={"size": 8},
            )
        )

    if add_zero_line:
        fig.add_hline(y=0, line_dash="dash", line_color=BRAND_COLOURS["muted_text"])

    fig.update_layout(
        template="ampyr_brand",
        title=title,
        height=height,
    )

    return fig


# ═══════════════════════════════════════════════════════════════════════════════
# 6. INITIALIZATION
# ═══════════════════════════════════════════════════════════════════════════════


def initialize_brand_theme(show_header: bool = True):
    """
    Initialize the AMPYR brand theme.
    Call after st.set_page_config().
    """
    inject_brand_css()
    register_plotly_theme()

    if show_header:
        show_header_fn()


def show_header_fn():
    """Alias for show_header."""
    show_header()
