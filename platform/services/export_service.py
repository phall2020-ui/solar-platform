"""
Data Export Service for Solar Portfolio Manager.
Provides export functionality for various data formats and automated report generation.
"""
import io
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


class ExportFormat:
    """Supported export formats."""
    CSV = "csv"
    EXCEL = "xlsx"
    JSON = "json"
    PDF = "pdf"
    PARQUET = "parquet"


class ExportService:
    """Service for exporting data in various formats."""

    def __init__(self) -> None:
        """Initialize export service."""
        self.export_dir = Path.home() / ".solar_toolkit" / "exports"
        self.export_dir.mkdir(parents=True, exist_ok=True)
        logger.info("ExportService initialized, export_dir=%s", self.export_dir)

    def export_dataframe(self, df: pd.DataFrame, filename: str,
                        format: str = ExportFormat.CSV,
                        **kwargs) -> bytes:
        """
        Export a pandas DataFrame to the specified format.

        Args:
            df: DataFrame to export
            filename: Output filename (without extension)
            format: Export format (csv, xlsx, json, parquet)
            **kwargs: Additional format-specific options

        Returns:
            Bytes object containing the exported data
        """
        buffer = io.BytesIO()

        if format == ExportFormat.CSV:
            logger.info("Exporting dataframe as CSV, rows=%d, filename=%s", len(df), filename)
            csv_data = df.to_csv(index=kwargs.get('index', False))
            buffer.write(csv_data.encode())

        elif format == ExportFormat.EXCEL:
            logger.info("Exporting dataframe as Excel, rows=%d, filename=%s", len(df), filename)
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name=kwargs.get('sheet_name', 'Data'),
                           index=kwargs.get('index', False))

        elif format == ExportFormat.JSON:
            logger.info("Exporting dataframe as JSON, rows=%d, filename=%s", len(df), filename)
            json_data = df.to_json(orient=kwargs.get('orient', 'records'),
                                  date_format='iso', indent=2)
            buffer.write(json_data.encode())

        elif format == ExportFormat.PARQUET:
            logger.info("Exporting dataframe as Parquet, rows=%d, filename=%s", len(df), filename)
            df.to_parquet(buffer, index=kwargs.get('index', False))

        else:
            logger.error("Unsupported export format: %s", format)
            raise ValueError(f"Unsupported export format: {format}")

        buffer.seek(0)
        return buffer.getvalue()

    def export_to_file(self, df: pd.DataFrame, filename: str,
                       format: str = ExportFormat.CSV,
                       **kwargs) -> Path:
        """
        Export DataFrame to a file in the exports directory.

        Returns:
            Path to the exported file
        """
        extensions = {
            ExportFormat.CSV: '.csv',
            ExportFormat.EXCEL: '.xlsx',
            ExportFormat.JSON: '.json',
            ExportFormat.PARQUET: '.parquet',
        }

        ext = extensions.get(format, '.csv')
        filepath = self.export_dir / f"{filename}{ext}"

        data = self.export_dataframe(df, filename, format, **kwargs)

        with open(filepath, 'wb') as f:
            f.write(data)

        logger.info("Exported to file: %s (%d bytes)", filepath, len(data))
        return filepath

    def export_query_result(self, db_path: Path, query: str,
                           filename: str, format: str = ExportFormat.CSV,
                           **kwargs) -> bytes:
        """
        Export SQL query results directly.

        Args:
            db_path: Path to SQLite database
            query: SQL query to execute
            filename: Output filename
            format: Export format
            **kwargs: Additional options

        Returns:
            Bytes object containing exported data
        """
        conn = sqlite3.connect(str(db_path))
        df = pd.read_sql_query(query, conn)
        conn.close()

        return self.export_dataframe(df, filename, format, **kwargs)

    def export_multiple_sheets(self, data_dict: dict[str, pd.DataFrame],
                              filename: str) -> bytes:
        """
        Export multiple DataFrames to separate sheets in an Excel file.

        Args:
            data_dict: Dictionary mapping sheet names to DataFrames
            filename: Output filename

        Returns:
            Bytes object containing Excel file
        """
        buffer = io.BytesIO()

        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            for sheet_name, df in data_dict.items():
                df.to_excel(writer, sheet_name=sheet_name, index=False)

        buffer.seek(0)
        return buffer.getvalue()

    def create_export_package(self, exports: list[dict[str, Any]],
                             package_name: str) -> bytes:
        """
        Create a zip package containing multiple exports.

        Args:
            exports: List of export definitions with 'name', 'data', 'format'
            package_name: Name of the zip package

        Returns:
            Bytes object containing zip file
        """
        import zipfile

        buffer = io.BytesIO()

        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for export in exports:
                name = export['name']
                data = export['data']
                format = export.get('format', ExportFormat.CSV)

                if isinstance(data, pd.DataFrame):
                    file_data = self.export_dataframe(data, name, format)
                else:
                    file_data = data.encode() if isinstance(data, str) else data

                extensions = {
                    ExportFormat.CSV: '.csv',
                    ExportFormat.EXCEL: '.xlsx',
                    ExportFormat.JSON: '.json',
                    ExportFormat.PARQUET: '.parquet',
                }
                ext = extensions.get(format, '.txt')

                zf.writestr(f"{name}{ext}", file_data)

        buffer.seek(0)
        return buffer.getvalue()

    def export_analysis_results(self, analysis_name: str,
                               results: dict[str, Any],
                               format: str = ExportFormat.EXCEL) -> bytes:
        """
        Export analysis results in a structured format.

        Args:
            analysis_name: Name of the analysis
            results: Dictionary containing analysis results
            format: Export format

        Returns:
            Bytes object containing exported data
        """
        logger.info("Exporting analysis results: %s, format=%s", analysis_name, format)
        if format == ExportFormat.EXCEL:
            # Create multi-sheet Excel with summary and detailed data
            sheets = {}

            # Summary sheet
            summary_data = {
                'Analysis': [analysis_name],
                'Generated': [datetime.now().isoformat()],
                'Description': [results.get('description', '')],
            }
            sheets['Summary'] = pd.DataFrame(summary_data)

            # Add data sheets
            for key, value in results.items():
                if isinstance(value, pd.DataFrame):
                    # Clean sheet name
                    sheet_name = str(key).replace('/', '_')[:31]
                    sheets[sheet_name] = value
                elif isinstance(value, (list, dict)) and key != 'description':
                    try:
                        df = pd.DataFrame(value)
                        sheet_name = str(key).replace('/', '_')[:31]
                        sheets[sheet_name] = df
                    except Exception:
                        pass

            return self.export_multiple_sheets(sheets, analysis_name)

        elif format == ExportFormat.JSON:
            # Convert DataFrames to records for JSON
            export_data = {'analysis': analysis_name, 'timestamp': datetime.now().isoformat()}

            for key, value in results.items():
                if isinstance(value, pd.DataFrame):
                    export_data[key] = value.to_dict('records')
                else:
                    export_data[key] = value

            json_str = json.dumps(export_data, indent=2, default=str)
            return json_str.encode()

        else:
            logger.error("Unsupported format for analysis export: %s", format)
            raise ValueError(f"Format {format} not supported for analysis export")

    def get_export_metadata(self, filepath: Path) -> dict[str, Any] | None:
        """Get metadata about an exported file."""
        if not filepath.exists():
            return None

        stat = filepath.stat()
        return {
            'filename': filepath.name,
            'size_bytes': stat.st_size,
            'created': datetime.fromtimestamp(stat.st_ctime).isoformat(),
            'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
            'format': filepath.suffix.lstrip('.'),
        }

    def list_exports(self) -> list[dict[str, Any]]:
        """List all exports in the export directory."""
        exports = []

        for filepath in self.export_dir.iterdir():
            if filepath.is_file():
                metadata = self.get_export_metadata(filepath)
                if metadata:
                    exports.append(metadata)

        return sorted(exports, key=lambda x: x['modified'], reverse=True)

    def cleanup_old_exports(self, days: int = 30) -> int:
        """Delete exports older than specified days."""
        import time

        cutoff_time = time.time() - (days * 86400)
        deleted = 0

        for filepath in self.export_dir.iterdir():
            if filepath.is_file() and filepath.stat().st_mtime < cutoff_time:
                filepath.unlink()
                deleted += 1

        return deleted


# Template exports for common use cases
class TemplateExports:
    """Pre-defined export templates for common reports."""

    @staticmethod
    def monthly_performance_report(db_path: Path, year: int, month: int) -> dict[str, pd.DataFrame]:
        """Generate monthly performance report data."""
        conn = sqlite3.connect(str(db_path))

        sheets = {}

        # Energy production
        query = f"""
            SELECT plant_name, SUM(energy_kwh) as total_energy
            FROM energy_data
            WHERE year = {year} AND month = {month}
            GROUP BY plant_name
        """
        try:
            sheets['Energy Production'] = pd.read_sql_query(query, conn)
        except Exception:
            pass

        # Performance metrics
        query = f"""
            SELECT plant_name, AVG(pr) as avg_pr, AVG(availability) as avg_availability
            FROM performance_metrics
            WHERE year = {year} AND month = {month}
            GROUP BY plant_name
        """
        try:
            sheets['Performance'] = pd.read_sql_query(query, conn)
        except Exception:
            pass

        conn.close()
        return sheets

    @staticmethod
    def plant_summary_report(db_path: Path, plant_id: str) -> dict[str, pd.DataFrame]:
        """Generate plant summary report data."""
        conn = sqlite3.connect(str(db_path))

        sheets = {}

        # Plant details
        try:
            sheets['Plant Info'] = pd.read_sql_query(
                "SELECT * FROM plants WHERE plant_id = ?",
                conn,
                params=(plant_id,),
            )
        except Exception:
            pass

        # Recent performance
        try:
            sheets['Recent Performance'] = pd.read_sql_query(
                """
                SELECT date, energy_kwh, pr, availability
                FROM daily_performance
                WHERE plant_id = ?
                ORDER BY date DESC
                LIMIT 90
                """,
                conn,
                params=(plant_id,),
            )
        except Exception:
            pass

        conn.close()
        return sheets
