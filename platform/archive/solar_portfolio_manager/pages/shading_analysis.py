"""
Shading Analysis page for Solar Portfolio Manager.
Analyzes shading losses by comparing summer and winter performance.
"""
import reflex as rx
from solar_portfolio_manager.state import AppState
from solar_portfolio_manager.components.layout import section_header, divider
from solar_portfolio_manager.components.kpi_card import kpi_card
from solar_portfolio_manager.components.alert import info_alert, error_alert, success_alert
from solar_portfolio_manager.styles import heading_style, COLORS, card_style


def shading_analysis_page() -> rx.Component:
    """The Shading Analysis page for detecting shading losses."""
    return rx.vstack(
        rx.heading("🌑 Shading Analysis", style=heading_style, size="8"),
        rx.text(
            "Compare summer baseline performance to winter periods to detect shading losses.",
            color=COLORS["text_secondary"]
        ),
        
        divider(),
        
        # Configuration Section
        section_header("Analysis Configuration", "Select baseline and comparison periods."),
        
        rx.box(
            rx.vstack(
                rx.grid(
                    # Column 1: Plant and Baseline
                    rx.vstack(
                        rx.text("Plant Selection", font_weight="600"),
                        rx.select(
                            AppState.registered_plant_aliases,
                            placeholder="Select a plant...",
                            value=AppState.shading_plant_alias,
                            on_change=AppState.set_shading_plant_alias,
                        ),
                        rx.text("Baseline Period (Summer)", font_weight="600", margin_top="1rem"),
                        rx.text("Select months with minimal shading", color=COLORS["text_secondary"], font_size="0.85rem"),
                        rx.hstack(
                            rx.input(
                                type="month",
                                value=AppState.shading_baseline_start,
                                on_change=AppState.set_shading_baseline_start,
                            ),
                            rx.text("to"),
                            rx.input(
                                type="month",
                                value=AppState.shading_baseline_end,
                                on_change=AppState.set_shading_baseline_end,
                            ),
                            spacing="2",
                            align="center",
                        ),
                        spacing="2",
                        align_items="start",
                    ),
                    # Column 2: Comparison Period
                    rx.vstack(
                        rx.text("Comparison Period (Winter)", font_weight="600"),
                        rx.text("Select months to analyze for shading", color=COLORS["text_secondary"], font_size="0.85rem"),
                        rx.hstack(
                            rx.input(
                                type="month",
                                value=AppState.shading_compare_start,
                                on_change=AppState.set_shading_compare_start,
                            ),
                            rx.text("to"),
                            rx.input(
                                type="month",
                                value=AppState.shading_compare_end,
                                on_change=AppState.set_shading_compare_end,
                            ),
                            spacing="2",
                            align="center",
                        ),
                        spacing="2",
                        align_items="start",
                    ),
                    columns=rx.breakpoints(initial="1", md="2"),
                    spacing="6",
                    width="100%",
                ),
                rx.divider(margin_y="1rem"),
                rx.button(
                    rx.cond(
                        AppState.shading_loading,
                        rx.spinner(size="1"),
                        rx.icon("play"),
                    ),
                    "Run Shading Analysis",
                    color_scheme="teal",
                    size="3",
                    on_click=AppState.run_shading_analysis,
                    disabled=AppState.shading_loading,
                ),
                spacing="4",
                width="100%",
            ),
            style=card_style,
            width="100%",
        ),
        
        divider(),
        
        # Error Display
        rx.cond(
            AppState.shading_error != "",
            error_alert(AppState.shading_error),
            rx.fragment(),
        ),
        
        # Results Section
        section_header("Analysis Results", "Shading patterns will be displayed here."),
        
        rx.cond(
            AppState.shading_result.contains("data_points"),
            rx.vstack(
                success_alert("Analysis complete!"),
                rx.hstack(
                    kpi_card(
                        title="Data Points",
                        value=AppState.shading_result["data_points"].to_string(),
                        icon="📊",
                    ),
                    kpi_card(
                        title="Inverters Analyzed",
                        value=AppState.shading_result["inverters_analyzed"].to_string(),
                        icon="🔌",
                    ),
                    spacing="4",
                    width="100%",
                ),
                spacing="4",
                width="100%",
            ),
            rx.box(
                rx.vstack(
                    info_alert("Configure the parameters above and click 'Run Shading Analysis' to see results."),
                    rx.box(
                        rx.hstack(
                            rx.vstack(
                                rx.text("📈", font_size="2rem"),
                                rx.text("Time-of-Day Heatmap", font_weight="600"),
                                rx.text("Chart placeholder", color=COLORS["text_secondary"], font_size="0.85rem"),
                                align="center",
                            ),
                            rx.vstack(
                                rx.text("🔄", font_size="2rem"),
                                rx.text("Inverter Comparison", font_weight="600"),
                                rx.text("Table placeholder", color=COLORS["text_secondary"], font_size="0.85rem"),
                                align="center",
                            ),
                            spacing="6",
                            justify="center",
                            width="100%",
                        ),
                        padding="2rem",
                        border=f"2px dashed {COLORS['border']}",
                        border_radius="12px",
                        width="100%",
                    ),
                    spacing="4",
                    width="100%",
                ),
                width="100%",
            ),
        ),
        
        spacing="6",
        width="100%",
        align_items="stretch",
    )
