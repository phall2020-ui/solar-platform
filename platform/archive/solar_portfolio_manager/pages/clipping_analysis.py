"""
Clipping Analysis page for Solar Portfolio Manager.
Analyzes inverter clipping losses when DC power exceeds AC capacity.
"""
import reflex as rx
from solar_portfolio_manager.state import AppState
from solar_portfolio_manager.components.layout import section_header, divider
from solar_portfolio_manager.components.kpi_card import kpi_card
from solar_portfolio_manager.components.alert import info_alert, error_alert, success_alert
from solar_portfolio_manager.styles import heading_style, COLORS, card_style


def clipping_analysis_page() -> rx.Component:
    """The Clipping Analysis page for inverter capacity analysis."""
    return rx.vstack(
        rx.heading("⚡ Clipping Analysis", style=heading_style, size="8"),
        rx.text(
            "Analyze inverter clipping losses when DC power exceeds AC capacity limits.",
            color=COLORS["text_secondary"]
        ),
        
        divider(),
        
        # Configuration Section
        section_header("Inverter Configuration", "Set up inverter parameters for clipping simulation."),
        
        rx.box(
            rx.vstack(
                rx.grid(
                    # Column 1: Plant Selection
                    rx.vstack(
                        rx.text("Plant Selection", font_weight="600"),
                        rx.select(
                            AppState.registered_plant_aliases,
                            placeholder="Select a plant...",
                            value=AppState.clipping_plant_alias,
                            on_change=AppState.set_clipping_plant_alias,
                        ),
                        rx.text("Analysis Year", font_weight="600", margin_top="1rem"),
                        rx.input(
                            type="number",
                            placeholder="2024",
                            default_value="2024",
                            on_change=AppState.set_clipping_year_str,
                        ),
                        spacing="2",
                        align_items="start",
                    ),
                    # Column 2: Inverter Specs
                    rx.vstack(
                        rx.text("DC Capacity per Inverter (kW)", font_weight="600"),
                        rx.input(
                            type="number",
                            placeholder="100",
                            default_value="100",
                            on_change=AppState.set_clipping_dc_capacity_str,
                        ),
                        rx.text("AC Capacity per Inverter (kW)", font_weight="600", margin_top="1rem"),
                        rx.input(
                            type="number",
                            placeholder="80",
                            default_value="80",
                            on_change=AppState.set_clipping_ac_capacity_str,
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
                        AppState.clipping_loading,
                        rx.spinner(size="1"),
                        rx.icon("play"),
                    ),
                    "Run Clipping Simulation",
                    color_scheme="teal",
                    size="3",
                    on_click=AppState.run_clipping_analysis,
                    disabled=AppState.clipping_loading,
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
            AppState.clipping_error != "",
            error_alert(AppState.clipping_error),
            rx.fragment(),
        ),
        
        # Results Section
        section_header("Simulation Results", "Clipping losses will be displayed here."),
        
        rx.cond(
            AppState.clipping_result.contains("has_data"),
            rx.vstack(
                success_alert("Simulation complete!"),
                rx.text("Metrics and charts will be displayed here.", color=COLORS["text_secondary"]),
                spacing="4",
                width="100%",
            ),
            rx.box(
                rx.vstack(
                    info_alert("Configure the inverter parameters and click 'Run Clipping Simulation' to see results."),
                    rx.box(
                        rx.hstack(
                            rx.vstack(
                                rx.text("📊", font_size="2rem"),
                                rx.text("Clipping Events Timeline", font_weight="600"),
                                rx.text("Chart placeholder", color=COLORS["text_secondary"], font_size="0.85rem"),
                                align="center",
                            ),
                            rx.vstack(
                                rx.text("⚡", font_size="2rem"),
                                rx.text("Energy Loss Summary", font_weight="600"),
                                rx.text("KPI placeholder", color=COLORS["text_secondary"], font_size="0.85rem"),
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
