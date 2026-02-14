import pandas as pd
import plotly.express as px

from services.analysis.chart_templates import apply_analysis_template
from unified_config import config


def create_shading_chart(merged_df, site_name):
    """Create shading analysis scatter plot."""
    if merged_df.empty or 'power_ac_baseline' not in merged_df.columns:
        return None
    
    fig = px.scatter(
        merged_df, 
        x='power_ac_baseline', 
        y='power_ac_compare', 
        color='shading_ratio', 
        title=f"Shading Analysis ({site_name})",
        color_continuous_scale=px.colors.diverging.RdYlGn,
        labels={
            'power_ac_baseline': 'Summer Power (kW) (Baseline)',
            'power_ac_compare': 'Winter Power (kW) (Comparison)',
            'shading_ratio': 'Shading Ratio'
        }
    )
    # Add 1:1 line
    max_val = max(merged_df['power_ac_baseline'].max(), merged_df['power_ac_compare'].max())
    fig.add_shape(type="line",
        x0=0, y0=0, x1=max_val, y1=max_val,
        line=dict(color="Gray", dash="dash")
    )
    return apply_analysis_template(fig)

def create_soiling_chart(daily_df, site_name):
    """Create soiling loss line chart."""
    cols_to_plot = [c for c in daily_df.columns if 'loss' in c.lower()]
    if not cols_to_plot:
        return None
        
    fig = px.line(
        daily_df, 
        y=cols_to_plot, 
        title=f"Soiling Loss: {site_name}",
        labels={'value': 'Loss (kWh)', 'index': 'Date'},
        color_discrete_sequence=[config.BRAND_COLORS['negative']]
    )
    return apply_analysis_template(fig)

def create_heatmap_chart(pivot_df, metric_name):
    """Create technical loss heatmap."""
    # Force a symmetric range so 0 always maps to the midpoint (white)
    min_val = pivot_df.min().min() if not pivot_df.empty else 0
    max_val = pivot_df.max().max() if not pivot_df.empty else 0
    abs_max = max(abs(min_val), abs(max_val))
    if pd.isna(abs_max) or abs_max == 0:
        abs_max = 1

    # Light neutral green around zero for better readability
    zero_tint = "#e3f5eb"
    diverging_scale = [
        (0.0, config.BRAND_COLORS["positive"]),  # Darker green at min
        (0.45, zero_tint),
        (0.55, zero_tint),                       # Slightly light green at 0 kWh
        (1.0, config.BRAND_COLORS["negative"]),  # Red for high loss
    ]

    fig = px.imshow(
        pivot_df,
        text_auto=".0f",
        aspect="auto",
        color_continuous_scale=diverging_scale,
        title=f"{metric_name} Heatmap (kWh)"
    )
    fig.update_coloraxes(cmin=-abs_max, cmax=abs_max, cmid=0)
    fig.update_layout(xaxis_title="Month", yaxis_title="Site")
    return apply_analysis_template(fig)
