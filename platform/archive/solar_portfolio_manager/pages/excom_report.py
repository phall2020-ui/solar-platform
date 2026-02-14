"""
Excom Report page for Solar Portfolio Manager.
Executive summary reports for monthly solar performance.
"""
import reflex as rx
from solar_portfolio_manager.state import AppState
from solar_portfolio_manager.components.layout import section_header, divider
from solar_portfolio_manager.components.alert import info_alert, success_alert, warning_alert
from solar_portfolio_manager.styles import heading_style, COLORS, card_style


def excom_report_page() -> rx.Component:
    """The Excom Report page for executive summaries."""
    return rx.vstack(
        rx.heading("📋 Excom Report", style=heading_style, size="8"),
        rx.text(
            "Executive summary reports for solar portfolio performance.",
            color=COLORS["text_secondary"]
        ),
        
        divider(),
        
        # Report Parameters
        section_header("Report Configuration", "Configure the executive report parameters."),
        
        rx.box(
            rx.hstack(
                rx.vstack(
                    rx.text("Report Month", font_weight="600"),
                    rx.input(type="month"),
                    spacing="2",
                    flex="1",
                ),
                rx.vstack(
                    rx.text("Report Type", font_weight="600"),
                    rx.select(
                        ["Monthly Summary", "YTD Summary", "Rolling 12 Months"],
                        placeholder="Select report type...",
                        default_value="Monthly Summary",
                    ),
                    spacing="2",
                    flex="1",
                ),
                rx.vstack(
                    rx.text("Format", font_weight="600"),
                    rx.select(
                        ["Dashboard", "PDF Export", "PowerPoint"],
                        placeholder="Select format...",
                        default_value="Dashboard",
                    ),
                    spacing="2",
                    flex="1",
                ),
                rx.button(
                    rx.icon("file-text"),
                    "Generate Report",
                    color_scheme="teal",
                    align_self="end",
                    on_click=AppState.generate_excom_report,
                ),
                spacing="4",
                width="100%",
                align="end",
            ),
            style=card_style,
            width="100%",
        ),
        
        divider(),
        
        # Executive Summary Section
        section_header("Portfolio Overview", "High-level performance metrics."),
        
        rx.grid(
            # Total Generation Card
            rx.box(
                rx.vstack(
                    rx.hstack(
                        rx.text("⚡", font_size="1.5rem"),
                        rx.text("Total Generation", font_weight="600"),
                        spacing="2",
                        justify="start",
                    ),
                    rx.text(
                        AppState.excom_total_generation,
                        font_size="2rem",
                        color=COLORS["primary"],
                        font_weight="700",
                    ),
                    rx.text("MWh", color=COLORS["text_secondary"]),
                    rx.hstack(
                        rx.text(
                            AppState.excom_gen_variance,
                            color=rx.cond(
                                AppState.excom_gen_variance_positive,
                                COLORS["positive"],
                                COLORS["negative"],
                            ),
                            font_weight="600",
                        ),
                        rx.text("vs budget", color=COLORS["text_secondary"]),
                        spacing="2",
                    ),
                    align="start",
                    spacing="2",
                ),
                style=card_style,
            ),
            # Weighted PR Card
            rx.box(
                rx.vstack(
                    rx.hstack(
                        rx.text("📊", font_size="1.5rem"),
                        rx.text("Weighted PR", font_weight="600"),
                        spacing="2",
                        justify="start",
                    ),
                    rx.text(
                        AppState.excom_weighted_pr,
                        font_size="2rem",
                        color=COLORS["primary"],
                        font_weight="700",
                    ),
                    rx.text("%", color=COLORS["text_secondary"]),
                    rx.hstack(
                        rx.text(
                            AppState.excom_pr_variance,
                            color=rx.cond(
                                AppState.excom_pr_variance_positive,
                                COLORS["positive"],
                                COLORS["negative"],
                            ),
                            font_weight="600",
                        ),
                        rx.text("vs target", color=COLORS["text_secondary"]),
                        spacing="2",
                    ),
                    align="start",
                    spacing="2",
                ),
                style=card_style,
            ),
            # Availability Card
            rx.box(
                rx.vstack(
                    rx.hstack(
                        rx.text("☀️", font_size="1.5rem"),
                        rx.text("Availability", font_weight="600"),
                        spacing="2",
                        justify="start",
                    ),
                    rx.text(
                        AppState.excom_availability,
                        font_size="2rem",
                        color=COLORS["primary"],
                        font_weight="700",
                    ),
                    rx.text("%", color=COLORS["text_secondary"]),
                    rx.hstack(
                        rx.text(
                            AppState.excom_avail_status,
                            color=rx.cond(
                                AppState.excom_avail_ok,
                                COLORS["positive"],
                                COLORS["warning"],
                            ),
                            font_weight="600",
                        ),
                        spacing="2",
                    ),
                    align="start",
                    spacing="2",
                ),
                style=card_style,
            ),
            # Plants Count Card
            rx.box(
                rx.vstack(
                    rx.hstack(
                        rx.text("🏭", font_size="1.5rem"),
                        rx.text("Active Sites", font_weight="600"),
                        spacing="2",
                        justify="start",
                    ),
                    rx.text(
                        AppState.excom_plant_count,
                        font_size="2rem",
                        color=COLORS["primary"],
                        font_weight="700",
                    ),
                    rx.text("plants", color=COLORS["text_secondary"]),
                    rx.hstack(
                        rx.text(
                            AppState.excom_total_capacity,
                            color=COLORS["text_secondary"],
                            font_weight="600",
                        ),
                        rx.text("MWp total", color=COLORS["text_secondary"]),
                        spacing="2",
                    ),
                    align="start",
                    spacing="2",
                ),
                style=card_style,
            ),
            columns=rx.breakpoints(initial="1", sm="2", lg="4"),
            spacing="4",
            width="100%",
        ),
        
        divider(),
        
        # Site Performance Table
        section_header("Site Performance Summary", "Individual site metrics for the period."),
        
        rx.box(
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("Site"),
                        rx.table.column_header_cell("Capacity (kWp)"),
                        rx.table.column_header_cell("Generation (MWh)"),
                        rx.table.column_header_cell("Budget (MWh)"),
                        rx.table.column_header_cell("Variance (%)"),
                        rx.table.column_header_cell("PR (%)"),
                        rx.table.column_header_cell("Availability (%)"),
                    ),
                ),
                rx.table.body(
                    rx.foreach(
                        AppState.excom_site_data,
                        lambda site: rx.table.row(
                            rx.table.cell(site["name"]),
                            rx.table.cell(site["capacity"]),
                            rx.table.cell(site["generation"]),
                            rx.table.cell(site["budget"]),
                            rx.table.cell(
                                site["variance"],
                                color=rx.cond(
                                    site["variance_positive"],
                                    COLORS["positive"],
                                    COLORS["negative"],
                                ),
                            ),
                            rx.table.cell(site["pr"]),
                            rx.table.cell(site["availability"]),
                        ),
                    ),
                ),
                width="100%",
            ),
            style=card_style,
            width="100%",
            overflow_x="auto",
        ),
        
        divider(),
        
        # Key Highlights
        section_header("Key Highlights & Actions", "Important observations and follow-up items."),
        
        rx.grid(
            rx.box(
                rx.vstack(
                    rx.text("🎯 Top Performers", font_weight="600", color=COLORS["positive"]),
                    rx.text("Sites exceeding budget targets:", color=COLORS["text_secondary"], font_size="0.9rem"),
                    rx.foreach(
                        AppState.excom_top_performers,
                        lambda site: rx.text(f"• {site}", font_size="0.9rem"),
                    ),
                    align="start",
                    spacing="2",
                ),
                style=card_style,
            ),
            rx.box(
                rx.vstack(
                    rx.text("⚠️ Attention Required", font_weight="600", color=COLORS["warning"]),
                    rx.text("Sites below target:", color=COLORS["text_secondary"], font_size="0.9rem"),
                    rx.foreach(
                        AppState.excom_underperformers,
                        lambda site: rx.text(f"• {site}", font_size="0.9rem"),
                    ),
                    align="start",
                    spacing="2",
                ),
                style=card_style,
            ),
            rx.box(
                rx.vstack(
                    rx.text("📋 Action Items", font_weight="600", color=COLORS["accent"]),
                    rx.text("Recommended follow-ups:", color=COLORS["text_secondary"], font_size="0.9rem"),
                    rx.foreach(
                        AppState.excom_action_items,
                        lambda item: rx.text(f"• {item}", font_size="0.9rem"),
                    ),
                    align="start",
                    spacing="2",
                ),
                style=card_style,
            ),
            columns=rx.breakpoints(initial="1", sm="2", lg="3"),
            spacing="4",
            width="100%",
        ),
        
        # Export button
        rx.hstack(
            rx.button(
                rx.icon("download"),
                "Export PDF",
                variant="outline",
                color_scheme="teal",
            ),
            rx.button(
                rx.icon("presentation"),
                "Export PowerPoint",
                variant="outline",
                color_scheme="teal",
            ),
            rx.button(
                rx.icon("mail"),
                "Email Report",
                variant="outline",
                color_scheme="teal",
            ),
            justify="end",
            width="100%",
            spacing="3",
        ),
        
        spacing="6",
        width="100%",
        align_items="stretch",
    )
