"""Tests for the ExportService (services/export_service.py).

All tests operate on in-memory DataFrames — no database or filesystem
access required.
"""
import csv
import io
import json

import pandas as pd
import pytest

from solar_platform.services.export import ExportFormat, ExportService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def svc(tmp_path):
    """ExportService with export dir pointing to a temp directory."""
    service = ExportService.__new__(ExportService)
    service.export_dir = tmp_path / "exports"
    service.export_dir.mkdir()
    return service


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

class TestCsvExport:
    """Tests for CSV export."""

    def test_produces_valid_csv(self, svc, sample_dataframe):
        data = svc.export_dataframe(sample_dataframe, "test", ExportFormat.CSV)
        text = data.decode()
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        assert rows[0] == ["Site", "Energy_kWh", "PR", "Date"]  # header
        assert len(rows) == 4  # header + 3 data rows

    def test_csv_contains_data(self, svc, sample_dataframe):
        data = svc.export_dataframe(sample_dataframe, "test", ExportFormat.CSV)
        text = data.decode()
        assert "Plant A" in text
        assert "3000" in text

    def test_empty_dataframe_produces_header_only(self, svc):
        df = pd.DataFrame({"A": [], "B": []})
        data = svc.export_dataframe(df, "empty", ExportFormat.CSV)
        text = data.decode().strip()
        lines = text.split("\n")
        assert len(lines) == 1  # header only


# ---------------------------------------------------------------------------
# Excel export
# ---------------------------------------------------------------------------

class TestExcelExport:
    """Tests for Excel (xlsx) export."""

    def test_produces_bytes(self, svc, sample_dataframe):
        data = svc.export_dataframe(sample_dataframe, "test", ExportFormat.EXCEL)
        assert isinstance(data, bytes)
        assert len(data) > 0

    def test_excel_is_valid_xlsx(self, svc, sample_dataframe):
        """XLSX files start with the PK zip magic bytes."""
        data = svc.export_dataframe(sample_dataframe, "test", ExportFormat.EXCEL)
        assert data[:2] == b"PK"

    def test_empty_dataframe_produces_valid_excel(self, svc):
        df = pd.DataFrame({"X": []})
        data = svc.export_dataframe(df, "empty", ExportFormat.EXCEL)
        assert isinstance(data, bytes)
        assert data[:2] == b"PK"


# ---------------------------------------------------------------------------
# JSON export
# ---------------------------------------------------------------------------

class TestJsonExport:
    """Tests for JSON export."""

    def test_produces_valid_json(self, svc, sample_dataframe):
        data = svc.export_dataframe(sample_dataframe, "test", ExportFormat.JSON)
        records = json.loads(data.decode())
        assert isinstance(records, list)
        assert len(records) == 3

    def test_json_contains_columns(self, svc, sample_dataframe):
        data = svc.export_dataframe(sample_dataframe, "test", ExportFormat.JSON)
        records = json.loads(data.decode())
        assert "Site" in records[0]
        assert "Energy_kWh" in records[0]


# ---------------------------------------------------------------------------
# Unsupported format
# ---------------------------------------------------------------------------

class TestUnsupportedFormat:
    def test_raises_value_error(self, svc, sample_dataframe):
        with pytest.raises(ValueError, match="Unsupported export format"):
            svc.export_dataframe(sample_dataframe, "test", "pdf_v99")


# ---------------------------------------------------------------------------
# Multiple sheets
# ---------------------------------------------------------------------------

class TestMultipleSheets:
    """Tests for export_multiple_sheets()."""

    def test_produces_valid_excel(self, svc, sample_dataframe):
        sheets = {
            "Sheet1": sample_dataframe,
            "Sheet2": sample_dataframe.head(1),
        }
        data = svc.export_multiple_sheets(sheets, "multi")
        assert isinstance(data, bytes)
        assert data[:2] == b"PK"

    def test_empty_sheets_dict_raises(self, svc):
        """An Excel file with zero sheets is invalid (openpyxl requires >= 1)."""
        with pytest.raises(IndexError):
            svc.export_multiple_sheets({}, "empty")


# ---------------------------------------------------------------------------
# export_to_file
# ---------------------------------------------------------------------------

class TestExportToFile:
    """Tests for export_to_file()."""

    def test_creates_csv_file(self, svc, sample_dataframe):
        path = svc.export_to_file(sample_dataframe, "out", ExportFormat.CSV)
        assert path.exists()
        assert path.suffix == ".csv"
        content = path.read_text()
        assert "Plant A" in content

    def test_creates_xlsx_file(self, svc, sample_dataframe):
        path = svc.export_to_file(sample_dataframe, "out", ExportFormat.EXCEL)
        assert path.exists()
        assert path.suffix == ".xlsx"
        assert path.stat().st_size > 0
