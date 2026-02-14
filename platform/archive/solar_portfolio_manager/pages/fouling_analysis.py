"""
Fouling (Soiling) Analysis page for Solar Portfolio Manager.
Analyzes performance degradation due to soiling on solar panels.
"""
import reflex as rx
from solar_portfolio_manager.state import AppState
from solar_portfolio_manager.components.layout import section_header, divider
from solar_portfolio_manager.components.kpi_card import kpi_card
from solar_portfolio_manager.components.alert import info_alert, warning_alert, success_alert, error_alert
from solar_portfolio_manager.styles import heading_style, COLORS, card_style


def fouling_analysis_page() -> rx.Component:
    """The Fouling Analysis page for soiling detection."""
    return rx.vstack(
        rx.heading("🧹 Fouling Analysis", style=heading_style, size="8"),
        rx.text(
            "Analyze panel soiling by comparing current performance to clean baseline periods.",
            color=COLORS["text_secondary"]
        ),
        
        divider(),
        
        # Configuration Section
        section_header("Analysis Configuration", "Set up the fouling analysis parameters."),
        
        rx.box(
            rx.vstack(
                rx.grid(
                    # Column 1: Plant Selection
                    rx.vstack(
                        rx.text("Plant Selection", font_weight="600"),
                        rx.select(
                            AppState.registered_plant_aliases,
                            placeholder="Select a plant...",
                            value=AppState.fouling_plant_alias,
                            on_change=AppState.set_fouling_plant_alias,
                        ),
                        rx.text("Analysis Period", font_weight="600", margin_top="1rem"),
                        rx.cond(
                            AppState.data_min_date != "",
                            rx.text(
                                rx.text.span("Data available: ", color=COLORS["text_secondary"]),
                                rx.text.span(AppState.data_min_date, font_weight="500"),
                                rx.text.span(" to ", color=COLORS["text_secondary"]),
                                rx.text.span(AppState.data_max_date, font_weight="500"),
                                font_size="0.85rem",
                                margin_bottom="0.5rem",
                            ),
                            rx.fragment(),
                        ),
                        rx.hstack(
                            rx.input(
                                type="date",
                                value=AppState.fouling_start_date,
                                on_change=AppState.set_fouling_start_date,
                                min=AppState.data_min_date,
                                max=AppState.data_max_date,
                            ),
                            rx.text("to"),
                            rx.input(
                                type="date",
                                value=AppState.fouling_end_date,
                                on_change=AppState.set_fouling_end_date,
                                min=AppState.data_min_date,
                                max=AppState.data_max_date,
                            ),
                            spacing="2",
                            align="center",
                        ),
                        spacing="2",
                        align_items="start",
                    ),
                    # Column 2: Parameters
                    rx.vstack(
                        rx.text("DC Size (kW)", font_weight="600"),
                        rx.input(
                            type="number",
                            placeholder="1000",
                            default_value="1000",
                            on_change=AppState.set_fouling_dc_size_str,
                        ),
                        rx.text("Auto-Clean Period (days)", font_weight="600", margin_top="1rem"),
                        rx.text(
                            "3 days (default)",
                            color=COLORS["text_secondary"],
                            font_size="0.85rem",
                        ),
                        spacing="2",
                        align_items="start",
                    ),
                    columns=rx.breakpoints(initial="1", md="2"),
                    spacing="6",
                    width="100%",
                ),
                rx.divider(margin_y="1rem"),
                rx.hstack(
                    rx.button(
                        rx.cond(
                            AppState.fouling_loading,
                            rx.spinner(size="1"),
                            rx.icon("play"),
                        ),
                        "Run Fouling Analysis",
                        color_scheme="teal",
                        size="3",
                        on_click=AppState.run_fouling_analysis,
                        disabled=AppState.fouling_loading,
                    ),
                    spacing="3",
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
            AppState.fouling_error != "",
            error_alert(AppState.fouling_error),
            rx.fragment(),
        ),
        
        # Results Section
        section_header("Analysis Results", "Results will appear here after running the analysis."),
        
        rx.cond(
            AppState.fouling_result.contains("fouling_index"),
            # Show results
            rx.vstack(
                success_alert("Analysis complete!"),
                rx.hstack(
                    kpi_card(
                        title="Median Fouling Index",
                        value=AppState.fouling_result["fouling_index"].to_string(),
                        icon="📊",
                    ),
                    kpi_card(
                        title="Fouling Level",
                        value=AppState.fouling_result["fouling_level"].to_string(),
                        icon="🧹",
                    ),
                    kpi_card(
                        title="Data Points",
                        value=AppState.fouling_result["data_points"].to_string(),
                        icon="📈",
                    ),
                    spacing="4",
                    width="100%",
                ),
                spacing="4",
                width="100%",
            ),
            # Show placeholder
            rx.box(
                rx.vstack(
                    info_alert("Configure the parameters above and click 'Run Fouling Analysis' to see results."),
                    rx.box(
                        rx.hstack(
                            rx.vstack(
                                rx.text("📊", font_size="2rem"),
                                rx.text("Fouling Index", font_weight="600"),
                                rx.text("Result placeholder", color=COLORS["text_secondary"], font_size="0.85rem"),
                                align="center",
                            ),
                            rx.vstack(
                                rx.text("🧹", font_size="2rem"),
                                rx.text("Fouling Level", font_weight="600"),
                                rx.text("Result placeholder", color=COLORS["text_secondary"], font_size="0.85rem"),
                                align="center",
                            ),
                            rx.vstack(
                                rx.text("📈", font_size="2rem"),
                                rx.text("Data Points", font_weight="600"),
                                rx.text("Result placeholder", color=COLORS["text_secondary"], font_size="0.85rem"),
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
