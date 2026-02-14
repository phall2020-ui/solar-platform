"""
Loss Waterfall Analysis page for Solar Portfolio Manager.
Combines multiple analysis components to show comprehensive loss breakdown.
"""
import reflex as rx
from solar_portfolio_manager.state import AppState
from solar_portfolio_manager.components.layout import section_header, divider
from solar_portfolio_manager.components.kpi_card import kpi_card
from solar_portfolio_manager.components.alert import info_alert, error_alert, success_alert, warning_alert
from solar_portfolio_manager.styles import heading_style, COLORS, card_style


def loss_component_card(
    icon: str,
    title: str,
    loss_kwh: str,
    loss_pct: str,
    is_active: bool,
    status: str = ""
) -> rx.Component:
    """Card displaying a single loss component."""
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.text(icon, font_size="1.5rem"),
                rx.text(
                    title,
                    font_weight="600",
                    font_size="0.9rem",
                    color=rx.cond(is_active, COLORS["text"], COLORS["text_secondary"]),
                ),
                justify="between",
                width="100%",
            ),
            rx.cond(
                is_active,
                rx.vstack(
                    rx.text(
                        loss_kwh,
                        font_size="1.3rem",
                        font_weight="700",
                        color=COLORS["negative"] if loss_kwh != "0" else COLORS["text"],
                    ),
                    rx.text(
                        loss_pct,
                        font_size="0.85rem",
                        color=COLORS["text_secondary"],
                    ),
                    spacing="0",
                    align="start",
                ),
                rx.vstack(
                    rx.text(
                        "Not applicable",
                        font_size="0.9rem",
                        color=COLORS["text_secondary"],
                        font_style="italic",
                    ),
                    rx.text(
                        status,
                        font_size="0.75rem",
                        color=COLORS["text_secondary"],
                    ),
                    spacing="0",
                    align="start",
                ),
            ),
            spacing="2",
            align="start",
            width="100%",
        ),
        style={
            **card_style,
            "opacity": "1" if is_active else "0.5",
            "border_left": f"3px solid {COLORS['negative'] if is_active else COLORS['border']}",
        },
        width="100%",
    )


def loss_waterfall_page() -> rx.Component:
    """The Loss Waterfall Analysis page."""
    return rx.vstack(
        rx.heading("📉 Loss Waterfall", style=heading_style, size="8"),
        rx.text(
            "Comprehensive breakdown of generation losses for a selected site and month.",
            color=COLORS["text_secondary"]
        ),
        
        divider(),
        
        # Configuration Section
        section_header("Analysis Configuration", "Select a site and month to analyze."),
        
        rx.box(
            rx.vstack(
                rx.grid(
                    # Site Selection
                    rx.vstack(
                        rx.text("Site", font_weight="600"),
                        rx.select(
                            AppState.registered_plant_aliases,
                            placeholder="Select a site...",
                            value=AppState.lw_plant_alias,
                            on_change=AppState.set_lw_plant_alias,
                        ),
                        spacing="2",
                        align_items="start",
                    ),
                    # Month Selection
                    rx.vstack(
                        rx.text("Month", font_weight="600"),
                        rx.input(
                            type="month",
                            value=AppState.lw_month,
                            on_change=AppState.set_lw_month,
                        ),
                        spacing="2",
                        align_items="start",
                    ),
                    # Budget Generation (optional)
                    rx.vstack(
                        rx.text("Budget Generation (kWh)", font_weight="600"),
                        rx.input(
                            type="number",
                            placeholder="Optional - for % calculations",
                            value=AppState.lw_budget_gen_str,
                            on_change=AppState.set_lw_budget_gen_str,
                        ),
                        rx.text(
                            "Leave blank to show losses without budget comparison",
                            font_size="0.75rem",
                            color=COLORS["text_secondary"],
                        ),
                        spacing="2",
                        align_items="start",
                    ),
                    columns=rx.breakpoints(initial="1", md="3"),
                    spacing="6",
                    width="100%",
                ),
                rx.divider(margin_y="1rem"),
                rx.button(
                    rx.cond(
                        AppState.lw_loading,
                        rx.spinner(size="1"),
                        rx.icon("bar-chart-3"),
                    ),
                    "Analyze Losses",
                    color_scheme="teal",
                    size="3",
                    on_click=AppState.run_loss_waterfall,
                    disabled=AppState.lw_loading,
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
            AppState.lw_error != "",
            error_alert(AppState.lw_error),
            rx.fragment(),
        ),
        
        # Loading State
        rx.cond(
            AppState.lw_loading,
            rx.center(
                rx.spinner(size="3"),
                rx.text("Analyzing losses...", margin_left="10px"),
                padding="40px",
            ),
            rx.fragment(),
        ),
        
        # Results Section
        rx.cond(
            AppState.lw_has_results,
            rx.vstack(
                section_header("Loss Breakdown", f"Analysis for {AppState.lw_month}"),
                
                # Summary Cards Row
                rx.grid(
                    rx.box(
                        rx.vstack(
                            rx.text("📈", font_size="1.5rem"),
                            rx.text("Budget Generation", font_weight="600", font_size="0.9rem"),
                            rx.text(
                                AppState.lw_budget_display,
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
                            rx.text("Total Losses", font_weight="600", font_size="0.9rem"),
                            rx.text(
                                AppState.lw_total_loss_display,
                                font_size="1.5rem",
                                color=COLORS["negative"],
                                font_weight="700",
                            ),
                            rx.text(
                                AppState.lw_total_loss_pct_display,
                                font_size="0.8rem",
                                color=COLORS["text_secondary"],
                            ),
                            align="center",
                            spacing="1",
                        ),
                        style=card_style,
                    ),
                    rx.box(
                        rx.vstack(
                            rx.text("⚡", font_size="1.5rem"),
                            rx.text("Estimated Actual", font_weight="600", font_size="0.9rem"),
                            rx.text(
                                AppState.lw_actual_display,
                                font_size="1.5rem",
                                color=COLORS["positive"],
                                font_weight="700",
                            ),
                            rx.text("kWh", font_size="0.8rem", color=COLORS["text_secondary"]),
                            align="center",
                            spacing="1",
                        ),
                        style=card_style,
                    ),
                    columns=rx.breakpoints(initial="1", sm="3"),
                    spacing="4",
                    width="100%",
                ),
                
                # Waterfall Chart
                rx.cond(
                    AppState.lw_waterfall_fig,
                    rx.box(
                        rx.plotly(data=AppState.lw_waterfall_fig),
                        style=card_style,
                        width="100%",
                        margin_top="1rem",
                    ),
                ),
                
                divider(),
                
                # Loss Components Grid
                section_header("Loss Components", "Each category analyzed with seasonal logic."),
                
                rx.grid(
                    # Clipping
                    rx.box(
                        rx.vstack(
                            rx.hstack(
                                rx.text("⚡", font_size="1.3rem"),
                                rx.text("Clipping", font_weight="600"),
                                rx.cond(
                                    AppState.lw_clipping_active,
                                    rx.badge("Active", color_scheme="green", size="1"),
                                    rx.badge("Skipped", color_scheme="gray", size="1"),
                                ),
                                spacing="2",
                                align="center",
                            ),
                            rx.cond(
                                AppState.lw_clipping_active,
                                rx.text(
                                    AppState.lw_clipping_loss,
                                    font_size="1.2rem",
                                    font_weight="600",
                                    color=COLORS["negative"],
                                ),
                                rx.text(
                                    "Not applicable (winter month)",
                                    font_size="0.85rem",
                                    color=COLORS["text_secondary"],
                                    font_style="italic",
                                ),
                            ),
                            rx.text(
                                "Inverter capacity limits",
                                font_size="0.75rem",
                                color=COLORS["text_secondary"],
                            ),
                            spacing="2",
                            align="start",
                        ),
                        style=card_style,
                        opacity=rx.cond(AppState.lw_clipping_active, "1", "0.6"),
                    ),
                    # Curtailment
                    rx.box(
                        rx.vstack(
                            rx.hstack(
                                rx.text("🚫", font_size="1.3rem"),
                                rx.text("Curtailment", font_weight="600"),
                                rx.cond(
                                    AppState.lw_curtailment_active,
                                    rx.badge("Active", color_scheme="green", size="1"),
                                    rx.badge("Skipped", color_scheme="gray", size="1"),
                                ),
                                spacing="2",
                                align="center",
                            ),
                            rx.cond(
                                AppState.lw_curtailment_active,
                                rx.text(
                                    AppState.lw_curtailment_loss,
                                    font_size="1.2rem",
                                    font_weight="600",
                                    color=COLORS["negative"],
                                ),
                                rx.text(
                                    "No limitation device",
                                    font_size="0.85rem",
                                    color=COLORS["text_secondary"],
                                    font_style="italic",
                                ),
                            ),
                            rx.text(
                                "Grid export limits",
                                font_size="0.75rem",
                                color=COLORS["text_secondary"],
                            ),
                            spacing="2",
                            align="start",
                        ),
                        style=card_style,
                        opacity=rx.cond(AppState.lw_curtailment_active, "1", "0.6"),
                    ),
                    # Thermal
                    rx.box(
                        rx.vstack(
                            rx.hstack(
                                rx.text("🌡️", font_size="1.3rem"),
                                rx.text("Thermal", font_weight="600"),
                                rx.cond(
                                    AppState.lw_thermal_active,
                                    rx.badge("Active", color_scheme="green", size="1"),
                                    rx.badge("Skipped", color_scheme="gray", size="1"),
                                ),
                                spacing="2",
                                align="center",
                            ),
                            rx.cond(
                                AppState.lw_thermal_active,
                                rx.text(
                                    AppState.lw_thermal_loss,
                                    font_size="1.2rem",
                                    font_weight="600",
                                    color=COLORS["negative"],
                                ),
                                rx.text(
                                    "Not applicable (cool month)",
                                    font_size="0.85rem",
                                    color=COLORS["text_secondary"],
                                    font_style="italic",
                                ),
                            ),
                            rx.text(
                                "Temperature derating",
                                font_size="0.75rem",
                                color=COLORS["text_secondary"],
                            ),
                            spacing="2",
                            align="start",
                        ),
                        style=card_style,
                        opacity=rx.cond(AppState.lw_thermal_active, "1", "0.6"),
                    ),
                    # Shading
                    rx.box(
                        rx.vstack(
                            rx.hstack(
                                rx.text("🌑", font_size="1.3rem"),
                                rx.text("Shading", font_weight="600"),
                                rx.cond(
                                    AppState.lw_shading_active,
                                    rx.badge("Active", color_scheme="green", size="1"),
                                    rx.badge("Skipped", color_scheme="gray", size="1"),
                                ),
                                spacing="2",
                                align="center",
                            ),
                            rx.cond(
                                AppState.lw_shading_active,
                                rx.text(
                                    AppState.lw_shading_loss,
                                    font_size="1.2rem",
                                    font_weight="600",
                                    color=COLORS["negative"],
                                ),
                                rx.text(
                                    "Not applicable (summer month)",
                                    font_size="0.85rem",
                                    color=COLORS["text_secondary"],
                                    font_style="italic",
                                ),
                            ),
                            rx.text(
                                "Low sun angle losses",
                                font_size="0.75rem",
                                color=COLORS["text_secondary"],
                            ),
                            spacing="2",
                            align="start",
                        ),
                        style=card_style,
                        opacity=rx.cond(AppState.lw_shading_active, "1", "0.6"),
                    ),
                    # Fouling
                    rx.box(
                        rx.vstack(
                            rx.hstack(
                                rx.text("🧹", font_size="1.3rem"),
                                rx.text("Fouling/Soiling", font_weight="600"),
                                rx.cond(
                                    AppState.lw_fouling_active,
                                    rx.badge("Active", color_scheme="green", size="1"),
                                    rx.badge("Skipped", color_scheme="gray", size="1"),
                                ),
                                spacing="2",
                                align="center",
                            ),
                            rx.cond(
                                AppState.lw_fouling_active,
                                rx.text(
                                    AppState.lw_fouling_loss,
                                    font_size="1.2rem",
                                    font_weight="600",
                                    color=COLORS["negative"],
                                ),
                                rx.text(
                                    "No data",
                                    font_size="0.85rem",
                                    color=COLORS["text_secondary"],
                                    font_style="italic",
                                ),
                            ),
                            rx.text(
                                "Panel soiling",
                                font_size="0.75rem",
                                color=COLORS["text_secondary"],
                            ),
                            spacing="2",
                            align="start",
                        ),
                        style=card_style,
                        opacity=rx.cond(AppState.lw_fouling_active, "1", "0.6"),
                    ),
                    # Availability
                    rx.box(
                        rx.vstack(
                            rx.hstack(
                                rx.text("⏸️", font_size="1.3rem"),
                                rx.text("Availability", font_weight="600"),
                                rx.cond(
                                    AppState.lw_availability_active,
                                    rx.badge("Active", color_scheme="green", size="1"),
                                    rx.badge("Skipped", color_scheme="gray", size="1"),
                                ),
                                spacing="2",
                                align="center",
                            ),
                            rx.cond(
                                AppState.lw_availability_active,
                                rx.text(
                                    AppState.lw_availability_loss,
                                    font_size="1.2rem",
                                    font_weight="600",
                                    color=COLORS["negative"],
                                ),
                                rx.text(
                                    "No downtime data",
                                    font_size="0.85rem",
                                    color=COLORS["text_secondary"],
                                    font_style="italic",
                                ),
                            ),
                            rx.text(
                                "System downtime",
                                font_size="0.75rem",
                                color=COLORS["text_secondary"],
                            ),
                            spacing="2",
                            align="start",
                        ),
                        style=card_style,
                        opacity=rx.cond(AppState.lw_availability_active, "1", "0.6"),
                    ),
                    columns=rx.breakpoints(initial="1", sm="2", lg="3"),
                    spacing="4",
                    width="100%",
                ),
                
                divider(),
                
                # Seasonal Logic Info
                rx.box(
                    rx.vstack(
                        rx.hstack(
                            rx.icon("info", size=16),
                            rx.text("Seasonal Logic", font_weight="600"),
                            spacing="2",
                        ),
                        rx.text(
                            "Loss components are automatically enabled based on UK seasonal patterns:",
                            color=COLORS["text_secondary"],
                            font_size="0.9rem",
                        ),
                        rx.hstack(
                            rx.badge("Clipping: Apr-Sep", color_scheme="orange"),
                            rx.badge("Thermal: May-Sep", color_scheme="red"),
                            rx.badge("Shading: Oct-Feb", color_scheme="blue"),
                            rx.badge("Fouling: Year-round", color_scheme="gray"),
                            rx.badge("Curtailment: Year-round", color_scheme="purple"),
                            spacing="2",
                            flex_wrap="wrap",
                        ),
                        spacing="3",
                        align="start",
                    ),
                    style=card_style,
                    width="100%",
                    background=f"linear-gradient(135deg, {COLORS['surface']} 0%, {COLORS['background']} 100%)",
                ),
                
                spacing="4",
                width="100%",
            ),
            # No results state
            rx.cond(
                ~AppState.lw_loading,
                info_alert("Select a site and month, then click 'Analyze Losses' to see the breakdown."),
                rx.fragment(),
            ),
        ),
        
        spacing="6",
        width="100%",
        align_items="stretch",
    )
