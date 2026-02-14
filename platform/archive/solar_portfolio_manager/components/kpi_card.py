"""KPI Card component."""
import reflex as rx
from solar_portfolio_manager.styles import (
    card_style, 
    card_positive_style, 
    card_negative_style,
    COLORS,
)


def kpi_card(
    title: str,
    value: str,
    icon: str = "📊",
    delta: str = None,
    delta_positive: bool = True,
) -> rx.Component:
    """
    Render a KPI card with AMPYR styling.
    
    Args:
        title: Card title
        value: Main value to display
        icon: Emoji icon to display
        delta: Optional delta/change value
        delta_positive: Whether delta is positive (green) or negative (red)
    
    Returns:
        Reflex Component
    """
    # Choose style based on delta direction
    style = card_positive_style if delta_positive else card_negative_style
    
    # Delta display
    delta_component = rx.fragment()
    if delta:
        delta_color = COLORS["positive"] if delta_positive else COLORS["negative"]
        delta_arrow = "▲" if delta_positive else "▼"
        delta_component = rx.text(
            f"{delta_arrow} {delta}",
            color=delta_color,
            font_size="0.9rem",
        )
    
    return rx.box(
        rx.hstack(
            rx.text(icon, font_size="1.5rem"),
            rx.vstack(
                rx.text(
                    title, 
                    color=COLORS["text_secondary"], 
                    font_size="0.85rem",
                    margin_bottom="0.25rem",
                ),
                rx.text(
                    value, 
                    color=COLORS["primary"], 
                    font_size="1.75rem", 
                    font_weight="600",
                ),
                delta_component,
                spacing="1",
                align_items="flex_start",
            ),
            spacing="3",
            align_items="center",
        ),
        style=style,
    )


def kpi_row(metrics: list) -> rx.Component:
    """
    Render a row of KPI cards.
    
    Args:
        metrics: List of dicts with keys: title, value, delta (optional), icon (optional)
    
    Returns:
        Reflex Component with horizontal KPI cards
    """
    cards = []
    for metric in metrics:
        cards.append(
            kpi_card(
                title=metric.get('title', ''),
                value=metric.get('value', ''),
                icon=metric.get('icon', '📊'),
                delta=metric.get('delta'),
                delta_positive=metric.get('delta_positive', True),
            )
        )
    
    return rx.hstack(
        *cards,
        spacing="4",
        width="100%",
        flex_wrap="wrap",
    )
