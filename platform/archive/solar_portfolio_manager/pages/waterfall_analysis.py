"""
Waterfall Analysis page for Solar Portfolio Manager.
Variance analysis showing generation deviation breakdown.
"""
import reflex as rx
from solar_portfolio_manager.state import AppState
from solar_portfolio_manager.components.layout import section_header, divider
from solar_portfolio_manager.components.alert import info_alert, success_alert
from solar_portfolio_manager.styles import heading_style, COLORS, card_style


def waterfall_chart_page() -> rx.Component:
    """The Waterfall Analysis page for variance breakdown."""
    return rx.vstack(
        rx.heading("📊 Waterfall Analysis", style=heading_style, size="8"),
        rx.text(
            "Variance analysis showing generation deviation breakdown by factor.",
            color=COLORS["text_secondary"]
        ),
        
        divider(),
        
        # Filter Section
        section_header("Report Parameters", "Select the time period and site."),
        
        rx.box(
            rx.hstack(
                rx.vstack(
                    rx.text("Site", font_weight="600"),
                    rx.select(
                        AppState.registered_plant_aliases,
                        placeholder="All sites...",
                    ),
                    spacing="2",
                    flex="1",
                ),
                rx.vstack(
                    rx.text("Start Month", font_weight="600"),
                    rx.input(type="month"),
                    spacing="2",
                    flex="1",
                ),
                rx.vstack(
                    rx.text("End Month", font_weight="600"),
                    rx.input(type="month"),
                    spacing="2",
                    flex="1",
                ),
                rx.button(
                    rx.icon("bar-chart-3"),
                    "Generate Waterfall",
                    color_scheme="teal",
                    align_self="end",
                    on_click=AppState.generate_waterfall,
                ),
                spacing="4",
                width="100%",
                align="end",
            ),
            style=card_style,
            width="100%",
        ),
        
        divider(),
        
        # Waterfall Chart Section
        section_header("Generation Variance Breakdown", "Visualizing the factors affecting generation."),
        
        rx.cond(
            AppState.waterfall_loading,
            rx.center(
                rx.spinner(size="3"),
                rx.text("Generating waterfall chart...", margin_left="10px"),
                padding="40px",
            ),
            rx.cond(
                AppState.waterfall_data_available,
                rx.vstack(
                    # Summary cards
                    rx.grid(
                        rx.box(
                            rx.vstack(
                                rx.text("📈", font_size="1.5rem"),
                                rx.text("Budget Generation", font_weight="600", font_size="0.9rem"),
                                rx.text(
                                    AppState.waterfall_budget_gen,
                                    font_size="1.5rem",
                                    color=COLORS["primary"],
                                    font_weight="700",
                                ),
                                rx.text("kWh", font_size="0.8rem", color=COLORS["text_secondary"]),
                                align="center",
                                spacing="1",
                            ),
                            style=card_style,
                        ),
                        rx.box(
                            rx.vstack(
                                rx.text("⚡", font_size="1.5rem"),
                                rx.text("Actual Generation", font_weight="600", font_size="0.9rem"),
                                rx.text(
                                    AppState.waterfall_actual_gen,
                                    font_size="1.5rem",
                                    color=COLORS["primary"],
                                    font_weight="700",
                                ),
                                rx.text("kWh", font_size="0.8rem", color=COLORS["text_secondary"]),
                                align="center",
                                spacing="1",
                            ),
                            style=card_style,
                        ),
                        rx.box(
                            rx.vstack(
                                rx.text("📉", font_size="1.5rem"),
                                rx.text("Total Variance", font_weight="600", font_size="0.9rem"),
                                rx.text(
                                    AppState.waterfall_variance,
                                    font_size="1.5rem",
                                    color=rx.cond(
                                        AppState.waterfall_variance_positive,
                                        COLORS["positive"],
                                        COLORS["negative"],
                                    ),
                                    font_weight="700",
                                ),
                                rx.text("%", font_size="0.8rem", color=COLORS["text_secondary"]),
                                align="center",
                                spacing="1",
                            ),
                            style=card_style,
                        ),
                        columns=rx.breakpoints(initial="1", sm="2", lg="3"),
                        spacing="4",
                        width="100%",
                    ),
                    
                    # Waterfall Chart Placeholder
                    rx.box(
                        rx.vstack(
                            rx.text("🏗️ Waterfall Chart", font_size="1.2rem", font_weight="600"),
                            rx.text(
                                "Plotly waterfall chart will be rendered here.",
                                color=COLORS["text_secondary"],
                            ),
                            # TODO: Add rx.plotly with actual waterfall chart data
                            rx.box(
                                height="400px",
                                width="100%",
                                background=f"linear-gradient(135deg, {COLORS['surface']} 0%, {COLORS['background']} 100%)",
                                border_radius="8px",
                                border=f"1px dashed {COLORS['border']}",
                                display="flex",
                                align_items="center",
                                justify_content="center",
                            ),
                            align="center",
                            width="100%",
                        ),
                        style=card_style,
                        width="100%",
                    ),
                    
                    # Variance Breakdown Table
                    rx.box(
                        rx.vstack(
                            rx.text("Variance Factors", font_size="1.1rem", font_weight="600"),
                            rx.table.root(
                                rx.table.header(
                                    rx.table.row(
                                        rx.table.column_header_cell("Factor"),
                                        rx.table.column_header_cell("Impact (kWh)"),
                                        rx.table.column_header_cell("Impact (%)"),
                                    ),
                                ),
                                rx.table.body(
                                    rx.table.row(
                                        rx.table.cell("Irradiance Variance"),
                                        rx.table.cell("—"),
                                        rx.table.cell("—"),
                                    ),
                                    rx.table.row(
                                        rx.table.cell("Availability Losses"),
                                        rx.table.cell("—"),
                                        rx.table.cell("—"),
                                    ),
                                    rx.table.row(
                                        rx.table.cell("PR Deviation"),
                                        rx.table.cell("—"),
                                        rx.table.cell("—"),
                                    ),
                                    rx.table.row(
                                        rx.table.cell("Other Factors"),
                                        rx.table.cell("—"),
                                        rx.table.cell("—"),
                                    ),
                                ),
                                width="100%",
                            ),
                            spacing="4",
                            width="100%",
                        ),
                        style=card_style,
                        width="100%",
                    ),
                    spacing="4",
                    width="100%",
                ),
                # No data state
                info_alert("Select parameters and click 'Generate Waterfall' to view variance analysis."),
            ),
        ),
        
        spacing="6",
        width="100%",
        align_items="stretch",
    )
