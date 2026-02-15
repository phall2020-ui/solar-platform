"""
Incremental ETL with data validation.
Implements incremental data loading with pydantic validation and data quality checks.
"""
from datetime import datetime
from enum import Enum
from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from solar_platform.db.utils import get_connection


class DataQualityStatus(Enum):
    """Data quality check status."""
    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"


class SolarDataSchema(BaseModel):
    """Schema validation for solar data records."""
    model_config = ConfigDict(extra='allow')
    
    Site: str = Field(..., min_length=1, description="Site name/ID")
    Date: str = Field(..., description="Date string")
    PR: float | None = Field(None, ge=0, le=2, description="Performance ratio (0-2)")
    Irradiance_kWh_m2: float | None = Field(None, ge=0, description="Irradiance (kWh/m²)")
    Energy_MWh: float | None = Field(None, ge=0, description="Energy production (MWh)")
    Availability_percent: float | None = Field(None, ge=0, le=100, description="Availability (0-100%)")
    
    @field_validator('Date')
    @classmethod
    def validate_date(cls, v):
        """Validate date format."""
        try:
            # Try common date formats
            for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%Y%m%d']:
                try:
                    datetime.strptime(v, fmt)
                    return v
                except ValueError:
                    continue
            raise ValueError(f"Invalid date format: {v}")
        except Exception as e:
            raise ValueError(f"Date validation failed: {e}")


class DataQualityReport:
    """Data quality validation report."""
    
    def __init__(self):
        self.checks: list[dict[str, Any]] = []
        self.overall_status = DataQualityStatus.PASSED
        
    def add_check(self, name: str, status: DataQualityStatus, message: str, details: dict | None = None):
        """Add a validation check result."""
        self.checks.append({
            "name": name,
            "status": status.value,
            "message": message,
            "details": details or {},
            "timestamp": datetime.now().isoformat()
        })
        
        # Update overall status (FAILED > WARNING > PASSED)
        if status == DataQualityStatus.FAILED:
            self.overall_status = DataQualityStatus.FAILED
        elif status == DataQualityStatus.WARNING and self.overall_status != DataQualityStatus.FAILED:
            self.overall_status = DataQualityStatus.WARNING
    
    def is_passed(self) -> bool:
        """Check if all validations passed (no failures)."""
        return self.overall_status != DataQualityStatus.FAILED
    
    def to_dict(self) -> dict:
        """Convert report to dictionary."""
        return {
            "overall_status": self.overall_status.value,
            "checks": self.checks,
            "total_checks": len(self.checks),
            "passed": sum(1 for c in self.checks if c["status"] == "passed"),
            "warnings": sum(1 for c in self.checks if c["status"] == "warning"),
            "failed": sum(1 for c in self.checks if c["status"] == "failed"),
        }


class IncrementalETL:
    """Incremental ETL pipeline with validation."""
    
    def __init__(self, db_path: str):
        """
        Initialize incremental ETL.
        
        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path
        self.metadata_table = "_etl_metadata"
        self._ensure_metadata_table()
    
    def _ensure_metadata_table(self):
        """Create metadata table if it doesn't exist."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.metadata_table} (
                    table_name TEXT PRIMARY KEY,
                    last_ingestion_timestamp TEXT,
                    last_max_date TEXT,
                    total_rows INTEGER,
                    last_validation_status TEXT,
                    last_validation_report TEXT
                )
            """)
            conn.commit()
    
    def get_last_ingestion_info(self, table_name: str) -> dict[str, Any] | None:
        """Get last ingestion metadata for a table."""
        with get_connection(self.db_path, read_only=True) as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT * FROM {self.metadata_table} WHERE table_name = ?",
                (table_name,)
            )
            row = cursor.fetchone()
        
        if row:
            return {
                "table_name": row[0],
                "last_ingestion_timestamp": row[1],
                "last_max_date": row[2],
                "total_rows": row[3],
                "last_validation_status": row[4],
                "last_validation_report": row[5]
            }
        return None
    
    def update_ingestion_metadata(
        self,
        table_name: str,
        max_date: str | None,
        total_rows: int,
        validation_status: str,
        validation_report: str
    ):
        """Update ingestion metadata."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                INSERT OR REPLACE INTO {self.metadata_table}
                (table_name, last_ingestion_timestamp, last_max_date, total_rows, 
                 last_validation_status, last_validation_report)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    table_name,
                    datetime.now().isoformat(),
                    max_date,
                    total_rows,
                    validation_status,
                    validation_report
                )
            )
            conn.commit()
    
    def validate_dataframe(self, df: pd.DataFrame, sample_size: int = 1000) -> DataQualityReport:
        """
        Validate dataframe with pydantic schema and quality checks.
        
        Args:
            df: DataFrame to validate
            sample_size: Number of rows to validate with pydantic (for performance)
            
        Returns:
            DataQualityReport with validation results
        """
        report = DataQualityReport()
        
        # Check 1: Empty dataframe
        if df.empty:
            report.add_check(
                "empty_check",
                DataQualityStatus.FAILED,
                "DataFrame is empty",
                {"row_count": 0}
            )
            return report
        
        report.add_check(
            "empty_check",
            DataQualityStatus.PASSED,
            f"DataFrame has {len(df)} rows",
            {"row_count": len(df)}
        )
        
        # Check 2: Required columns
        required_cols = ['Site', 'Date']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            report.add_check(
                "required_columns",
                DataQualityStatus.FAILED,
                f"Missing required columns: {missing_cols}",
                {"missing": missing_cols, "available": list(df.columns)}
            )
            return report
        
        report.add_check(
            "required_columns",
            DataQualityStatus.PASSED,
            "All required columns present",
            {"columns": list(df.columns)}
        )
        
        # Check 3: Null values in key columns
        null_counts = {}
        for col in required_cols:
            null_count = df[col].isna().sum()
            null_counts[col] = int(null_count)
            if null_count > 0:
                pct = (null_count / len(df)) * 100
                status = DataQualityStatus.FAILED if pct > 10 else DataQualityStatus.WARNING
                report.add_check(
                    f"nulls_{col}",
                    status,
                    f"{null_count} null values in {col} ({pct:.1f}%)",
                    {"null_count": null_count, "percentage": pct}
                )
        
        if not any(null_counts.values()):
            report.add_check(
                "null_check",
                DataQualityStatus.PASSED,
                "No null values in required columns"
            )
        
        # Check 4: Duplicate rows
        duplicate_count = df.duplicated(subset=['Site', 'Date']).sum()
        if duplicate_count > 0:
            pct = (duplicate_count / len(df)) * 100
            status = DataQualityStatus.WARNING if pct < 5 else DataQualityStatus.FAILED
            report.add_check(
                "duplicates",
                status,
                f"{duplicate_count} duplicate Site/Date combinations ({pct:.1f}%)",
                {"duplicate_count": int(duplicate_count), "percentage": pct}
            )
        else:
            report.add_check(
                "duplicates",
                DataQualityStatus.PASSED,
                "No duplicate Site/Date combinations"
            )
        
        # Check 5: Date range validation
        try:
            dates = pd.to_datetime(df['Date'], errors='coerce')
            invalid_dates = dates.isna().sum()
            if invalid_dates > 0:
                pct = (invalid_dates / len(df)) * 100
                report.add_check(
                    "date_format",
                    DataQualityStatus.WARNING,
                    f"{invalid_dates} rows with invalid dates ({pct:.1f}%)",
                    {"invalid_count": int(invalid_dates)}
                )
            else:
                min_date = dates.min()
                max_date = dates.max()
                report.add_check(
                    "date_range",
                    DataQualityStatus.PASSED,
                    f"Date range: {min_date.date()} to {max_date.date()}",
                    {"min_date": str(min_date.date()), "max_date": str(max_date.date())}
                )
        except Exception as e:
            report.add_check(
                "date_validation",
                DataQualityStatus.FAILED,
                f"Date validation error: {e}"
            )
        
        # Check 6: Schema validation (sample for performance)
        sample_df = df.head(min(sample_size, len(df)))
        validation_errors = []
        
        for idx, row in sample_df.iterrows():
            try:
                SolarDataSchema(**row.to_dict())
            except ValidationError as e:
                validation_errors.append({"row": int(idx), "errors": str(e)})
                if len(validation_errors) >= 10:  # Limit error collection
                    break
        
        if validation_errors:
            report.add_check(
                "schema_validation",
                DataQualityStatus.WARNING,
                f"{len(validation_errors)} rows failed schema validation (sampled {len(sample_df)} rows)",
                {"error_count": len(validation_errors), "sample_errors": validation_errors[:3]}
            )
        else:
            report.add_check(
                "schema_validation",
                DataQualityStatus.PASSED,
                f"Schema validation passed for {len(sample_df)} sampled rows"
            )
        
        # Check 7: Numeric range checks for key metrics
        numeric_cols = {
            'PR': (0, 2),
            'Irradiance_kWh_m2': (0, 10),
            'Energy_MWh': (0, None),
            'Availability_percent': (0, 100)
        }
        
        for col, (min_val, max_val) in numeric_cols.items():
            if col in df.columns:
                out_of_range = 0
                if min_val is not None:
                    out_of_range += (df[col] < min_val).sum()
                if max_val is not None:
                    out_of_range += (df[col] > max_val).sum()
                
                if out_of_range > 0:
                    pct = (out_of_range / len(df)) * 100
                    status = DataQualityStatus.WARNING if pct < 5 else DataQualityStatus.FAILED
                    report.add_check(
                        f"range_{col}",
                        status,
                        f"{out_of_range} values out of range in {col} ({pct:.1f}%)",
                        {"out_of_range_count": int(out_of_range)}
                    )
        
        return report
    
    def load_incremental(
        self,
        source_df: pd.DataFrame,
        table_name: str,
        date_column: str = 'Date',
        validate: bool = True,
        block_on_failure: bool = True
    ) -> tuple[bool, DataQualityReport]:
        """
        Load data incrementally with validation.
        
        Args:
            source_df: Source dataframe to load
            table_name: Target table name
            date_column: Column to use for incremental logic
            validate: Whether to run validation
            block_on_failure: Whether to block load on validation failure
            
        Returns:
            Tuple of (success, validation_report)
        """
        # Validate first if requested
        report = DataQualityReport()
        if validate:
            report = self.validate_dataframe(source_df)
            if not report.is_passed() and block_on_failure:
                # Don't load if validation failed
                return False, report
        
        # Get last ingestion info
        last_info = self.get_last_ingestion_info(table_name)
        
        # Filter for incremental load
        if last_info and last_info['last_max_date']:
            try:
                source_dates = pd.to_datetime(source_df[date_column], errors='coerce')
                last_max = pd.to_datetime(last_info['last_max_date'])
                new_data = source_df[source_dates > last_max].copy()
                
                if new_data.empty:
                    report.add_check(
                        "incremental_load",
                        DataQualityStatus.PASSED,
                        "No new data to load (all dates <= last ingestion)",
                        {"last_max_date": last_info['last_max_date']}
                    )
                    return True, report
                
                df_to_load = new_data
                load_mode = 'append'
                report.add_check(
                    "incremental_load",
                    DataQualityStatus.PASSED,
                    f"Loading {len(new_data)} new rows (dates > {last_info['last_max_date']})",
                    {"new_rows": len(new_data), "last_max_date": last_info['last_max_date']}
                )
            except Exception as e:
                # Fall back to full load on error
                df_to_load = source_df
                load_mode = 'replace'
                report.add_check(
                    "incremental_load",
                    DataQualityStatus.WARNING,
                    f"Incremental load failed, doing full replace: {e}"
                )
        else:
            # First load
            df_to_load = source_df
            load_mode = 'replace'
            report.add_check(
                "incremental_load",
                DataQualityStatus.PASSED,
                f"First load: {len(source_df)} rows"
            )
        
        # Perform the load
        try:
            with get_connection(self.db_path) as conn:
                df_to_load.to_sql(table_name, conn, if_exists=load_mode, index=False)
            
            # Update metadata
            max_date = None
            try:
                dates = pd.to_datetime(source_df[date_column], errors='coerce')
                max_date = str(dates.max().date())
            except Exception:
                pass
            
            # Get total row count
            with get_connection(self.db_path, read_only=True) as conn:
                cursor = conn.cursor()
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                total_rows = cursor.fetchone()[0]
            
            self.update_ingestion_metadata(
                table_name,
                max_date,
                total_rows,
                report.overall_status.value,
                str(report.to_dict())
            )
            
            report.add_check(
                "load_success",
                DataQualityStatus.PASSED,
                f"Successfully loaded to {table_name} ({load_mode})",
                {"total_rows": total_rows, "loaded_rows": len(df_to_load)}
            )
            
            return True, report
            
        except Exception as e:
            report.add_check(
                "load_error",
                DataQualityStatus.FAILED,
                f"Load failed: {e}"
            )
            return False, report
