"""
Notifications page for Solar Portfolio Manager.
Configure alerts and notification preferences.
"""
import reflex as rx
from solar_portfolio_manager.state import AppState
from solar_portfolio_manager.components.layout import section_header, divider
from solar_portfolio_manager.components.alert import info_alert
from solar_portfolio_manager.styles import heading_style, COLORS, card_style


def notifications_page() -> rx.Component:
    """The Notifications page for alert configuration."""
    return rx.vstack(
        rx.heading("🔔 Notifications", style=heading_style, size="8"),
        rx.text(
            "Configure alerts and notification preferences for your portfolio.",
            color=COLORS["text_secondary"]
        ),
        
        divider(),
        
        # Alert Types
        section_header("Alert Configuration", "Choose which events trigger notifications."),
        
        rx.box(
            rx.vstack(
                rx.hstack(
                    rx.switch(default_checked=True),
                    rx.vstack(
                        rx.text("Performance Alerts", font_weight="600"),
                        rx.text("Notify when PR drops below threshold", color=COLORS["text_secondary"], font_size="0.85rem"),
                        spacing="0",
                        align_items="start",
                    ),
                    spacing="3",
                    width="100%",
                ),
                rx.divider(),
                rx.hstack(
                    rx.switch(default_checked=True),
                    rx.vstack(
                        rx.text("Inverter Offline", font_weight="600"),
                        rx.text("Notify when inverters go offline", color=COLORS["text_secondary"], font_size="0.85rem"),
                        spacing="0",
                        align_items="start",
                    ),
                    spacing="3",
                    width="100%",
                ),
                rx.divider(),
                rx.hstack(
                    rx.switch(),
                    rx.vstack(
                        rx.text("Daily Summary", font_weight="600"),
                        rx.text("Send daily portfolio summary email", color=COLORS["text_secondary"], font_size="0.85rem"),
                        spacing="0",
                        align_items="start",
                    ),
                    spacing="3",
                    width="100%",
                ),
                rx.divider(),
                rx.hstack(
                    rx.switch(),
                    rx.vstack(
                        rx.text("Weekly Report", font_weight="600"),
                        rx.text("Send weekly performance report", color=COLORS["text_secondary"], font_size="0.85rem"),
                        spacing="0",
                        align_items="start",
                    ),
                    spacing="3",
                    width="100%",
                ),
                spacing="3",
                width="100%",
            ),
            style=card_style,
            width="100%",
        ),
        
        divider(),
        
        # Notification Channels
        section_header("Notification Channels", "How you want to receive alerts."),
        
        rx.box(
            rx.vstack(
                rx.text("Email Address", font_weight="600"),
                rx.input(placeholder="your@email.com", type="email"),
                rx.text("Slack Webhook (Optional)", font_weight="600", margin_top="1rem"),
                rx.input(placeholder="https://hooks.slack.com/..."),
                rx.button("Save Preferences", color_scheme="teal", margin_top="1rem"),
                spacing="2",
                width="100%",
                align_items="start",
            ),
            style=card_style,
            width="100%",
        ),
        
        spacing="6",
        width="100%",
        align_items="stretch",
    )
