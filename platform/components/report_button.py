"""
Universal "Add to Report" Button Component
Captures charts, tables, and KPIs from any page and adds them to the report registry.
"""
import hashlib
import io
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st


def _figure_to_bytes(fig, width_inches: float, height_inches: float) -> bytes | None:
    """Convert any figure type to PNG bytes."""
    target_dpi = 130  # balance clarity vs payload

    # Plotly
    if hasattr(fig, 'to_image'):
        try:
            # Use kaleido backend
            img_bytes = fig.to_image(
                format="png",
                width=int(width_inches * target_dpi),
                height=int(height_inches * target_dpi),
                scale=1.5
            )
            return img_bytes
        except ValueError as e:
            if "kaleido" in str(e).lower():
                st.error("📦 Missing dependency: kaleido")
                st.code("pip install --upgrade kaleido", language="bash")
                st.info("After installing, restart the Streamlit app.")
            else:
                st.warning(f"Could not convert Plotly figure: {e}")
            return None
        except Exception as e:
            st.warning(f"Could not convert Plotly figure: {e}")
            return None

    # Matplotlib
    elif hasattr(fig, 'savefig'):
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=target_dpi, bbox_inches='tight')
        buf.seek(0)
        return buf.getvalue()

    # Altair
    elif hasattr(fig, 'to_dict'):  # Altair charts have to_dict
        # Try vl-convert first (modern, simpler dependency)
        try:
            import vl_convert as vlc
            vega_spec = fig.to_dict()
            png_data = vlc.vegalite_to_png(
                vega_spec,
                scale=2
            )
            return png_data
        except ImportError:
            pass  # Try other methods

        # Try altair_saver if available
        try:
            import altair_saver
            buf = io.BytesIO()
            altair_saver.save(fig, buf, fmt='png')
            buf.seek(0)
            return buf.getvalue()
        except ImportError:
            pass  # Try other methods

        # Fallback: try Altair's native save method
        try:
            buf = io.BytesIO()
            fig.save(buf, format='png')
            buf.seek(0)
            return buf.getvalue()
        except Exception:
            pass

        # Last resort: store as JSON spec (can be rendered later)
        st.warning("Altair chart export requires 'vl-convert-python'. Install with: pip install vl-convert-python")
        st.info("Alternatively, consider using Plotly charts which have built-in PNG export.")
        return None

    else:
        st.error(f"Unsupported figure type: {type(fig)}")
        return None


def _dataframe_to_thumb(df: pd.DataFrame, max_rows: int = 5) -> bytes:
    """Create thumbnail image of dataframe."""
    try:
        # Use matplotlib to render table
        fig, ax = plt.subplots(figsize=(4, 2))
        ax.axis('tight')
        ax.axis('off')

        display_df = df.head(max_rows)

        # Handle wide dataframes
        if len(display_df.columns) > 6:
            display_df = display_df.iloc[:, :6]

        table = ax.table(
            cellText=display_df.values,
            colLabels=display_df.columns,
            cellLoc='left',
            loc='center'
        )
        table.auto_set_font_size(False)
        table.set_fontsize(6)
        table.scale(1, 1.5)

        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=100, bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)

        return buf.getvalue()
    except Exception:
        # Return None if thumbnail generation fails
        return None


def _kpi_to_thumb(kpi_dict: dict) -> bytes:
    """Create thumbnail for KPI."""
    try:
        fig, ax = plt.subplots(figsize=(2, 1))
        ax.axis('off')

        # Extract first few KPIs if dict
        if isinstance(kpi_dict, dict):
            items = list(kpi_dict.items())[:3]
            text = "\n".join([f"{k}: {v}" for k, v in items])
        else:
            text = str(kpi_dict)

        ax.text(0.5, 0.5, text,
                ha='center', va='center', fontsize=8, weight='bold')

        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=80, bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)

        return buf.getvalue()
    except Exception:
        return None


def _text_to_thumb(text: str, max_chars: int = 100) -> bytes:
    """Create thumbnail for text block."""
    try:
        fig, ax = plt.subplots(figsize=(3, 1))
        ax.axis('off')

        preview = text[:max_chars] + "..." if len(text) > max_chars else text
        ax.text(0, 0.5, preview, ha='left', va='center', fontsize=7, wrap=True)

        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=80, bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)

        return buf.getvalue()
    except Exception:
        return None


def add_to_report_button(
    content,
    title: str,
    item_type: str = 'chart',
    description: str = "",
    source_page: str = "",
    width: float = 6.0,
    height: float = 4.0,
    button_key: str = None
) -> bool:
    """
    Universal button to add any content to the report.

    Args:
        content: Figure (Plotly/Matplotlib/Altair), DataFrame, dict (KPI), or str (text)
        title: Display title for the item
        item_type: 'chart', 'table', 'kpi', or 'text'
        description: Optional description
        source_page: Name of the current page/tab
        width: PDF width in inches
        height: PDF height in inches
        button_key: Unique button key (auto-generated if None)

    Returns:
        bool: True if button was clicked and item added
    """
    from modules.report_builder import ReportItem, ReportRegistry

    temp_dir = Path("reports") / "tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    MAX_TABLE_ROWS = 500
    MAX_TABLE_COLS = 25

    # Auto-generate key if not provided
    if button_key is None:
        # Create hash from title and source
        hash_str = hashlib.md5(f"{source_page}_{title}".encode()).hexdigest()[:8]
        button_key = f"add_report_{hash_str}"

    # Get current count for badge
    count = ReportRegistry.get_count()

    # Defaults to avoid unbound references
    image_path = None
    data_path = None
    thumbnail_path = None

    # Render button
    col1, col2 = st.columns([3, 1])

    with col1:
        clicked = st.button(
            "📊 Add to Report",
            key=button_key,
            help=f"Add '{title}' to your custom report",
            use_container_width=True
        )

    with col2:
        if count > 0:
            st.caption(f"📋 {count} items")

    if clicked:
        # Generate unique ID
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        item_id = f"{source_page.replace(' ', '_')}_{item_type}_{timestamp}"

        # Convert content to appropriate format
        image_bytes = None
        dataframe = None
        kpi_data = None
        text_content = None
        thumbnail_bytes = None

        if item_type == 'chart':
            image_bytes = _figure_to_bytes(content, width, height)
            image_path = None
            if image_bytes:
                image_path = temp_dir / f"{item_id}_chart.png"
                image_path.write_bytes(image_bytes)
                # Create smaller thumbnail
                thumbnail_bytes = _figure_to_bytes(content, 2.0, 1.5)
                if thumbnail_bytes:
                    thumb_path = temp_dir / f"{item_id}_thumb.png"
                    thumb_path.write_bytes(thumbnail_bytes)
                    thumbnail_path = str(thumb_path)
                # Free session memory; keep path reference
                image_bytes = None
            else:
                st.error("Failed to convert chart to image. Cannot add to report.")
                return False

        elif item_type == 'table':
            if isinstance(content, pd.DataFrame):
                dataframe = content.copy()
                data_path = None
                truncated = False
                if len(dataframe) > MAX_TABLE_ROWS:
                    dataframe = dataframe.head(MAX_TABLE_ROWS)
                    truncated = True
                if len(dataframe.columns) > MAX_TABLE_COLS:
                    dataframe = dataframe.iloc[:, :MAX_TABLE_COLS]
                    truncated = True

                if truncated:
                    st.info(f"Table trimmed to {len(dataframe)} rows and {len(dataframe.columns)} columns for report performance.")

                # Create thumbnail
                thumbnail_bytes = _dataframe_to_thumb(dataframe)
                if thumbnail_bytes:
                    thumb_path = temp_dir / f"{item_id}_thumb.png"
                    thumb_path.write_bytes(thumbnail_bytes)
                    thumbnail_path = str(thumb_path)
                    thumbnail_bytes = None

                # Persist table to disk to avoid session bloat
                try:
                    data_path = temp_dir / f"{item_id}.csv"
                    dataframe.to_csv(data_path, index=False)
                except Exception:
                    data_path = None
                # Avoid storing full dataframe in session if persisted
                if data_path:
                    dataframe = None
            else:
                st.error("Content must be a pandas DataFrame for item_type='table'")
                return False

        elif item_type == 'kpi':
            if isinstance(content, dict):
                kpi_data = content
                # Create thumbnail
                thumbnail_bytes = _kpi_to_thumb(content)
            else:
                st.error("Content must be a dict for item_type='kpi'")
                return False

        elif item_type == 'text':
            text_content = str(content)
            thumbnail_bytes = _text_to_thumb(text_content)
            if thumbnail_bytes:
                thumb_path = temp_dir / f"{item_id}_thumb.png"
                thumb_path.write_bytes(thumbnail_bytes)
                thumbnail_path = str(thumb_path)
                thumbnail_bytes = None

        else:
            st.error(f"Unknown item_type: {item_type}")
            return False

        # Create ReportItem
        item = ReportItem(
            item_id=item_id,
            item_type=item_type,
            title=title,
            description=description,
            image_bytes=image_bytes,
            image_path=str(image_path) if image_path else None,
            dataframe=dataframe,
            data_path=str(data_path) if data_path else None,
            kpi_data=kpi_data,
            text_content=text_content,
            source_ref=None,
            source_page=source_page,
            created_at=datetime.now(),
            width_inches=width,
            height_inches=height,
            thumbnail_bytes=thumbnail_bytes,
            thumbnail_path=thumbnail_path if thumbnail_path else None
        )

        # Add to registry
        success = ReportRegistry.add_item(item)

        if success:
            st.success(f"✅ Added '{title}' to report!")
            st.toast(f"📋 {title} added to report ({ReportRegistry.get_count()} items)", icon="✅")
            return True

    return False
