"""
API Management page for Solar Portfolio Manager.
Manage API connections and credentials.
"""
import reflex as rx
from solar_portfolio_manager.state import AppState
from solar_portfolio_manager.components.layout import section_header, divider
from solar_portfolio_manager.components.alert import info_alert, warning_alert
from solar_portfolio_manager.styles import heading_style, COLORS, card_style


def api_management_page() -> rx.Component:
    """The API Management page for managing external connections."""
    return rx.vstack(
        rx.heading("🔌 API Management", style=heading_style, size="8"),
        rx.text(
            "Manage API credentials and connection settings for external data sources.",
            color=COLORS["text_secondary"]
        ),
        
        divider(),
        
        # EMIG API Section
        section_header("EMIG API", "Connection to plant monitoring API."),
        
        rx.box(
            rx.vstack(
                rx.hstack(
                    rx.text("Status:", font_weight="600"),
                    rx.badge("Connected", color_scheme="green", variant="soft"),
                    spacing="2",
                ),
                rx.grid(
                    rx.vstack(
                        rx.text("API URL", font_weight="500", color=COLORS["text_secondary"]),
                        rx.input(placeholder="https://api.example.com", type="url"),
                        spacing="1",
                    ),
                    rx.vstack(
                        rx.text("API Key", font_weight="500", color=COLORS["text_secondary"]),
                        rx.input(placeholder="••••••••", type="password"),
                        spacing="1",
                    ),
                    columns=rx.breakpoints(initial="1", md="2"),
                    spacing="4",
                    width="100%",
                ),
                rx.hstack(
                    rx.button("Test Connection", variant="outline"),
                    rx.button("Save Changes", color_scheme="teal"),
                    spacing="3",
                ),
                spacing="4",
                width="100%",
            ),
            style=card_style,
            width="100%",
        ),
        
        divider(),
        
        # SolarGIS API Section
        section_header("SolarGIS API", "Weather and irradiance data source."),
        
        rx.box(
            rx.vstack(
                rx.hstack(
                    rx.text("Status:", font_weight="600"),
                    rx.badge("Not Configured", color_scheme="gray", variant="soft"),
                    spacing="2",
                ),
                rx.grid(
                    rx.vstack(
                        rx.text("API Key", font_weight="500", color=COLORS["text_secondary"]),
                        rx.input(placeholder="Enter SolarGIS API key", type="password"),
                        spacing="1",
                    ),
                    rx.vstack(
                        rx.text("Site ID", font_weight="500", color=COLORS["text_secondary"]),
                        rx.input(placeholder="Enter Site ID"),
                        spacing="1",
                    ),
                    columns=rx.breakpoints(initial="1", md="2"),
                    spacing="4",
                    width="100%",
                ),
                rx.button("Configure SolarGIS", color_scheme="teal"),
                spacing="4",
                width="100%",
            ),
            style=card_style,
            width="100%",
        ),
        
        spacing="6",
        width="100%",
        align_items="stretch",
    )
