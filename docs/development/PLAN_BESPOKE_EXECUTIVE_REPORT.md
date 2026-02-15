# Bespoke Monthly Executive Report - Implementation Plan

## Overview

Enable users to create fully customizable Monthly Executive Reports by selecting any charts, tables, or visualizations from across the platform and composing them into a personalized report.

---

## Current State Analysis

### Existing Infrastructure
- **PDFReportGenerator** (`modules/report_generator.py`) - ReportLab-based PDF generation with AMPYR branding
- **Chart Generation** - Plotly, Matplotlib, and Altair charts across various tabs
- **Session State** - Already used for navigation and temporary data storage
- **Monthly Report Tab** - Has basic report composer with fixed sections

### Key Tabs with Reportable Content
| Tab | Available Charts/Tables |
|-----|------------------------|
| ExCom Report | Top/Bottom 5 tables, Waterfall charts, KPI summaries |
| Shading Analysis | Scatter plots, Hourly ratio heatmaps, Per-inverter efficiency charts |
| Fouling Analysis | Trend lines, PR vs Irradiance scatter, Daily bar charts |
| Clipping Analysis | Clipping loss visualizations |
| Dashboard | Portfolio KPIs, Data source comparisons |
| Waterfall Analysis | Loss breakdown charts by period |

---

## Proposed Architecture

### Core Components

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Report Builder System                            │
│                                                                      │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│  │  Report Registry │  │  Report Composer │  │  Report Preview  │  │
│  │  (Session State) │  │  (New Tab UI)    │  │  & Generator     │  │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘  │
│          ↑                                            ↓              │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │              "Add to Report" Buttons (All Tabs)              │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Implementation Plan

### Phase 1: Report Registry & Data Model

#### 1.1 Create Report Item Data Model

**New File: `modules/report_registry.py`**

```python
from dataclasses import dataclass, field
from typing import Optional, Literal, Any
from datetime import datetime
import uuid

@dataclass
class ReportItem:
    """Represents a single item (chart/table) to include in the report."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    item_type: Literal["chart", "table", "kpi", "text"] = "chart"
    title: str = ""
    description: str = ""
    source_tab: str = ""  # e.g., "Shading Analysis", "ExCom Report"

    # For charts: store figure object or regeneration params
    figure: Optional[Any] = None  # Plotly/Matplotlib figure
    figure_bytes: Optional[bytes] = None  # PNG bytes for persistence

    # For tables: store DataFrame
    dataframe: Optional[Any] = None

    # For KPIs: store metrics
    metrics: Optional[dict] = None

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    site_filter: Optional[str] = None
    date_range: Optional[tuple] = None

    # Report positioning
    order: int = 0
    page_break_before: bool = False
    width: Literal["full", "half"] = "full"

@dataclass
class ReportConfig:
    """Configuration for the entire report."""
    title: str = "Monthly Executive Report"
    subtitle: str = ""
    report_month: str = ""  # e.g., "Dec-24"
    items: list[ReportItem] = field(default_factory=list)
    include_cover_page: bool = True
    include_table_of_contents: bool = False
    created_at: datetime = field(default_factory=datetime.now)
```

#### 1.2 Report Registry Manager

**Add to `modules/report_registry.py`:**

```python
class ReportRegistry:
    """Manages the collection of report items in session state."""

    SESSION_KEY = "report_registry"

    @classmethod
    def initialize(cls):
        """Initialize registry in session state if not exists."""
        if cls.SESSION_KEY not in st.session_state:
            st.session_state[cls.SESSION_KEY] = ReportConfig()

    @classmethod
    def get_config(cls) -> ReportConfig:
        cls.initialize()
        return st.session_state[cls.SESSION_KEY]

    @classmethod
    def add_item(cls, item: ReportItem) -> bool:
        """Add item to report. Returns True if added."""
        config = cls.get_config()
        item.order = len(config.items)
        config.items.append(item)
        return True

    @classmethod
    def remove_item(cls, item_id: str):
        """Remove item by ID."""
        config = cls.get_config()
        config.items = [i for i in config.items if i.id != item_id]
        cls._reorder_items()

    @classmethod
    def reorder_items(cls, new_order: list[str]):
        """Reorder items by list of IDs."""
        config = cls.get_config()
        id_to_item = {i.id: i for i in config.items}
        config.items = [id_to_item[id] for id in new_order if id in id_to_item]
        cls._reorder_items()

    @classmethod
    def _reorder_items(cls):
        config = cls.get_config()
        for idx, item in enumerate(config.items):
            item.order = idx

    @classmethod
    def clear(cls):
        """Clear all items from report."""
        st.session_state[cls.SESSION_KEY] = ReportConfig()

    @classmethod
    def get_item_count(cls) -> int:
        return len(cls.get_config().items)

    @classmethod
    def set_report_month(cls, month: str):
        cls.get_config().report_month = month

    @classmethod
    def set_title(cls, title: str):
        cls.get_config().title = title
```

---

### Phase 2: "Add to Report" Component

#### 2.1 Reusable Add-to-Report Button Component

**New File: `components/add_to_report.py`**

```python
import streamlit as st
from modules.report_registry import ReportRegistry, ReportItem
import plotly.graph_objects as go
import matplotlib.figure
import io

def convert_figure_to_bytes(fig) -> bytes:
    """Convert Plotly or Matplotlib figure to PNG bytes."""
    if isinstance(fig, go.Figure):
        return fig.to_image(format="png", width=1200, height=600, scale=2)
    elif isinstance(fig, matplotlib.figure.Figure):
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        return buf.getvalue()
    return None

def add_to_report_button(
    fig=None,
    df=None,
    metrics=None,
    title: str = "",
    description: str = "",
    source_tab: str = "",
    item_type: str = "chart",
    site_filter: str = None,
    date_range: tuple = None,
    key: str = None
):
    """
    Renders an "Add to Report" button that saves the item to the report registry.

    Args:
        fig: Plotly or Matplotlib figure object
        df: DataFrame for tables
        metrics: Dict of KPI values
        title: Display title for the item
        description: Optional description
        source_tab: Name of the source tab
        item_type: "chart", "table", or "kpi"
        site_filter: Site name if applicable
        date_range: Tuple of (start_date, end_date) if applicable
        key: Unique key for the button
    """
    # Generate unique key if not provided
    if key is None:
        key = f"add_to_report_{title}_{source_tab}".replace(" ", "_").lower()

    col1, col2 = st.columns([3, 1])

    with col2:
        if st.button("📋 Add to Report", key=key, use_container_width=True):
            # Convert figure to bytes for persistence
            figure_bytes = None
            if fig is not None:
                try:
                    figure_bytes = convert_figure_to_bytes(fig)
                except Exception as e:
                    st.warning(f"Could not capture figure: {e}")

            item = ReportItem(
                item_type=item_type,
                title=title,
                description=description,
                source_tab=source_tab,
                figure=fig,
                figure_bytes=figure_bytes,
                dataframe=df.copy() if df is not None else None,
                metrics=metrics.copy() if metrics is not None else None,
                site_filter=site_filter,
                date_range=date_range
            )

            ReportRegistry.add_item(item)
            st.success(f"✅ Added '{title}' to report!")
            st.toast(f"📋 {title} added to report ({ReportRegistry.get_item_count()} items)")


def show_report_status_badge():
    """Shows a badge with current report item count in sidebar."""
    count = ReportRegistry.get_item_count()
    if count > 0:
        st.sidebar.markdown(f"""
        <div style="
            background-color: #00838f;
            color: white;
            padding: 8px 12px;
            border-radius: 8px;
            text-align: center;
            margin: 10px 0;
        ">
            📋 Report Items: <strong>{count}</strong>
        </div>
        """, unsafe_allow_html=True)

        if st.sidebar.button("📝 Go to Report Builder", use_container_width=True):
            st.session_state["current_page"] = "Monthly Executive Report"
            st.rerun()
```

---

### Phase 3: Integrate "Add to Report" Across Tabs

#### 3.1 Shading Analysis Tab Integration

**Modify: `modules/shading_analysis.py` (or wherever shading charts are generated)**

```python
from components.add_to_report import add_to_report_button

# After generating shading scatter chart:
st.plotly_chart(shading_fig, use_container_width=True)
add_to_report_button(
    fig=shading_fig,
    title=f"Shading Analysis - {site_name}",
    description=f"Baseline: {baseline_period}, Comparison: {comparison_period}",
    source_tab="Shading Analysis",
    item_type="chart",
    site_filter=site_name,
    date_range=(start_date, end_date),
    key=f"shading_scatter_{site_name}"
)

# After generating hourly ratio heatmap:
st.pyplot(heatmap_fig)
add_to_report_button(
    fig=heatmap_fig,
    title=f"Hourly Shading Ratio - {site_name}",
    source_tab="Shading Analysis",
    item_type="chart",
    key=f"shading_heatmap_{site_name}"
)
```

#### 3.2 ExCom Report Tab Integration

**Modify: `modules/excom_report.py` (or monthly_reporting.py ExCom section)**

```python
from components.add_to_report import add_to_report_button

# After generating Top/Bottom 5 table:
st.dataframe(top_bottom_df, use_container_width=True)
add_to_report_button(
    df=top_bottom_df,
    title=f"Top & Bottom 5 Sites - {metric_name}",
    description=f"Month: {selected_month}",
    source_tab="ExCom Report",
    item_type="table",
    key=f"top_bottom_5_{metric_name}"
)

# After generating waterfall chart:
st.plotly_chart(waterfall_fig, use_container_width=True)
add_to_report_button(
    fig=waterfall_fig,
    title=f"Loss Waterfall - {site_name}",
    source_tab="ExCom Report",
    item_type="chart",
    key=f"waterfall_{site_name}"
)
```

#### 3.3 Fouling Analysis Tab Integration

```python
# After generating fouling trend chart:
st.altair_chart(fouling_chart, use_container_width=True)
add_to_report_button(
    fig=fouling_chart,  # Note: May need Altair-to-PNG conversion
    title=f"Fouling Trend - {site_name}",
    source_tab="Fouling Analysis",
    item_type="chart",
    key=f"fouling_trend_{site_name}"
)
```

#### 3.4 Dashboard Integration

```python
# After generating portfolio KPIs:
add_to_report_button(
    metrics={
        "Total Sites": total_sites,
        "Avg PR": avg_pr,
        "Avg Availability": avg_availability,
        "Total Generation": total_gen
    },
    title="Portfolio KPI Summary",
    source_tab="Dashboard",
    item_type="kpi",
    key="dashboard_kpis"
)
```

---

### Phase 4: Monthly Executive Report Builder Tab

#### 4.1 New Report Builder UI

**New/Modified: `modules/executive_report_builder.py`**

```python
import streamlit as st
from modules.report_registry import ReportRegistry, ReportConfig
from modules.report_generator import PDFReportGenerator
from components.add_to_report import show_report_status_badge

def render_executive_report_builder():
    """Main UI for the bespoke report builder."""

    st.header("📊 Monthly Executive Report Builder")

    config = ReportRegistry.get_config()

    # === SECTION 1: Report Configuration ===
    with st.expander("⚙️ Report Configuration", expanded=True):
        col1, col2 = st.columns(2)

        with col1:
            # Month selector (from available data)
            available_months = get_available_months()  # From reporting DB
            selected_month = st.selectbox(
                "Report Month",
                options=available_months,
                index=0 if available_months else None,
                key="report_month_selector"
            )
            ReportRegistry.set_report_month(selected_month)

        with col2:
            report_title = st.text_input(
                "Report Title",
                value=config.title,
                key="report_title_input"
            )
            ReportRegistry.set_title(report_title)

        config.subtitle = st.text_input(
            "Subtitle (optional)",
            value=config.subtitle,
            placeholder="e.g., Q4 2024 Performance Summary"
        )

        col3, col4 = st.columns(2)
        with col3:
            config.include_cover_page = st.checkbox("Include Cover Page", value=True)
        with col4:
            config.include_table_of_contents = st.checkbox("Include Table of Contents", value=False)

    st.divider()

    # === SECTION 2: Report Items Manager ===
    st.subheader("📋 Report Items")

    if len(config.items) == 0:
        st.info("""
        **No items added to report yet.**

        Navigate to other tabs (Shading Analysis, ExCom Report, Fouling Analysis, etc.)
        and click **"📋 Add to Report"** next to any chart or table you want to include.
        """)

        # Quick links to other tabs
        st.markdown("**Quick Navigation:**")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            if st.button("📈 Shading Analysis"):
                st.session_state["current_page"] = "Shading Analysis"
                st.rerun()
        with col2:
            if st.button("📊 ExCom Report"):
                st.session_state["current_page"] = "ExCom Report"
                st.rerun()
        with col3:
            if st.button("🔍 Fouling Analysis"):
                st.session_state["current_page"] = "Fouling Analysis"
                st.rerun()
        with col4:
            if st.button("💧 Waterfall"):
                st.session_state["current_page"] = "Waterfall Analysis"
                st.rerun()

    else:
        # Display and manage report items
        st.write(f"**{len(config.items)} items** in your report:")

        # Drag-and-drop reordering (using session state for order)
        for idx, item in enumerate(config.items):
            with st.container():
                col1, col2, col3, col4, col5 = st.columns([0.5, 3, 1.5, 1, 0.5])

                with col1:
                    st.write(f"**{idx + 1}.**")

                with col2:
                    icon = {"chart": "📈", "table": "📋", "kpi": "🎯", "text": "📝"}.get(item.item_type, "📄")
                    st.write(f"{icon} **{item.title}**")
                    st.caption(f"Source: {item.source_tab}")

                with col3:
                    # Preview thumbnail
                    if item.figure_bytes:
                        st.image(item.figure_bytes, width=150)
                    elif item.dataframe is not None:
                        st.caption(f"Table: {len(item.dataframe)} rows")

                with col4:
                    # Reorder buttons
                    subcol1, subcol2 = st.columns(2)
                    with subcol1:
                        if idx > 0:
                            if st.button("⬆️", key=f"up_{item.id}"):
                                move_item_up(idx)
                                st.rerun()
                    with subcol2:
                        if idx < len(config.items) - 1:
                            if st.button("⬇️", key=f"down_{item.id}"):
                                move_item_down(idx)
                                st.rerun()

                with col5:
                    if st.button("🗑️", key=f"remove_{item.id}"):
                        ReportRegistry.remove_item(item.id)
                        st.rerun()

                st.divider()

        # Clear all button
        if st.button("🗑️ Clear All Items", type="secondary"):
            ReportRegistry.clear()
            st.rerun()

    st.divider()

    # === SECTION 3: Preview & Generate ===
    st.subheader("📄 Generate Report")

    if len(config.items) > 0:
        col1, col2 = st.columns(2)

        with col1:
            if st.button("👁️ Preview Report", use_container_width=True):
                render_report_preview(config)

        with col2:
            pdf_bytes = generate_report_pdf(config)
            if pdf_bytes:
                st.download_button(
                    "📥 Download PDF",
                    data=pdf_bytes,
                    file_name=f"Executive_Report_{config.report_month}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
    else:
        st.warning("Add at least one item to generate a report.")


def render_report_preview(config: ReportConfig):
    """Render an in-app preview of the report."""
    st.subheader("📄 Report Preview")

    if config.include_cover_page:
        st.markdown(f"""
        <div style="text-align: center; padding: 40px; background: linear-gradient(135deg, #00838f, #006064); color: white; border-radius: 10px; margin-bottom: 20px;">
            <h1>{config.title}</h1>
            <h3>{config.subtitle or config.report_month}</h3>
            <p>Generated: {datetime.now().strftime('%d %B %Y')}</p>
        </div>
        """, unsafe_allow_html=True)

    for item in config.items:
        st.markdown(f"### {item.title}")
        if item.description:
            st.caption(item.description)

        if item.item_type == "chart" and item.figure_bytes:
            st.image(item.figure_bytes, use_column_width=True)
        elif item.item_type == "table" and item.dataframe is not None:
            st.dataframe(item.dataframe, use_container_width=True)
        elif item.item_type == "kpi" and item.metrics:
            cols = st.columns(len(item.metrics))
            for col, (key, value) in zip(cols, item.metrics.items()):
                col.metric(key, value)

        st.divider()


def generate_report_pdf(config: ReportConfig) -> bytes:
    """Generate PDF from report configuration."""
    from modules.report_generator import PDFReportGenerator

    generator = PDFReportGenerator()

    # Add cover page
    if config.include_cover_page:
        generator.add_title_page(
            title=config.title,
            subtitle=config.subtitle or config.report_month
        )

    # Add each item
    for item in config.items:
        if item.page_break_before:
            generator.add_page_break()

        generator.add_section_header(item.title)

        if item.description:
            generator.add_paragraph(item.description)

        if item.item_type == "chart" and item.figure_bytes:
            generator.add_image_from_bytes(item.figure_bytes)
        elif item.item_type == "table" and item.dataframe is not None:
            generator.add_table(item.dataframe, item.title)
        elif item.item_type == "kpi" and item.metrics:
            generator.add_kpi_section(item.metrics)

    return generator.generate()


def move_item_up(idx: int):
    """Move item up in the order."""
    config = ReportRegistry.get_config()
    if idx > 0:
        config.items[idx], config.items[idx-1] = config.items[idx-1], config.items[idx]
        ReportRegistry._reorder_items()


def move_item_down(idx: int):
    """Move item down in the order."""
    config = ReportRegistry.get_config()
    if idx < len(config.items) - 1:
        config.items[idx], config.items[idx+1] = config.items[idx+1], config.items[idx]
        ReportRegistry._reorder_items()


def get_available_months():
    """Get list of available months from the reporting database."""
    from services.reporting_bridge import ReportingBridge
    try:
        df = ReportingBridge.get_table_data('solar_data')
        if df is not None and 'Date' in df.columns:
            return sorted(df['Date'].unique().tolist(), reverse=True)
    except:
        pass
    return []
```

---

### Phase 5: Enhance PDF Generator

#### 5.1 Add New Methods to PDFReportGenerator

**Modify: `modules/report_generator.py`**

```python
class PDFReportGenerator:
    # ... existing methods ...

    def add_image_from_bytes(self, img_bytes: bytes, width: float = None):
        """Add image from PNG bytes."""
        from reportlab.lib.utils import ImageReader
        from io import BytesIO

        img = ImageReader(BytesIO(img_bytes))
        img_width, img_height = img.getSize()

        # Scale to fit page width
        if width is None:
            width = self.page_width - 2 * self.margin

        aspect = img_height / img_width
        height = width * aspect

        # Check if we need a new page
        if self.y_position - height < self.margin:
            self.add_page_break()

        self.canvas.drawImage(
            img,
            self.margin,
            self.y_position - height,
            width=width,
            height=height
        )
        self.y_position -= height + 20

    def add_paragraph(self, text: str):
        """Add a paragraph of text."""
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph

        styles = getSampleStyleSheet()
        para = Paragraph(text, styles['Normal'])
        para.wrapOn(self.canvas, self.page_width - 2*self.margin, 100)
        para.drawOn(self.canvas, self.margin, self.y_position - para.height)
        self.y_position -= para.height + 10

    def add_kpi_section(self, metrics: dict):
        """Add a KPI metrics section with styled boxes."""
        box_width = (self.page_width - 2*self.margin - 30) / min(len(metrics), 4)
        box_height = 60

        x = self.margin
        for key, value in metrics.items():
            # Draw box
            self.canvas.setFillColor(colors.HexColor("#e0f2f1"))
            self.canvas.rect(x, self.y_position - box_height, box_width - 10, box_height, fill=1)

            # Draw label
            self.canvas.setFillColor(colors.HexColor("#00695c"))
            self.canvas.setFont("Helvetica", 10)
            self.canvas.drawString(x + 10, self.y_position - 20, str(key))

            # Draw value
            self.canvas.setFont("Helvetica-Bold", 16)
            self.canvas.drawString(x + 10, self.y_position - 45, str(value))

            x += box_width

        self.y_position -= box_height + 20
```

---

### Phase 6: Update Navigation & Sidebar

#### 6.1 Add Report Badge to Sidebar

**Modify: `components/sidebar.py`**

```python
from components.add_to_report import show_report_status_badge

def render_sidebar():
    # ... existing sidebar code ...

    # Add report status badge
    show_report_status_badge()

    # ... rest of sidebar ...
```

#### 6.2 Update Page Navigation

**Modify: `app.py`**

```python
# In the REPORTING section, add/update:
PAGES = {
    # ... existing pages ...
    "Monthly Executive Report": render_executive_report_builder,
    # ... other pages ...
}
```

---

## File Changes Summary

| File | Action | Description |
|------|--------|-------------|
| `modules/report_registry.py` | **CREATE** | New report item data model and registry manager |
| `components/add_to_report.py` | **CREATE** | Reusable "Add to Report" button component |
| `modules/executive_report_builder.py` | **CREATE** | New report builder UI tab |
| `modules/report_generator.py` | **MODIFY** | Add new methods for bytes images, paragraphs, KPIs |
| `modules/shading_analysis.py` | **MODIFY** | Add "Add to Report" buttons after charts |
| `modules/monthly_reporting.py` | **MODIFY** | Add "Add to Report" buttons in ExCom section |
| `modules/fouling_analysis.py` | **MODIFY** | Add "Add to Report" buttons after charts |
| `components/sidebar.py` | **MODIFY** | Add report status badge |
| `app.py` | **MODIFY** | Add new page to navigation |

---

## User Flow

```
1. User navigates to any analysis tab (Shading, Fouling, ExCom, etc.)
2. User configures analysis parameters and generates charts/tables
3. User clicks "📋 Add to Report" button next to desired visualizations
   → Toast notification confirms item added
   → Sidebar badge updates with item count
4. User repeats for all desired content across multiple tabs
5. User navigates to "Monthly Executive Report" tab
6. User sees all collected items with thumbnails
7. User reorders items using up/down arrows
8. User removes unwanted items
9. User configures report title, month, and options
10. User clicks "Preview" to see in-app preview
11. User clicks "Download PDF" to generate final report
```

---

## Future Enhancements

1. **Report Templates** - Save/load report configurations
2. **Scheduled Reports** - Auto-generate reports on schedule
3. **Email Delivery** - Send reports via email
4. **Multi-format Export** - PowerPoint, Word, HTML
5. **Collaborative Editing** - Share report drafts
6. **Custom Sections** - Add free-form text/commentary
7. **Chart Customization** - Edit titles/colors before adding to report
8. **Persistent Storage** - Save reports to database

---

## Implementation Order

1. **Phase 1** - Report Registry (foundation)
2. **Phase 2** - Add to Report component (enables collection)
3. **Phase 3** - Integrate across 2-3 tabs (prove concept)
4. **Phase 5** - Enhance PDF generator (required for output)
5. **Phase 4** - Report Builder UI (main interface)
6. **Phase 6** - Navigation updates (tie it together)
7. **Remaining Phase 3** - Integrate remaining tabs

Estimated effort: Medium complexity, ~2-3 development cycles to complete core functionality.
