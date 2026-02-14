"""
Report Builder page for Solar Portfolio Manager.
Generate custom PDF/Word reports from analysis results.
"""
import reflex as rx
from solar_portfolio_manager.state import AppState
from solar_portfolio_manager.components.layout import section_header, divider
from solar_portfolio_manager.components.alert import info_alert
from solar_portfolio_manager.styles import heading_style, COLORS, card_style


def report_builder_page() -> rx.Component:
    """The Report Builder page for creating custom reports."""
    return rx.vstack(
        rx.heading("📝 Report Builder", style=heading_style, size="8"),
        rx.text(
            "Create and export custom reports from your analysis results.",
            color=COLORS["text_secondary"]
        ),
        
        divider(),
        
        # Report Configuration
        section_header("Report Configuration", "Set up your report parameters."),
        
        rx.box(
            rx.vstack(
                rx.grid(
                    rx.vstack(
                        rx.text("Report Title", font_weight="600"),
                        rx.input(placeholder="Monthly Performance Report"),
                        rx.text("Plants to Include", font_weight="600", margin_top="1rem"),
                        rx.select(
                            AppState.registered_plant_aliases,
                            placeholder="All plants...",
                        ),
                        spacing="2",
                        align_items="start",
                    ),
                    rx.vstack(
                        rx.text("Report Period", font_weight="600"),
                        rx.hstack(
                            rx.input(type="date"),
                            rx.text("to"),
                            rx.input(type="date"),
                            spacing="2",
                        ),
                        rx.text("Output Format", font_weight="600", margin_top="1rem"),
                        rx.radio_group(
                            items=["PDF", "Word Document", "Excel"],
                            default_value="PDF",
                        ),
                        spacing="2",
                        align_items="start",
                    ),
                    columns=rx.breakpoints(initial="1", md="2"),
                    spacing="6",
                    width="100%",
                ),
                rx.divider(margin_y="1rem"),
                
                # Include Sections
                rx.text("Include Sections", font_weight="600"),
                rx.hstack(
                    rx.checkbox("Executive Summary", default_checked=True),
                    rx.checkbox("Performance Charts", default_checked=True),
                    rx.checkbox("Detailed Data Tables"),
                    rx.checkbox("Loss Analysis"),
                    spacing="4",
                    flex_wrap="wrap",
                ),
                
                rx.hstack(
                    rx.button(
                        rx.icon("eye"),
                        "Preview",
                        variant="outline",
                    ),
                    rx.button(
                        rx.icon("download"),
                        "Generate & Download",
                        color_scheme="teal",
                    ),
                    spacing="3",
                    margin_top="1rem",
                ),
                spacing="4",
                width="100%",
            ),
            style=card_style,
            width="100%",
        ),
        
        divider(),
        
        # Report Queue
        section_header("Report Items", "Items added to the current report."),
        
        info_alert("Add items from analysis pages using the 'Add to Report' buttons, or configure above to generate a new report."),
        
        spacing="6",
        width="100%",
        align_items="stretch",
    )
