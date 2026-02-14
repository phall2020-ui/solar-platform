"""Alert/notification box component."""
import reflex as rx
from solar_portfolio_manager.styles import (
    alert_success_style,
    alert_error_style,
    alert_warning_style,
    alert_info_style,
    COLORS,
)


def alert_box(
    message: str,
    alert_type: str = "info",
    icon: str = None,
) -> rx.Component:
    """
    Render a styled alert box.
    
    Args:
        message: Content of the alert (supports markdown)
        alert_type: 'success', 'warning', 'error', 'info'
        icon: Optional custom icon (emoji)
    
    Returns:
        Reflex Component
    """
    # Map alert types to styles and default icons
    style_map = {
        'success': alert_success_style,
        'warning': alert_warning_style,
        'error': alert_error_style,
        'info': alert_info_style,
    }
    
    icon_map = {
        'success': '✅',
        'warning': '⚠️',
        'error': '❌',
        'info': 'ℹ️',
    }
    
    style = style_map.get(alert_type, alert_info_style)
    display_icon = icon or icon_map.get(alert_type, 'ℹ️')
    
    return rx.box(
        rx.hstack(
            rx.text(display_icon, font_size="1.25rem"),
            rx.box(
                rx.markdown(message),
                flex="1",
                font_size="0.95rem",
                line_height="1.5",
                color=COLORS["text"],
            ),
            align_items="flex_start",
            spacing="3",
        ),
        style=style,
    )


def success_alert(message: str, icon: str = None) -> rx.Component:
    """Shorthand for success alert."""
    return alert_box(message, "success", icon)


def error_alert(message: str, icon: str = None) -> rx.Component:
    """Shorthand for error alert."""
    return alert_box(message, "error", icon)


def warning_alert(message: str, icon: str = None) -> rx.Component:
    """Shorthand for warning alert."""
    return alert_box(message, "warning", icon)


def info_alert(message: str, icon: str = None) -> rx.Component:
    """Shorthand for info alert."""
    return alert_box(message, "info", icon)
