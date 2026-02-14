"""
Monthly Performance page for Solar Portfolio Manager.
Monthly performance reports and PR tracking.
"""
import reflex as rx
from solar_portfolio_manager.state import AppState
from solar_portfolio_manager.components.layout import section_header, divider
from solar_portfolio_manager.components.alert import info_alert
from solar_portfolio_manager.styles import heading_style, COLORS, card_style


def monthly_performance_page() -> rx.Component:
    """The Monthly Performance page for PR tracking."""
    return rx.vstack(
        rx.heading("📅 Monthly Performance", style=heading_style, size="8"),
        rx.text(
            "Track monthly performance ratios, energy yield, and availability metrics.",
            color=COLORS["text_secondary"]
        ),
        
        divider(),
        
        # Month Selection
        section_header("Report Period", "Select the month and plant."),
        
        rx.box(
            rx.hstack(
                rx.vstack(
                    rx.text("Plant", font_weight="600"),
                    rx.select(
                        AppState.registered_plant_aliases,
                        placeholder="Select a plant...",
                    ),
                    spacing="2",
                    flex="1",
                ),
                rx.vstack(
                    rx.text("Month", font_weight="600"),
                    rx.input(type="month"),
                    spacing="2",
                    flex="1",
                ),
                rx.button(
                    rx.icon("file-text"),
                    "Generate Report",
                    color_scheme="teal",
                    align_self="end",
                ),
                spacing="4",
                width="100%",
                align="end",
            ),
            style=card_style,
            width="100%",
        ),
        
        divider(),
        
        # Results Placeholder
        section_header("Performance Summary", "Monthly KPIs and charts."),
        
        info_alert("Select a plant and month, then click 'Generate Report' to view performance data."),
        
        rx.grid(
            rx.box(
                rx.vstack(
                    rx.text("📊", font_size="2rem"),
                    rx.text("Performance Ratio", font_weight="600"),
                    rx.text("—", font_size="1.5rem", color=COLORS["primary"]),
                    align="center",
                ),
                style=card_style,
            ),
            rx.box(
                rx.vstack(
                    rx.text("⚡", font_size="2rem"),
                    rx.text("Energy Yield (kWh)", font_weight="600"),
                    rx.text("—", font_size="1.5rem", color=COLORS["primary"]),
                    align="center",
                ),
                style=card_style,
            ),
            rx.box(
                rx.vstack(
                    rx.text("☀️", font_size="2rem"),
                    rx.text("Availability (%)", font_weight="600"),
                    rx.text("—", font_size="1.5rem", color=COLORS["primary"]),
                    align="center",
                ),
                style=card_style,
            ),
            columns=rx.breakpoints(initial="1", sm="2", lg="3"),
            spacing="4",
            width="100%",
        ),
        
        spacing="6",
        width="100%",
        align_items="stretch",
    )
