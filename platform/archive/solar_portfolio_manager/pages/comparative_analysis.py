"""
Comparative Analysis page for Solar Portfolio Manager.
Compare performance across multiple plants or time periods.
"""
import reflex as rx
from solar_portfolio_manager.state import AppState
from solar_portfolio_manager.components.layout import section_header, divider
from solar_portfolio_manager.components.alert import info_alert
from solar_portfolio_manager.styles import heading_style, COLORS, card_style


def comparative_analysis_page() -> rx.Component:
    """The Comparative Analysis page for cross-plant comparison."""
    return rx.vstack(
        rx.heading("📊 Comparative Analysis", style=heading_style, size="8"),
        rx.text(
            "Compare performance across multiple plants or different time periods.",
            color=COLORS["text_secondary"]
        ),
        
        divider(),
        
        # Comparison Configuration
        section_header("Comparison Setup", "Select plants and metrics to compare."),
        
        rx.box(
            rx.vstack(
                rx.text("Comparison Type", font_weight="600"),
                rx.radio_group(
                    items=["Compare Plants", "Compare Time Periods"],
                    default_value="Compare Plants",
                ),
                
                rx.text("Select Plants", font_weight="600", margin_top="1rem"),
                rx.select(
                    AppState.registered_plant_aliases,
                    placeholder="Select plants to compare...",
                ),
                
                rx.text("Metrics", font_weight="600", margin_top="1rem"),
                rx.hstack(
                    rx.checkbox("Performance Ratio", default_checked=True),
                    rx.checkbox("Energy Yield", default_checked=True),
                    rx.checkbox("Availability"),
                    rx.checkbox("Specific Yield"),
                    spacing="4",
                    flex_wrap="wrap",
                ),
                
                rx.button(
                    rx.icon("bar-chart-2"),
                    "Run Comparison",
                    color_scheme="teal",
                    margin_top="1rem",
                ),
                spacing="3",
                width="100%",
            ),
            style=card_style,
            width="100%",
        ),
        
        divider(),
        
        # Results
        section_header("Comparison Results", "Charts and tables will appear here."),
        
        info_alert("Select plants and metrics, then click 'Run Comparison' to see results."),
        
        spacing="6",
        width="100%",
        align_items="stretch",
    )
