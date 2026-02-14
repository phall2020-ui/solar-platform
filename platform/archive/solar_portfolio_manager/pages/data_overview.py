"""
Data Overview page for Solar Portfolio Manager.
High-level statistics and data health summary.
"""
import reflex as rx
from solar_portfolio_manager.state import AppState
from solar_portfolio_manager.components.layout import section_header, divider
from solar_portfolio_manager.components.kpi_card import kpi_card, kpi_row
from solar_portfolio_manager.components.alert import info_alert, success_alert
from solar_portfolio_manager.styles import heading_style, COLORS, card_style


def data_overview_page() -> rx.Component:
    """The Data Overview page showing portfolio-wide statistics."""
    return rx.vstack(
        rx.heading("📊 Data Overview", style=heading_style, size="8"),
        rx.text(
            "High-level summary of your solar portfolio data and health metrics.",
            color=COLORS["text_secondary"]
        ),
        
        divider(),
        
        # Portfolio KPIs
        section_header("Portfolio Summary", "Key metrics across all registered assets."),
        
        rx.cond(
            AppState.toolkit_available,
            rx.hstack(
                kpi_card(
                    title="Registered Plants",
                    value=AppState.total_plants_count.to_string(),
                    icon="🏭",
                ),
                kpi_card(
                    title="Total DC Capacity",
                    value=AppState.total_capacity_display,
                    icon="⚡",
                ),
                kpi_card(
                    title="Plants with Location",
                    value=AppState.plants_with_location.to_string(),
                    icon="📍",
                ),
                spacing="4",
                width="100%",
            ),
            info_alert("Solar Toolkit not connected. Connect to view portfolio statistics."),
        ),
        
        divider(),
        
        # Data Health Section
        section_header("Data Sources", "Connection status for your data sources."),
        
        rx.hstack(
            rx.box(
                rx.hstack(
                    rx.cond(
                        AppState.toolkit_available,
                        rx.icon("circle-check", color=COLORS["positive"]),
                        rx.icon("circle-x", color=COLORS["negative"]),
                    ),
                    rx.vstack(
                        rx.text("Solar Toolkit", font_weight="600"),
                        rx.cond(
                            AppState.toolkit_available,
                            rx.text("Connected", color=COLORS["positive"], font_size="0.85rem"),
                            rx.text("Not Available", color=COLORS["negative"], font_size="0.85rem"),
                        ),
                        spacing="0",
                        align_items="start",
                    ),
                    spacing="3",
                    align="center",
                ),
                style=card_style,
                flex="1",
            ),
            rx.box(
                rx.hstack(
                    rx.cond(
                        AppState.reporting_available,
                        rx.icon("circle-check", color=COLORS["positive"]),
                        rx.icon("circle-x", color=COLORS["negative"]),
                    ),
                    rx.vstack(
                        rx.text("Monthly Reporting", font_weight="600"),
                        rx.cond(
                            AppState.reporting_available,
                            rx.text("Connected", color=COLORS["positive"], font_size="0.85rem"),
                            rx.text("Not Available", color=COLORS["negative"], font_size="0.85rem"),
                        ),
                        spacing="0",
                        align_items="start",
                    ),
                    spacing="3",
                    align="center",
                ),
                style=card_style,
                flex="1",
            ),
            spacing="4",
            width="100%",
        ),
        
        divider(),
        
        # Reporting Tables Section
        section_header("Available Reporting Tables", "Tables available from Monthly Reporting database."),
        
        rx.cond(
            AppState.reporting_tables.length() > 0,
            rx.box(
                rx.vstack(
                    rx.foreach(
                        AppState.reporting_tables,
                        lambda table: rx.hstack(
                            rx.icon("table", size=16, color=COLORS["primary"]),
                            rx.text(table),
                            spacing="2",
                            padding="0.5rem 0",
                        )
                    ),
                    spacing="1",
                    align_items="start",
                    width="100%",
                ),
                style=card_style,
                width="100%",
            ),
            info_alert("No reporting tables available. Connect Monthly Reporting to view tables."),
        ),
        
        spacing="6",
        width="100%",
        align_items="stretch",
    )
