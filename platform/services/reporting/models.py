"""Report template and output models.

A report template defines:
- Sections (cover, KPI summary, charts, tables, appendix)
- Data requirements per section (which metrics, which plants)
- Layout preferences (orientation, margins, brand styling)

A generated report links a template + time range → PDF output.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ReportType(str, Enum):
    """Available report types."""

    MONTHLY_PERFORMANCE = "monthly_performance"
    EXCOM_SUMMARY = "excom_summary"
    OM_REPORT = "om_report"
    CUSTOM = "custom"


class SectionType(str, Enum):
    """Available section types within a report."""

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
    orientation: str = "portrait"  # "portrait" or "landscape"
    paper_size: str = "A4"

    # Brand
    include_cover: bool = True
    include_header: bool = True
    include_footer: bool = True
    logo_path: str = ""

    # Metadata
    created_by: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


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
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    generation_seconds: float = 0.0
