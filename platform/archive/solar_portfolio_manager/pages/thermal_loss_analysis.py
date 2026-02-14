"""
Thermal Loss Analysis page for Solar Portfolio Manager.
Analyzes performance degradation due to high temperatures.
"""
import reflex as rx
from solar_portfolio_manager.state import AppState
from solar_portfolio_manager.components.layout import section_header, divider
from solar_portfolio_manager.components.kpi_card import kpi_card
from solar_portfolio_manager.components.alert import info_alert, error_alert, warning_alert
from solar_portfolio_manager.styles import heading_style, COLORS, card_style


def thermal_loss_analysis_page() -> rx.Component:
    """The Thermal Loss Analysis page for temperature-related performance analysis."""
    return rx.vstack(
        rx.heading("🌡️ Thermal Loss Analysis", style=heading_style, size="8"),
        rx.text(
            "Analyze performance degradation due to high module temperatures.",
            color=COLORS["text_secondary"]
        ),
        
        divider(),
        
        # Configuration Section
        section_header("Analysis Configuration", "Set up thermal analysis parameters."),
        
        rx.box(
            rx.vstack(
                rx.grid(
                    # Column 1: Plant Selection
                    rx.vstack(
                        rx.text("Plant Selection", font_weight="600"),
                        rx.select(
                            AppState.registered_plant_aliases,
                            placeholder="Select a plant...",
                            value=AppState.thermal_plant_alias,
                            on_change=AppState.set_thermal_plant_alias,
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
                                value=AppState.thermal_start_date,
                                on_change=AppState.set_thermal_start_date,
                                min=AppState.data_min_date,
                                max=AppState.data_max_date,
                            ),
                            rx.text("to"),
                            rx.input(
                                type="date",
                                value=AppState.thermal_end_date,
                                on_change=AppState.set_thermal_end_date,
                                min=AppState.data_min_date,
                                max=AppState.data_max_date,
                            ),
                            spacing="2",
                            align="center",
                        ),
                        spacing="2",
                        align_items="start",
                    ),
                    # Column 2: Module Parameters
                    rx.vstack(
                        rx.text("Module Temperature Coefficient (%/°C)", font_weight="600"),
                        rx.input(
                            type="number",
                            placeholder="-0.4",
                            default_value="-0.4",
                            on_change=AppState.set_thermal_temp_coeff_str,
                        ),
                        rx.text("Reference Temperature (°C)", font_weight="600", margin_top="1rem"),
                        rx.input(
                            type="number",
                            placeholder="25",
                            default_value="25",
                            on_change=AppState.set_thermal_ref_temp_str,
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
                        AppState.thermal_loading,
                        rx.spinner(size="1"),
                        rx.icon("play"),
                    ),
                    "Run Thermal Analysis",
                    color_scheme="teal",
                    size="3",
                    on_click=AppState.run_thermal_analysis,
                    disabled=AppState.thermal_loading,
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
            AppState.thermal_error != "",
            error_alert(AppState.thermal_error),
            rx.fragment(),
        ),
        
        # Results Section
        section_header("Analysis Results", "Thermal loss patterns will be displayed here."),
        
        rx.cond(
            AppState.thermal_result.contains("status"),
            warning_alert("Thermal analysis backend is not yet implemented. Coming soon!"),
            rx.box(
                rx.vstack(
                    info_alert("Configure the parameters and click 'Run Thermal Analysis' to see results."),
                    rx.box(
                        rx.hstack(
                            rx.vstack(
                                rx.text("🌡️", font_size="2rem"),
                                rx.text("Temperature vs Performance", font_weight="600"),
                                rx.text("Chart placeholder", color=COLORS["text_secondary"], font_size="0.85rem"),
                                align="center",
                            ),
                            rx.vstack(
                                rx.text("📉", font_size="2rem"),
                                rx.text("Monthly Thermal Losses", font_weight="600"),
                                rx.text("Chart placeholder", color=COLORS["text_secondary"], font_size="0.85rem"),
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
