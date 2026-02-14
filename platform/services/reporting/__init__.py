"""Reporting engine package.

Template-driven report generation with PDF output and brand styling.
Pipeline: Template → DataFetcher → ChartExporter → PDFRenderer → ReportLibrary.
"""
from __future__ import annotations

from services.reporting.models import (
    GeneratedReport,
    ReportSection,
    ReportTemplate,
    ReportType,
    SectionType,
)
from services.reporting.templates import ALL_TEMPLATES, get_template

__all__ = [
    "GeneratedReport",
    "ReportSection",
    "ReportTemplate",
    "ReportType",
    "SectionType",
    "ALL_TEMPLATES",
    "get_template",
]
