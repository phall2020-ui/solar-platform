"""Navigation sidebar component."""
import reflex as rx
from solar_portfolio_manager.state import AppState
from solar_portfolio_manager.styles import (
    sidebar_style,
    nav_button_active_style,
    nav_button_inactive_style,
    logo_glyph_style,
    logo_wordmark_style,
    COLORS,
)

# Try to import app version
try:
    from unified_config import config
    APP_VERSION = config.APP_VERSION
except ImportError:
    APP_VERSION = "1.0.0"


def nav_button(label: str, page_name: str) -> rx.Component:
    """Navigation button for sidebar."""
    return rx.box(
        rx.text(label, font_size="0.9rem"),
        on_click=lambda: AppState.set_page(page_name),
        style=rx.cond(
            AppState.current_page == page_name,
            nav_button_active_style,
            nav_button_inactive_style,
        ),
        _hover={
            "background_color": COLORS["surface"],
            "color": "white",
        },
    )


def nav_section(title: str) -> rx.Component:
    """Section header in navigation."""
    return rx.text(
        title,
        font_size="0.75rem",
        font_weight="bold",
        color=COLORS["text_secondary"],
        margin_top="1rem",
        margin_bottom="0.5rem",
        padding_left="0.5rem",
    )


def sidebar() -> rx.Component:
    """Main navigation sidebar."""
    return rx.box(
        rx.vstack(
            # Logo area
            rx.hstack(
                rx.box(style=logo_glyph_style),
                rx.text("AMPYR", style=logo_wordmark_style),
                spacing="2",
                align_items="center",
            ),
            rx.text(
                "Solar Portfolio Manager",
                font_size="0.9rem",
                color=COLORS["text_secondary"],
            ),
            rx.text(
                f"v{APP_VERSION}",
                font_size="0.75rem",
                color=COLORS["text_secondary"],
                opacity="0.7",
            ),
            
            rx.divider(margin_y="1rem", border_color=COLORS["border"]),
            
            # Overview section
            nav_section("📊 OVERVIEW"),
            nav_button("Dashboard", "Dashboard"),
            
            # Operations section
            nav_section("🔧 OPERATIONS"),
            nav_button("Plant Management", "Plant Management"),
            nav_button("POA Import", "POA Import"),
            nav_button("Database Viewer", "Database Viewer"),
            nav_button("Data Explorer", "Data Explorer"),
            
            # Analysis section
            nav_section("📈 ANALYSIS"),
            nav_button("Data Overview", "Data Overview"),
            nav_button("Fouling Analysis", "Fouling Analysis"),
            nav_button("Shading Analysis", "Shading Analysis"),
            nav_button("Clipping Analysis", "Clipping Analysis"),
            nav_button("Thermal Loss Analysis", "Thermal Loss Analysis"),
            nav_button("Loss Waterfall", "Loss Waterfall"),
            
            # Reporting section
            nav_section("💼 REPORTING"),
            nav_button("Monthly Performance", "Monthly Performance"),
            nav_button("Waterfall Analysis", "Waterfall Analysis"),
            nav_button("Excom Report", "Excom Report"),
            nav_button("Report Builder", "Report Builder"),
            
            # Advanced section
            nav_section("🔍 ADVANCED"),
            nav_button("Comparative Analysis", "Comparative Analysis"),
            nav_button("Data Export", "Data Export"),
            nav_button("API Management", "API Management"),
            nav_button("Notifications", "Notifications"),
            
            rx.divider(margin_y="1rem", border_color=COLORS["border"]),
            
            # Settings
            nav_section("⚙️ SETTINGS"),
            nav_button("Settings", "Settings"),
            
            # Spacer to push footer to bottom
            rx.spacer(),
            
            # Footer
            rx.text(
                "AMPYR Solar Portfolio Manager",
                font_size="0.7rem",
                color=COLORS["text_secondary"],
                text_align="center",
                opacity="0.6",
            ),
            rx.text(
                "Combining operational and financial analysis",
                font_size="0.65rem",
                color=COLORS["text_secondary"],
                text_align="center",
                opacity="0.5",
            ),
            
            spacing="1",
            align_items="stretch",
            height="100%",
        ),
        style=sidebar_style,
    )
