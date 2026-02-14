"""Standard Plotly chart templates for analysis pages."""

from __future__ import annotations

import plotly.graph_objects as go


ANALYSIS_COLORS = {
    "primary": "#00838f",
    "positive": "#2e7d32",
    "negative": "#c62828",
    "neutral": "#546e7a",
    "background": "#ffffff",
    "grid": "#eceff1",
}


def apply_analysis_template(fig: go.Figure, title: str = "") -> go.Figure:
    """Apply a consistent visual style across analysis charts."""
    fig.update_layout(
        title=title,
        template="plotly_white",
        font={"family": "Source Sans Pro, Arial, sans-serif", "size": 13},
        paper_bgcolor=ANALYSIS_COLORS["background"],
        plot_bgcolor=ANALYSIS_COLORS["background"],
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
        margin={"l": 40, "r": 20, "t": 60, "b": 40},
    )
    fig.update_xaxes(showgrid=True, gridcolor=ANALYSIS_COLORS["grid"])
    fig.update_yaxes(showgrid=True, gridcolor=ANALYSIS_COLORS["grid"])
    return fig
