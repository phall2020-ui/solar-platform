"""
Settings page for Solar Portfolio Manager.
Application settings and preferences.
"""
import reflex as rx
from solar_portfolio_manager.state import AppState
from solar_portfolio_manager.components.layout import section_header, divider
from solar_portfolio_manager.components.alert import info_alert
from solar_portfolio_manager.styles import heading_style, COLORS, card_style


def settings_page() -> rx.Component:
    """The Settings page for application configuration."""
    return rx.vstack(
        rx.heading("⚙️ Settings", style=heading_style, size="8"),
        rx.text(
            "Configure application preferences and general settings.",
            color=COLORS["text_secondary"]
        ),
        
        divider(),
        
        # Display Settings
        section_header("Display Settings", "Customize how data is displayed."),
        
        rx.box(
            rx.vstack(
                rx.hstack(
                    rx.text("Theme", font_weight="600", min_width="150px"),
                    rx.select(
                        ["Light", "Dark", "System"],
                        default_value="Light",
                    ),
                    spacing="4",
                    width="100%",
                ),
                rx.hstack(
                    rx.text("Date Format", font_weight="600", min_width="150px"),
                    rx.select(
                        ["YYYY-MM-DD", "DD/MM/YYYY", "MM/DD/YYYY"],
                        default_value="YYYY-MM-DD",
                    ),
                    spacing="4",
                    width="100%",
                ),
                rx.hstack(
                    rx.text("Number Format", font_weight="600", min_width="150px"),
                    rx.select(
                        ["1,234.56", "1.234,56", "1 234.56"],
                        default_value="1,234.56",
                    ),
                    spacing="4",
                    width="100%",
                ),
                spacing="3",
                width="100%",
            ),
            style=card_style,
            width="100%",
        ),
        
        divider(),
        
        # Data Settings
        section_header("Data Settings", "Configure data handling preferences."),
        
        rx.box(
            rx.vstack(
                rx.hstack(
                    rx.text("Auto-refresh Interval", font_weight="600", min_width="150px"),
                    rx.select(
                        ["Off", "5 minutes", "15 minutes", "30 minutes", "1 hour"],
                        default_value="Off",
                    ),
                    spacing="4",
                    width="100%",
                ),
                rx.hstack(
                    rx.text("Default Date Range", font_weight="600", min_width="150px"),
                    rx.select(
                        ["Last 7 days", "Last 30 days", "Last 90 days", "Year to date"],
                        default_value="Last 30 days",
                    ),
                    spacing="4",
                    width="100%",
                ),
                spacing="3",
                width="100%",
            ),
            style=card_style,
            width="100%",
        ),
        
        divider(),
        
        # About
        section_header("About", "Application information."),
        
        rx.box(
            rx.vstack(
                rx.hstack(
                    rx.text("Version", font_weight="600", min_width="150px"),
                    rx.text("2.0.0 (Reflex)"),
                    spacing="4",
                ),
                rx.hstack(
                    rx.text("Framework", font_weight="600", min_width="150px"),
                    rx.text("Reflex"),
                    spacing="4",
                ),
                rx.hstack(
                    rx.text("Python", font_weight="600", min_width="150px"),
                    rx.text("3.14"),
                    spacing="4",
                ),
                rx.button("Save Settings", color_scheme="teal", margin_top="1rem"),
                spacing="2",
                width="100%",
            ),
            style=card_style,
            width="100%",
        ),
        
        spacing="6",
        width="100%",
        align_items="stretch",
    )
