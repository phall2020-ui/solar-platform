"""
Responsive layout patterns for Streamlit.

Provides reusable layout helpers that create consistent page structures.
These patterns work within Streamlit's constraints while maximizing
visual consistency across the application.

DESIGN NOTES FOR EXTRACTION:
- When moving to React, these patterns become CSS Grid / Flexbox layouts
- column_layout → CSS Grid with auto-fill
- page_header → React component with breadcrumbs
"""
import streamlit as st
from typing import Any


def page_header(
    title: str,
    subtitle: str = "",
    icon: str = "",
    actions: list[dict] | None = None,
):
    """Render a standardized page header with optional action buttons.

    Args:
        title: Page title
        subtitle: Optional subtitle/description
        icon: Optional emoji icon
        actions: Optional list of action buttons [{"label": "Refresh", "key": "refresh_btn"}]
    """
    title_text = f"{icon} {title}" if icon else title

    if actions:
        cols = st.columns([4, *[1 for _ in actions]])
        with cols[0]:
            st.title(title_text)
        for i, action in enumerate(actions):
            with cols[i + 1]:
                st.button(
                    action.get("label", ""),
                    key=action.get("key", f"action_{i}"),
                    use_container_width=True,
                )
    else:
        st.title(title_text)

    if subtitle:
        st.caption(subtitle)


def two_column_layout(
    main_ratio: int = 2,
    sidebar_ratio: int = 1,
) -> tuple:
    """Create a main content + sidebar layout.

    Returns:
        Tuple of (main_column, sidebar_column) Streamlit containers

    Usage:
        main, sidebar = two_column_layout()
        with main:
            st.write("Main content")
        with sidebar:
            st.write("Sidebar content")
    """
    return st.columns([main_ratio, sidebar_ratio])


def card_grid(
    items: list[dict[str, Any]],
    columns: int = 3,
    render_fn: Any = None,
):
    """Render items in a responsive card grid.

    Args:
        items: List of item dicts to render
        columns: Number of columns (default: 3)
        render_fn: Function to render each item. Receives (item, index).
                   If None, renders item["title"] and item.get("description").
    """
    for row_start in range(0, len(items), columns):
        row_items = items[row_start : row_start + columns]
        cols = st.columns(columns)
        for i, item in enumerate(row_items):
            with cols[i]:
                if render_fn:
                    render_fn(item, row_start + i)
                else:
                    _default_card_render(item)


def _default_card_render(item: dict):
    """Default card rendering for card_grid."""
    title = item.get("title", "Untitled")
    description = item.get("description", "")
    icon = item.get("icon", "")

    st.markdown(
        f"""
        <div style="
            background: white;
            border-radius: 0.5rem;
            padding: 1rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            margin-bottom: 0.5rem;
            min-height: 80px;
        ">
            <div style="font-size: 1rem; font-weight: 600; color: #1B4D5C;">
                {icon} {title}
            </div>
            <div style="font-size: 0.85rem; color: #7F8C8D; margin-top: 0.25rem;">
                {description}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def filter_bar(*filter_configs: dict) -> dict[str, Any]:
    """Render a horizontal filter bar with multiple inputs.

    Args:
        filter_configs: Dicts defining each filter, e.g.:
            {"key": "status", "label": "Status", "type": "selectbox", "options": ["All", "Active", "Offline"]}
            {"key": "search", "label": "Search", "type": "text_input", "placeholder": "Filter..."}

    Returns:
        Dict of filter values keyed by their 'key' field.
    """
    if not filter_configs:
        return {}

    cols = st.columns(len(filter_configs))
    values: dict[str, Any] = {}

    for i, cfg in enumerate(filter_configs):
        with cols[i]:
            key = cfg["key"]
            label = cfg.get("label", key.title())
            input_type = cfg.get("type", "text_input")

            if input_type == "selectbox":
                values[key] = st.selectbox(
                    label,
                    options=cfg.get("options", []),
                    key=f"filter_{key}",
                    label_visibility="collapsed",
                )
            elif input_type == "text_input":
                values[key] = st.text_input(
                    label,
                    key=f"filter_{key}",
                    placeholder=cfg.get("placeholder", f"Filter by {label}..."),
                    label_visibility="collapsed",
                )
            elif input_type == "date_input":
                values[key] = st.date_input(
                    label,
                    key=f"filter_{key}",
                    label_visibility="collapsed",
                )

    return values


def metric_section(title: str, description: str = "", icon: str = ""):
    """Render a section divider with title.

    Usage:
        metric_section("Portfolio Overview", icon="📊")
        # ... render metrics below
    """
    st.divider()
    header = f"{icon} {title}" if icon else title
    st.subheader(header)
    if description:
        st.caption(description)
