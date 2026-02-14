"""
Data Explorer page for Solar Portfolio Manager.
Execute custom SQL queries against the databases.
"""
import reflex as rx
from solar_portfolio_manager.state import AppState
from solar_portfolio_manager.components.layout import section_header, divider
from solar_portfolio_manager.components.alert import info_alert, warning_alert
from solar_portfolio_manager.styles import heading_style, COLORS, card_style


def data_explorer_page() -> rx.Component:
    """The Data Explorer page for running custom SQL queries."""
    return rx.vstack(
        rx.heading("🔍 Data Explorer", style=heading_style, size="8"),
        rx.text(
            "Execute custom SQL queries against the Solar Toolkit and Reporting databases.",
            color=COLORS["text_secondary"]
        ),
        
        divider(),
        
        # Query Editor Section
        section_header("SQL Query Editor", "Write and execute custom queries."),
        
        rx.box(
            rx.vstack(
                rx.text("Enter your SQL query:", font_weight="500"),
                rx.text_area(
                    placeholder="SELECT * FROM plants LIMIT 10",
                    min_height="150px",
                    width="100%",
                    font_family="monospace",
                    font_size="0.9rem",
                ),
                rx.hstack(
                    rx.button(
                        rx.icon("play"),
                        "Execute Query",
                        color_scheme="teal",
                    ),
                    rx.button(
                        rx.icon("trash-2"),
                        "Clear",
                        variant="outline",
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
        
        # Results Section
        section_header("Query Results", "Results will appear here after execution."),
        
        rx.box(
            rx.vstack(
                info_alert("Execute a query to see results here."),
                spacing="4",
                width="100%",
            ),
            width="100%",
        ),
        
        divider(),
        
        # Quick Queries Section
        section_header("Quick Queries", "Common queries you can run."),
        
        rx.grid(
            rx.box(
                rx.vstack(
                    rx.text("List All Plants", font_weight="600"),
                    rx.text("SELECT * FROM plants", font_family="monospace", font_size="0.8rem", color=COLORS["text_secondary"]),
                    rx.button("Run", size="1", variant="soft"),
                    spacing="2",
                    align_items="start",
                ),
                style=card_style,
            ),
            rx.box(
                rx.vstack(
                    rx.text("Recent Readings", font_weight="600"),
                    rx.text("SELECT * FROM readings ORDER BY timestamp DESC LIMIT 100", font_family="monospace", font_size="0.8rem", color=COLORS["text_secondary"]),
                    rx.button("Run", size="1", variant="soft"),
                    spacing="2",
                    align_items="start",
                ),
                style=card_style,
            ),
            rx.box(
                rx.vstack(
                    rx.text("Count by Plant", font_weight="600"),
                    rx.text("SELECT plant_uid, COUNT(*) FROM readings GROUP BY plant_uid", font_family="monospace", font_size="0.8rem", color=COLORS["text_secondary"]),
                    rx.button("Run", size="1", variant="soft"),
                    spacing="2",
                    align_items="start",
                ),
                style=card_style,
            ),
            columns=rx.breakpoints(initial="1", md="2", lg="3"),
            spacing="4",
            width="100%",
        ),
        
        spacing="6",
        width="100%",
        align_items="stretch",
    )
