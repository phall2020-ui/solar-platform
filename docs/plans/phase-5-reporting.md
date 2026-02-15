# Phase 5: Reporting Engine — Detailed Action Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Duration:** 3 weeks  
**Goal:** Build a report generation system with template-based monthly/ExCom/O&M reports, scheduled generation, PDF output with brand styling, and a report library. Migrate existing Monthly Reporting functionality and integrate with the analysis engines from Phase 3.

**Key Principle:** Report templates are data + layout specifications. The rendering pipeline is: Template → Data Fetcher (services) → Layout Engine (ReportLab/WeasyPrint) → PDF. Streamlit UI is only for template selection, preview, and scheduling.

**Prerequisite:** Phase 0 (database), Phase 3 (analysis engines for metrics), Phase 4 (alerts for report sections).

---

## Table of Contents

1. [Progress Tracker](#1-progress-tracker)
2. [Dependency Graph](#2-dependency-graph)
3. [Task 5.1: Report Template Schema](#task-51-report-template-schema)
4. [Task 5.2: Report Data Fetcher Service](#task-52-report-data-fetcher-service)
5. [Task 5.3: Monthly Performance Report Template](#task-53-monthly-performance-report-template)
6. [Task 5.4: ExCom Summary Report Template](#task-54-excom-summary-report-template)
7. [Task 5.5: O&M Report Template](#task-55-om-report-template)
8. [Task 5.6: PDF Rendering Engine](#task-56-pdf-rendering-engine)
9. [Task 5.7: Chart-to-Image Export](#task-57-chart-to-image-export)
10. [Task 5.8: Report Builder UI](#task-58-report-builder-ui)
11. [Task 5.9: Report Library & History](#task-59-report-library--history)
12. [Task 5.10: Scheduled Report Generation](#task-510-scheduled-report-generation)
13. [Risks](#risks)
14. [Definition of Done](#definition-of-done)

---

## 1. Progress Tracker

| Task | Status | Est Hours | Priority | Dependencies |
|------|--------|-----------|----------|--------------|
| 5.1 Report Template Schema | ✅ Done | 4 | P0 | Phase 0 |
| 5.2 Report Data Fetcher | ✅ Done | 8 | P0 | Phase 3 |
| 5.3 Monthly Performance Report | ✅ Done | 10 | P0 | 5.1, 5.2 |
| 5.4 ExCom Summary Report | ✅ Done | 6 | P1 | 5.1, 5.2 |
| 5.5 O&M Report | ✅ Done | 6 | P1 | 5.1, 5.2, Phase 4 |
| 5.6 PDF Rendering Engine | ✅ Done | 8 | P0 | 5.1 |
| 5.7 Chart-to-Image Export | ✅ Done | 4 | P0 | Phase 3.11 |
| 5.8 Report Builder UI | ✅ Done | 8 | P0 | 5.1, 5.6 |
| 5.9 Report Library & History | ✅ Done | 4 | P1 | 5.6 |
| 5.10 Scheduled Generation | ✅ Done | 4 | P2 | 5.6, 5.9 |
| **TOTAL** | | **62** | | |

---

## 2. Dependency Graph

```
┌─────────────────────────┐
│ 5.1 Report Template     │
│ Schema                  │
└──────────┬──────────────┘
           │
    ┌──────┼──────────────────┐
    │      │                  │
    ▼      ▼                  ▼
┌───────┐ ┌────────────┐ ┌──────────────┐
│ 5.2   │ │ 5.6 PDF    │ │ 5.7 Chart    │
│ Data  │ │ Rendering  │ │ Export       │
│Fetcher│ │ Engine     │ │              │
└──┬────┘ └─────┬──────┘ └──────┬───────┘
   │            │               │
   ├────────────┼───────────────┤
   │            │               │
   ▼            ▼               │
┌────────────────────┐          │
│ 5.3 Monthly Report │◄─────────┘
│ 5.4 ExCom Report   │
│ 5.5 O&M Report     │
└──────────┬─────────┘
           │
    ┌──────┼──────┐
    ▼      │      ▼
┌──────┐   │  ┌──────────┐
│ 5.8  │   │  │ 5.9      │
│ UI   │   │  │ Library  │
└──────┘   │  └────┬─────┘
           ▼       │
      ┌────────┐   │
      │ 5.10   │◄──┘
      │Schedule│
      └────────┘
```

---

## Task 5.1: Report Template Schema

**Goal:** Define report templates as structured data — sections, metrics, charts, and layout.

**Estimated Hours:** 4

### `services/reporting/__init__.py`
```python
"""Reporting engine package."""
```

### `services/reporting/models.py`
```python
"""
Report template and output models.

A report template defines:
- Sections (cover, KPI summary, charts, tables, appendix)
- Data requirements per section (which metrics, which plants)
- Layout preferences (orientation, margins, brand styling)

A generated report links a template + time range → PDF output.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ReportType(str, Enum):
    MONTHLY_PERFORMANCE = "monthly_performance"
    EXCOM_SUMMARY = "excom_summary"
    OM_REPORT = "om_report"
    CUSTOM = "custom"


class SectionType(str, Enum):
    COVER = "cover"
    KPI_SUMMARY = "kpi_summary"
    GENERATION_TABLE = "generation_table"
    PR_CHART = "pr_chart"
    GENERATION_CHART = "generation_chart"
    WATERFALL = "waterfall"
    ALERT_SUMMARY = "alert_summary"
    TICKET_SUMMARY = "ticket_summary"
    PLANT_DETAIL = "plant_detail"
    APPENDIX = "appendix"
    TEXT = "text"


class ReportSection(BaseModel):
    """A section within a report template."""
    type: SectionType
    title: str = ""
    plant_uid: str | None = None  # Optional scoping to specific plant
    config: dict[str, Any] = Field(default_factory=dict)
    page_break_before: bool = False


class ReportTemplate(BaseModel):
    """Report template definition."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    type: ReportType
    description: str = ""
    sections: list[ReportSection] = Field(default_factory=list)
    
    # Layout
    orientation: str = "portrait"   # "portrait" or "landscape"
    paper_size: str = "A4"
    
    # Brand
    include_cover: bool = True
    include_header: bool = True
    include_footer: bool = True
    logo_path: str = ""
    
    # Metadata
    created_by: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class GeneratedReport(BaseModel):
    """A generated report instance."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    template_id: str
    template_name: str
    report_type: ReportType
    
    # Time range
    period_start: datetime
    period_end: datetime
    period_label: str = ""  # e.g., "January 2025"
    
    # Scope
    plant_uids: list[str] = Field(default_factory=list)  # Empty = all plants
    
    # Output
    file_path: str = ""
    file_size_bytes: int = 0
    page_count: int = 0
    
    # Status
    status: str = "pending"  # "pending", "generating", "complete", "failed"
    error_message: str = ""
    
    # Metadata
    generated_by: str = ""
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    generation_seconds: float = 0.0
```

### Acceptance Criteria

- [ ] Template schema extensible for new report types
- [ ] Section types cover all known report components
- [ ] Generated report tracks file path, status, generation time

---

## Task 5.2: Report Data Fetcher Service

**Goal:** Service that collects all data needed for a report in one pass, using analysis engines from Phase 3.

**Estimated Hours:** 8

### `services/reporting/data_fetcher.py`
```python
"""
Report data fetcher — collects all data needed for report generation.

For each section type, fetches the required metrics/charts/tables
using the analysis engines and portfolio service.

This is the bridge between the report template and the data layer.
Fetched data is passed to the PDF renderer.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
import structlog

from services.analysis.clipping import ClippingEngine
from services.analysis.curtailment import CurtailmentEngine
from services.analysis.pr_trending import PRTrendingEngine
from services.portfolio_service import PortfolioService
from services.reporting.models import ReportSection, ReportTemplate, SectionType

logger = structlog.get_logger("reporting.data_fetcher")


class ReportDataFetcher:
    """Fetch all data needed for a report."""

    def __init__(self):
        self._portfolio = PortfolioService()
        self._pr_engine = PRTrendingEngine()
        self._clipping_engine = ClippingEngine()
        self._curtailment_engine = CurtailmentEngine()

    def fetch_all(
        self,
        template: ReportTemplate,
        start: datetime,
        end: datetime,
        plant_uids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Fetch data for all sections in a template."""
        data: dict[str, Any] = {
            "period_start": start,
            "period_end": end,
            "period_label": start.strftime("%B %Y"),
            "generated_at": datetime.utcnow(),
        }

        for section in template.sections:
            section_key = f"{section.type.value}_{section.title}".replace(" ", "_").lower()
            try:
                section_data = self._fetch_section(section, start, end, plant_uids)
                data[section_key] = section_data
            except Exception as e:
                logger.error("section_fetch_error", section=section.title, error=str(e))
                data[section_key] = {"error": str(e)}

        return data

    def _fetch_section(
        self,
        section: ReportSection,
        start: datetime, end: datetime,
        plant_uids: list[str] | None,
    ) -> dict[str, Any]:
        """Fetch data for a single section."""
        if section.type == SectionType.KPI_SUMMARY:
            summary = self._portfolio.get_summary(f"Custom: {start} to {end}")
            return {
                "total_capacity_mwp": summary.total_capacity_mwp,
                "total_generation_mwh": summary.total_generation_mwh,
                "fleet_pr_pct": summary.fleet_pr_pct,
                "plant_count": summary.plant_count,
            }
        
        elif section.type == SectionType.GENERATION_TABLE:
            plants = self._portfolio.get_plant_statuses(f"Custom: {start} to {end}")
            return {"plants": plants}
        
        elif section.type == SectionType.PR_CHART:
            uid = section.plant_uid or (plant_uids[0] if plant_uids else "")
            if uid:
                result = self._pr_engine.run(uid, start, end)
                return {"timeseries": result.timeseries, "summary": result.summary}
            return {}
        
        elif section.type == SectionType.WATERFALL:
            uid = section.plant_uid or (plant_uids[0] if plant_uids else "")
            # Aggregate loss data from multiple engines
            return {"losses": {}}  # Populated by waterfall engine
        
        elif section.type == SectionType.ALERT_SUMMARY:
            return {"alerts": self._portfolio.get_alert_summary()}
        
        else:
            return {}
```

### Acceptance Criteria

- [ ] Fetches data for all section types
- [ ] Uses analysis engines (not direct DB queries)
- [ ] Error handling per section (one section failure doesn't block report)
- [ ] Returns structured data ready for PDF renderer

---

## Task 5.3: Monthly Performance Report Template

**Goal:** Define the standard monthly performance report with all required sections.

**Estimated Hours:** 10

### Report Structure

```
Monthly Performance Report — January 2025
├── Cover Page (logo, title, period, confidentiality)
├── Executive Summary (4 KPIs in a row)
├── Portfolio Generation Table (all plants)
├── Fleet PR Trend (chart)
├── Plant-by-Plant Performance (per plant: PR, generation, availability)
├── Loss Waterfall (fleet-level or top 3 plants)
├── Alert Summary (critical alerts during period)
├── Appendix: Data Quality Notes
└── Appendix: Methodology
```

### Template Definition

```python
MONTHLY_REPORT = ReportTemplate(
    name="Monthly Performance Report",
    type=ReportType.MONTHLY_PERFORMANCE,
    description="Comprehensive monthly portfolio performance report",
    orientation="portrait",
    sections=[
        ReportSection(type=SectionType.COVER, title="Cover"),
        ReportSection(type=SectionType.KPI_SUMMARY, title="Executive Summary"),
        ReportSection(type=SectionType.GENERATION_TABLE, title="Portfolio Generation", page_break_before=True),
        ReportSection(type=SectionType.PR_CHART, title="Fleet PR Trend"),
        ReportSection(type=SectionType.GENERATION_CHART, title="Daily Generation"),
        ReportSection(type=SectionType.WATERFALL, title="Loss Waterfall", page_break_before=True),
        ReportSection(type=SectionType.ALERT_SUMMARY, title="Alerts & Incidents"),
        ReportSection(type=SectionType.APPENDIX, title="Data Quality", config={"type": "data_quality"}),
    ],
)
```

### Acceptance Criteria

- [ ] All sections defined with correct ordering
- [ ] Cover page with AMPYR branding
- [ ] Executive summary with 4 headline KPIs
- [ ] Plant table with PR, generation, availability columns
- [ ] Charts embedded as images

---

## Task 5.4: ExCom Summary Report Template

**Goal:** Create a condensed executive committee report — 2-3 pages max.

**Estimated Hours:** 6

### Report Structure

```
ExCom Report — January 2025
├── Cover (minimal — half page)
├── Portfolio KPIs (single row of 6 metrics)
├── Traffic Light Grid (plant × status matrix)
├── Key Issues (top 3 alerts/tickets)
└── Outlook (next month expected generation)
```

### Acceptance Criteria

- [ ] Maximum 3 pages
- [ ] Traffic light grid: green/amber/red per plant per metric (PR, gen, availability)
- [ ] Top issues with ticket status
- [ ] Clean, executive-friendly layout

---

## Task 5.5: O&M Report Template

**Goal:** Operations & Maintenance report focusing on tickets, downtime, and corrective actions.

**Estimated Hours:** 6

### Report Structure

```
O&M Report — January 2025
├── Cover
├── Availability Summary (fleet + per plant)
├── Ticket Summary (open/closed/SLA metrics)
├── Downtime Analysis (per plant, per category)
├── Corrective Actions Log
├── Preventive Maintenance Schedule
└── Recommendations
```

### Acceptance Criteria

- [ ] Integrates with Phase 4 ticket system
- [ ] Downtime tracked per plant per category
- [ ] SLA compliance percentage

---

## Task 5.6: PDF Rendering Engine

**Goal:** Build the PDF generation pipeline using ReportLab (existing dependency) with brand styling.

**Estimated Hours:** 8

### `services/reporting/pdf_renderer.py`
```python
"""
PDF rendering engine using ReportLab.

Takes: ReportTemplate + fetched data → branded PDF file.

Uses existing ReportLab dependency (already in requirements.txt).
Brand styling from styles/design_tokens.py.

DESIGN NOTES FOR EXTRACTION:
- PDF generation is a background task
- When Celery is added: run in Celery worker
- When adding web API: POST /api/reports/generate → returns download URL
"""
from __future__ import annotations

import io
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    PageBreak,
    PageTemplate,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
import structlog

from services.reporting.models import GeneratedReport, ReportSection, ReportTemplate, SectionType
from styles.design_tokens import AMPYR_TEAL, AMPYR_TEAL_LIGHT, STATUS_COLORS

logger = structlog.get_logger("reporting.pdf")

# Brand colors for ReportLab
RL_TEAL = colors.HexColor(AMPYR_TEAL)
RL_TEAL_LIGHT = colors.HexColor(AMPYR_TEAL_LIGHT)
RL_WHITE = colors.white
RL_GRAY = colors.HexColor("#F8F9FA")
RL_TEXT = colors.HexColor("#2C3E50")


class PDFRenderer:
    """Generate branded PDF reports."""

    def __init__(self, output_dir: str = "reports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._styles = self._create_styles()

    def render(
        self,
        template: ReportTemplate,
        data: dict[str, Any],
        filename: str | None = None,
    ) -> GeneratedReport:
        """Render a report template + data to PDF.
        
        Returns GeneratedReport with file_path set.
        """
        t0 = datetime.utcnow()
        
        if filename is None:
            period = data.get("period_label", "report")
            filename = f"{template.type.value}_{period}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
        
        filepath = self.output_dir / filename
        
        pagesize = landscape(A4) if template.orientation == "landscape" else A4
        
        doc = SimpleDocTemplate(
            str(filepath),
            pagesize=pagesize,
            leftMargin=2 * cm,
            rightMargin=2 * cm,
            topMargin=2.5 * cm,
            bottomMargin=2 * cm,
        )
        
        # Build flowable elements from sections
        elements = []
        
        for section in template.sections:
            if section.page_break_before and elements:
                elements.append(PageBreak())
            
            section_key = f"{section.type.value}_{section.title}".replace(" ", "_").lower()
            section_data = data.get(section_key, {})
            
            section_elements = self._render_section(section, section_data, data)
            elements.extend(section_elements)
        
        # Build PDF
        doc.build(elements, onFirstPage=self._header_footer, onLaterPages=self._header_footer)
        
        file_size = filepath.stat().st_size
        duration = (datetime.utcnow() - t0).total_seconds()
        
        return GeneratedReport(
            template_id=template.id,
            template_name=template.name,
            report_type=template.type,
            period_start=data.get("period_start", datetime.utcnow()),
            period_end=data.get("period_end", datetime.utcnow()),
            period_label=data.get("period_label", ""),
            file_path=str(filepath),
            file_size_bytes=file_size,
            status="complete",
            generation_seconds=duration,
        )

    def _render_section(
        self, section: ReportSection, section_data: dict, all_data: dict
    ) -> list:
        """Render a single section to ReportLab flowables."""
        elements = []
        
        if section.type == SectionType.COVER:
            elements.extend(self._render_cover(all_data))
        elif section.type == SectionType.KPI_SUMMARY:
            elements.extend(self._render_kpi_summary(section_data))
        elif section.type == SectionType.GENERATION_TABLE:
            elements.extend(self._render_generation_table(section_data))
        elif section.type in (SectionType.PR_CHART, SectionType.GENERATION_CHART):
            elements.extend(self._render_chart_image(section, section_data))
        elif section.type == SectionType.ALERT_SUMMARY:
            elements.extend(self._render_alert_summary(section_data))
        elif section.type == SectionType.TEXT:
            elements.append(Paragraph(section.config.get("text", ""), self._styles["body"]))
        
        return elements

    def _render_cover(self, data: dict) -> list:
        """Render cover page."""
        elements = [
            Spacer(1, 6 * cm),
            Paragraph("AMPYR Solar Portfolio Manager", self._styles["title"]),
            Spacer(1, 1 * cm),
            Paragraph(data.get("period_label", "Report"), self._styles["subtitle"]),
            Spacer(1, 2 * cm),
            Paragraph(f"Generated: {data.get('generated_at', datetime.utcnow()).strftime('%d %B %Y %H:%M')}", self._styles["body_center"]),
            Spacer(1, 1 * cm),
            Paragraph("CONFIDENTIAL", self._styles["confidential"]),
            PageBreak(),
        ]
        return elements

    def _render_kpi_summary(self, data: dict) -> list:
        """Render KPI summary as a table row."""
        elements = [
            Paragraph("Executive Summary", self._styles["heading"]),
            Spacer(1, 0.5 * cm),
        ]
        
        kpi_data = [
            ["Total Capacity", "Generation", "Fleet PR", "Plants"],
            [
                f"{data.get('total_capacity_mwp', 0):.1f} MWp",
                f"{data.get('total_generation_mwh', 0):.1f} MWh",
                f"{data.get('fleet_pr_pct', 0):.1f}%",
                str(data.get('plant_count', 0)),
            ],
        ]
        
        table = Table(kpi_data, colWidths=[4 * cm] * 4)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), RL_TEAL),
            ("TEXTCOLOR", (0, 0), (-1, 0), RL_WHITE),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("FONTSIZE", (0, 1), (-1, 1), 14),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E8E8E8")),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        elements.append(table)
        return elements

    def _render_generation_table(self, data: dict) -> list:
        """Render plant generation table."""
        elements = [
            Paragraph("Portfolio Generation", self._styles["heading"]),
            Spacer(1, 0.5 * cm),
        ]
        
        plants = data.get("plants", [])
        if not plants:
            elements.append(Paragraph("No plant data available.", self._styles["body"]))
            return elements
        
        header = ["Plant", "Status", "PR (%)", "Generation (MWh)", "Alerts"]
        rows = [header]
        for p in plants:
            rows.append([
                p.get("name", ""),
                p.get("status", "").title(),
                f"{p.get('pr', 0):.1f}",
                f"{p.get('generation_mwh', 0):.1f}",
                str(p.get("alerts", 0)),
            ])
        
        table = Table(rows, colWidths=[5 * cm, 2.5 * cm, 2.5 * cm, 3.5 * cm, 2 * cm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), RL_TEAL),
            ("TEXTCOLOR", (0, 0), (-1, 0), RL_WHITE),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [RL_WHITE, RL_GRAY]),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E8E8E8")),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        elements.append(table)
        return elements

    def _render_chart_image(self, section: ReportSection, data: dict) -> list:
        """Render a chart as an embedded image."""
        elements = [
            Paragraph(section.title, self._styles["heading"]),
            Spacer(1, 0.5 * cm),
        ]
        
        image_path = data.get("image_path")
        if image_path and os.path.exists(image_path):
            elements.append(Image(image_path, width=16 * cm, height=8 * cm))
        else:
            elements.append(Paragraph("Chart not available.", self._styles["body"]))
        
        return elements

    def _render_alert_summary(self, data: dict) -> list:
        elements = [
            Paragraph("Alerts & Incidents", self._styles["heading"]),
            Spacer(1, 0.5 * cm),
        ]
        alerts = data.get("alerts", [])
        if not alerts:
            elements.append(Paragraph("No alerts during this period.", self._styles["body"]))
        else:
            for alert in alerts:
                icon = "●" if alert["severity"] == "critical" else "▲" if alert["severity"] == "warning" else "○"
                elements.append(Paragraph(
                    f"{icon} {alert.get('count', 0)} × {alert.get('type', '')}",
                    self._styles["body"],
                ))
        return elements

    def _header_footer(self, canvas, doc):
        """Add header and footer to every page."""
        canvas.saveState()
        # Header line
        canvas.setStrokeColor(RL_TEAL)
        canvas.setLineWidth(2)
        canvas.line(2 * cm, A4[1] - 1.5 * cm, A4[0] - 2 * cm, A4[1] - 1.5 * cm)
        
        # Footer
        canvas.setFillColor(colors.HexColor("#7F8C8D"))
        canvas.setFont("Helvetica", 8)
        canvas.drawString(2 * cm, 1 * cm, "AMPYR Solar Portfolio Manager — Confidential")
        canvas.drawRightString(A4[0] - 2 * cm, 1 * cm, f"Page {doc.page}")
        canvas.restoreState()

    def _create_styles(self) -> dict:
        """Create brand-styled paragraph styles."""
        base = getSampleStyleSheet()
        return {
            "title": ParagraphStyle(
                "BrandTitle", parent=base["Title"],
                fontSize=28, textColor=RL_TEAL, alignment=TA_CENTER,
            ),
            "subtitle": ParagraphStyle(
                "BrandSubtitle", parent=base["Title"],
                fontSize=18, textColor=RL_TEXT, alignment=TA_CENTER,
            ),
            "heading": ParagraphStyle(
                "BrandHeading", parent=base["Heading1"],
                fontSize=16, textColor=RL_TEAL, spaceAfter=6,
            ),
            "body": ParagraphStyle(
                "BrandBody", parent=base["Normal"],
                fontSize=10, textColor=RL_TEXT, leading=14,
            ),
            "body_center": ParagraphStyle(
                "BrandBodyCenter", parent=base["Normal"],
                fontSize=10, textColor=RL_TEXT, alignment=TA_CENTER,
            ),
            "confidential": ParagraphStyle(
                "Confidential", parent=base["Normal"],
                fontSize=9, textColor=colors.HexColor("#95A5A6"),
                alignment=TA_CENTER,
            ),
        }
```

### Acceptance Criteria

- [ ] PDF generated with brand header/footer on every page
- [ ] Cover page with title, period, confidentiality notice
- [ ] KPI summary table rendered
- [ ] Plant generation table with alternating row colors
- [ ] Charts embedded as images
- [ ] Output to `reports/` directory

---

## Task 5.7: Chart-to-Image Export

**Goal:** Export Plotly charts as PNG images for PDF embedding.

**Estimated Hours:** 4

### Implementation

```python
# services/reporting/chart_exporter.py
"""Export Plotly charts to PNG for PDF embedding using kaleido."""
import plotly.graph_objects as go
from pathlib import Path


def chart_to_png(
    fig: go.Figure,
    filepath: str | Path,
    width: int = 1200,
    height: int = 600,
    scale: int = 2,
) -> str:
    """Export a Plotly figure to PNG.
    
    Requires kaleido (already in requirements.txt).
    """
    fig.write_image(str(filepath), width=width, height=height, scale=scale, format="png")
    return str(filepath)
```

### Acceptance Criteria

- [ ] Plotly charts export to PNG at 2x resolution
- [ ] Works with kaleido (already a dependency)
- [ ] Temporary images cleaned up after PDF generation

---

## Task 5.8: Report Builder UI

**Goal:** Streamlit interface for selecting template, time range, plants, and generating reports.

**Estimated Hours:** 8

### Layout

```
┌──────────────────────────────────────────────────────────────┐
│ 📄 Report Builder                                           │
├──────────────────────────────────────────────────────────────┤
│ Template: [Monthly Performance ▼]                           │
│ Period:   [January 2025 ▼]                                  │
│ Plants:   [✅ All] or [Select plants...]                    │
│                                                              │
│ Sections:                                                    │
│ ☑ Cover Page                                                │
│ ☑ Executive Summary                                         │
│ ☑ Generation Table                                          │
│ ☑ PR Trend Chart                                            │
│ ☑ Loss Waterfall                                            │
│ ☑ Alert Summary                                             │
│ ☐ Appendix                                                  │
│                                                              │
│ [Preview 👁️]  [Generate PDF 📄]                              │
│                                                              │
│ ┌──────────────────────────────────────────┐                │
│ │ Preview area (last page or summary)     │                │
│ └──────────────────────────────────────────┘                │
└──────────────────────────────────────────────────────────────┘
```

### Acceptance Criteria

- [ ] Template selector with descriptions
- [ ] Month/year picker for period
- [ ] Section toggle (include/exclude)
- [ ] PDF download button
- [ ] Generation progress indicator

---

## Task 5.9: Report Library & History

**Goal:** Store generated reports and provide a library view.

**Estimated Hours:** 4

### Database Table

```sql
CREATE TABLE IF NOT EXISTS generated_reports (
    id              VARCHAR PRIMARY KEY,
    template_id     VARCHAR,
    template_name   VARCHAR,
    report_type     VARCHAR,
    period_start    TIMESTAMP,
    period_end      TIMESTAMP,
    period_label    VARCHAR,
    file_path       VARCHAR,
    file_size_bytes INTEGER,
    page_count      INTEGER,
    status          VARCHAR DEFAULT 'complete',
    generated_by    VARCHAR,
    generated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    generation_seconds DOUBLE
);
```

### Acceptance Criteria

- [ ] Past reports listed with download links
- [ ] Filter by type, period, status
- [ ] Delete old reports
- [ ] File size and page count displayed

---

## Task 5.10: Scheduled Report Generation

**Goal:** Design scheduled generation (monthly auto-generation). Runs synchronously now, Celery later.

**Estimated Hours:** 4

### Schedule Config

```python
REPORT_SCHEDULES = {
    "monthly_performance": {
        "template": "monthly_performance",
        "cron": "0 8 1 * *",     # 1st of each month at 8 AM
        "description": "Auto-generate monthly performance report",
    },
    "excom_monthly": {
        "template": "excom_summary",
        "cron": "0 8 2 * *",     # 2nd of each month at 8 AM
        "description": "Auto-generate ExCom summary",
    },
}
```

### Acceptance Criteria

- [ ] Schedule definitions ready for Celery Beat
- [ ] Manual "Generate Now" button works
- [ ] Generated reports auto-saved to library

---

## Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| PDF generation slow for large portfolios | Medium | Medium | Pre-cache chart images; progress bar in UI |
| ReportLab font issues on Linux/Docker | Medium | Medium | Bundle Inter font; fallback to Helvetica |
| kaleido chart export failures | Medium | Low | Catch errors; skip chart and add placeholder text |
| Monthly reporting migration breaks existing workflow | High | Medium | Keep `Monthly reporting/` working in parallel during migration |
| Report files accumulate disk space | Low | Medium | Auto-cleanup reports older than 6 months |

---

## Definition of Done

- [ ] 3 report templates defined (Monthly, ExCom, O&M)
- [ ] PDF renderer generates branded output
- [ ] Charts embedded as high-res images
- [ ] Report builder UI with template selection and preview
- [ ] Report library stores and lists generated reports
- [ ] Monthly report matches or exceeds existing `Monthly reporting/` output
- [ ] Schedule definitions ready for Celery integration
- [ ] 10+ unit tests for data fetcher and renderer
- [ ] PDF output reviewed for brand compliance
