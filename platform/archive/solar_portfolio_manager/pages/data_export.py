"""
Data Export page for Solar Portfolio Manager.
Export data in various formats.
"""
import reflex as rx
from solar_portfolio_manager.state import AppState
from solar_portfolio_manager.components.layout import section_header, divider
from solar_portfolio_manager.components.alert import info_alert, success_alert, error_alert
from solar_portfolio_manager.styles import heading_style, COLORS, card_style


def data_export_page() -> rx.Component:
    """The Data Export page for bulk data export."""
    return rx.vstack(
        rx.heading("📤 Data Export", style=heading_style, size="8"),
        rx.text(
            "Export operational data and analysis results in various formats.",
            color=COLORS["text_secondary"]
        ),
        
        divider(),
        
        # Export Configuration
        section_header("Export Configuration", "Set up your export parameters."),
        
        rx.box(
            rx.vstack(
                rx.grid(
                    rx.vstack(
                        rx.text("Data Type", font_weight="600"),
                        rx.select(
                            ["Operational Readings", "POA Data", "Plant Registry", "Analysis Results"],
                            value=AppState.export_data_type,
                            on_change=AppState.set_export_data_type,
                        ),
                        rx.text("Plant Filter", font_weight="600", margin_top="1rem"),
                        rx.select(
                            AppState.registered_plant_aliases,
                            placeholder="All plants...",
                            value=AppState.export_plant_filter,
                            on_change=AppState.set_export_plant_filter,
                        ),
                        spacing="2",
                        align_items="start",
                    ),
                    rx.vstack(
                        rx.text("Date Range", font_weight="600"),
                        rx.cond(
                            AppState.data_min_date != "",
                            rx.text(
                                rx.text.span("Data available: ", color=COLORS["text_secondary"]),
                                rx.text.span(AppState.data_min_date, font_weight="500"),
                                rx.text.span(" to ", color=COLORS["text_secondary"]),
                                rx.text.span(AppState.data_max_date, font_weight="500"),
                                font_size="0.85rem",
                                margin_bottom="0.5rem",
                            ),
                            rx.fragment(),
                        ),
                        rx.hstack(
                            rx.input(
                                type="date",
                                value=AppState.export_start_date,
                                on_change=AppState.set_export_start_date,
                                min=AppState.data_min_date,
                                max=AppState.data_max_date,
                            ),
                            rx.text("to"),
                            rx.input(
                                type="date",
                                value=AppState.export_end_date,
                                on_change=AppState.set_export_end_date,
                                min=AppState.data_min_date,
                                max=AppState.data_max_date,
                            ),
                            spacing="2",
                        ),
                        rx.text("Export Format", font_weight="600", margin_top="1rem"),
                        rx.radio_group(
                            items=["CSV", "Excel", "Parquet", "JSON"],
                            value=AppState.export_format,
                            on_change=AppState.set_export_format,
                        ),
                        spacing="2",
                        align_items="start",
                    ),
                    columns=rx.breakpoints(initial="1", md="2"),
                    spacing="6",
                    width="100%",
                ),
                rx.divider(margin_y="1rem"),
                rx.hstack(
                    rx.button(
                        rx.cond(
                            AppState.export_loading,
                            rx.spinner(size="1"),
                            rx.icon("download"),
                        ),
                        "Export Data",
                        color_scheme="teal",
                        on_click=AppState.run_data_export,
                        disabled=AppState.export_loading,
                    ),
                    spacing="3",
                ),
                spacing="4",
                width="100%",
            ),
            style=card_style,
            width="100%",
        ),
        
        divider(),
        
        # Success/Error messages
        rx.cond(
            AppState.export_result != "",
            success_alert(AppState.export_result),
            rx.fragment(),
        ),
        rx.cond(
            AppState.export_error != "",
            error_alert(AppState.export_error),
            rx.fragment(),
        ),
        
        section_header("Recent Exports", "Previously generated exports."),
        
        info_alert("Export history will be shown here after exports are generated."),
        
        spacing="6",
        width="100%",
        align_items="stretch",
    )
