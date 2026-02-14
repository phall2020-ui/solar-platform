"""
Generic CSV / Excel / Parquet upload adapter.

Implements a ``DataSourceAdapter``-like interface for manual file uploads.
Instead of fetching from a remote API, this adapter ingests data from
user-uploaded files and maps columns to the standard ``Reading`` model
using **fuzzy header matching**.

Supported formats:
    - CSV  (.csv)
    - Excel (.xlsx, .xls)
    - Parquet (.parquet)

Quality score: 0.80 (manual upload — provenance less certain)
"""

from __future__ import annotations

import io
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar

import pandas as pd
import structlog
from pydantic import BaseModel, ConfigDict, Field

from services.ingestion.base import (
    DataSourceAdapter,
    FieldMapping,
    HealthState,
    HealthStatus,
    Reading,
    ReadingBatch,
    ReadingQuality,
)

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Fuzzy column-name matching rules
# ---------------------------------------------------------------------------

# Maps regex patterns (case-insensitive) to Reading field names.
# Order matters — first match wins.
COLUMN_PATTERNS: list[tuple[str, str]] = [
    # Timestamp
    (r"(?:^|_)(?:timestamp|time|datetime|date.?time)(?:$|_)", "__timestamp__"),
    (r"^date$", "__timestamp__"),
    (r"^ts$", "__timestamp__"),
    # Power
    (r"(?:ac.?)?power.*kw|p_ac|pac|active.?power|grid.?power", "power_kw"),
    (r"power.*(?:w$|watt)", "power_kw"),  # needs W→kW transform
    # Energy
    (r"energy.*kwh|e_(?:day|total)|yield|generation.*kwh", "energy_kwh"),
    (r"energy.*wh", "energy_kwh"),  # needs Wh→kWh transform
    # Irradiance
    (r"ghi|global.?horiz", "ghi_wm2"),
    (r"poa|plane.?of.?array|in.?plane.?irrad", "poa_wm2"),
    (r"dni|direct.?normal", "dni_wm2"),
    (r"dhi|diffuse.?horiz", "dhi_wm2"),
    (r"gti|global.?tilted", "gti_wm2"),
    (r"irrad", "poa_wm2"),                 # generic fallback
    # Temperature
    (r"(?:ambient|air).?temp", "ambient_temp_c"),
    (r"(?:module|panel|cell).?temp", "module_temp_c"),
    (r"temp(?:erature)?", "ambient_temp_c"),
    # Wind
    (r"wind.?speed|ws|wind_ms|anemometer", "wind_speed_ms"),
    # Voltage / current
    (r"(?:ac.?)?voltage|vac|v_ac", "voltage_v"),
    (r"(?:dc.?)?voltage|vdc|v_dc", "voltage_v"),
    (r"(?:ac.?)?current|iac|i_ac", "current_a"),
    (r"(?:dc.?)?current|idc|i_dc", "current_a"),
    (r"frequency|freq|hz|grid.?freq", "frequency_hz"),
    # Reactive / apparent
    (r"reactive|q_total|kvar", "reactive_power_kvar"),
    (r"apparent|s_total|kva", "apparent_power_kva"),
    (r"power.?factor|pf|cos.?phi", "power_factor"),
    # Device / plant identification
    (r"(?:device|inverter|emig|serial|meter).?(?:id|name|number)", "__device_id__"),
    (r"(?:plant|site|system|station).?(?:id|uid|name|code)", "__plant_uid__"),
]


class ColumnMapping(BaseModel):
    """Result of fuzzy column matching for one file."""
    model_config = ConfigDict(frozen=True)

    file_column: str
    reading_field: str
    confidence: float = Field(ge=0.0, le=1.0, description="Match confidence (1.0 = exact)")
    needs_transform: str | None = None   # e.g. "to_kw" if header says watts


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class GenericCSVAdapter(DataSourceAdapter):
    """
    Adapter for manual CSV / Excel / Parquet file uploads.

    Unlike remote-API adapters, this one does not authenticate against
    an external service.  The ``fetch_readings`` method is replaced by
    :meth:`ingest_file` and :meth:`ingest_dataframe`.

    Column mapping is performed **automatically** via fuzzy header matching,
    but the user can override mappings by passing an explicit ``column_map``.

    Usage::

        adapter = GenericCSVAdapter()
        batch = adapter.ingest_file("/path/to/data.csv", plant_uid="SITE:001")
        # or with a DataFrame already in memory:
        batch = adapter.ingest_dataframe(df, plant_uid="SITE:001")
    """

    source_name: ClassVar[str] = "generic_csv"

    def __init__(
        self,
        default_plant_uid: str = "",
        default_device_id: str = "upload",
    ) -> None:
        super().__init__()
        self.default_plant_uid = default_plant_uid
        self.default_device_id = default_device_id

    # ------------------------------------------------------------------
    # Column auto-detection
    # ------------------------------------------------------------------

    @staticmethod
    def detect_column_mapping(columns: list[str]) -> list[ColumnMapping]:
        """
        Match file columns to ``Reading`` fields using fuzzy regex patterns.

        Returns a list of :class:`ColumnMapping` for each matched column.
        Unmatched columns are silently ignored.
        """
        mappings: list[ColumnMapping] = []
        used_fields: set[str] = set()

        for col in columns:
            col_lower = col.strip().lower()
            for pattern, field in COLUMN_PATTERNS:
                if field in used_fields and field != "__timestamp__":
                    continue  # Don't double-map
                if re.search(pattern, col_lower, re.IGNORECASE):
                    # Detect if value is in watts/watt-hours and needs conversion
                    transform: str | None = None
                    if field == "power_kw" and re.search(r"\bw\b|watt(?!.?h)", col_lower):
                        transform = "to_kw"
                    elif field == "energy_kwh" and re.search(r"\bwh\b|watt.?h", col_lower):
                        transform = "to_kwh"

                    mappings.append(ColumnMapping(
                        file_column=col,
                        reading_field=field,
                        confidence=1.0 if field != "poa_wm2" else 0.8,
                        needs_transform=transform,
                    ))
                    used_fields.add(field)
                    break

        return mappings

    # ------------------------------------------------------------------
    # File loading
    # ------------------------------------------------------------------

    @staticmethod
    def load_file(path: str | Path) -> pd.DataFrame:
        """
        Load a CSV, Excel, or Parquet file into a DataFrame.

        Auto-detects format from extension.

        Raises:
            ValueError: If the format is unsupported.
        """
        p = Path(path)
        ext = p.suffix.lower()
        if ext == ".csv":
            return pd.read_csv(p, parse_dates=True)
        elif ext in (".xlsx", ".xls"):
            return pd.read_excel(p, parse_dates=True)
        elif ext == ".parquet":
            return pd.read_parquet(p)
        else:
            raise ValueError(
                f"Unsupported file format: {ext}. "
                "Supported: .csv, .xlsx, .xls, .parquet"
            )

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def ingest_file(
        self,
        path: str | Path,
        plant_uid: str | None = None,
        device_id: str | None = None,
        column_map: dict[str, str] | None = None,
    ) -> ReadingBatch:
        """
        Ingest readings from a file on disk.

        Args:
            path: Path to CSV / Excel / Parquet file.
            plant_uid: Override plant UID (auto-detected from file if possible).
            device_id: Override device ID.
            column_map: Explicit ``{file_column: reading_field}`` overrides.
        """
        df = self.load_file(path)
        return self.ingest_dataframe(
            df,
            plant_uid=plant_uid,
            device_id=device_id,
            column_map=column_map,
            source_label=str(path),
        )

    def ingest_dataframe(
        self,
        df: pd.DataFrame,
        plant_uid: str | None = None,
        device_id: str | None = None,
        column_map: dict[str, str] | None = None,
        source_label: str = "<dataframe>",
    ) -> ReadingBatch:
        """
        Map a DataFrame to ``Reading`` objects.

        Args:
            df: Input DataFrame.
            plant_uid: Plant UID to assign.
            device_id: Device ID to assign.
            column_map: Optional explicit column mapping overrides.
            source_label: Label for log messages.
        """
        uid = plant_uid or self.default_plant_uid
        dev = device_id or self.default_device_id

        batch = ReadingBatch(source=self.source_name, plant_uid=uid)
        batch.total_raw_records = len(df)

        if df.empty:
            batch.warnings.append("Uploaded file is empty")
            return batch.finalize()

        # 1. Auto-detect column mapping
        auto_mappings = self.detect_column_mapping(list(df.columns))

        # 2. Override with explicit mappings
        if column_map:
            # Remove auto-mappings that conflict
            auto_fields = {m.reading_field for m in auto_mappings}
            for file_col, reading_field in column_map.items():
                auto_mappings = [m for m in auto_mappings if m.reading_field != reading_field]
                auto_mappings.append(ColumnMapping(
                    file_column=file_col,
                    reading_field=reading_field,
                    confidence=1.0,
                ))

        # 3. Identify timestamp column
        ts_mapping = next((m for m in auto_mappings if m.reading_field == "__timestamp__"), None)
        if ts_mapping is None:
            batch.errors.append(
                f"No timestamp column detected in {source_label}. "
                f"Columns: {list(df.columns)}"
            )
            return batch.finalize()

        ts_col = ts_mapping.file_column

        # 4. Identify optional plant_uid / device_id columns
        uid_mapping = next((m for m in auto_mappings if m.reading_field == "__plant_uid__"), None)
        dev_mapping = next((m for m in auto_mappings if m.reading_field == "__device_id__"), None)

        # 5. Data mappings (exclude metadata columns)
        data_mappings = [
            m for m in auto_mappings
            if m.reading_field not in ("__timestamp__", "__plant_uid__", "__device_id__")
        ]

        if not data_mappings:
            batch.warnings.append(
                f"No data columns matched in {source_label}. "
                f"Columns: {list(df.columns)}"
            )

        self.log.info(
            "csv_column_mapping",
            source=source_label,
            mapped=[(m.file_column, m.reading_field) for m in data_mappings],
            timestamp_col=ts_col,
        )

        # 6. Convert rows
        transforms = {
            "to_kw": lambda v: v / 1000.0 if v is not None and pd.notna(v) else None,
            "to_kwh": lambda v: v / 1000.0 if v is not None and pd.notna(v) else None,
        }

        for idx, row in df.iterrows():
            try:
                ts_val = row[ts_col]
                if pd.isna(ts_val):
                    continue

                row_uid = uid
                if uid_mapping and pd.notna(row.get(uid_mapping.file_column)):
                    row_uid = str(row[uid_mapping.file_column])

                row_dev = dev
                if dev_mapping and pd.notna(row.get(dev_mapping.file_column)):
                    row_dev = str(row[dev_mapping.file_column])

                kwargs: dict[str, Any] = {}
                for m in data_mappings:
                    val = row.get(m.file_column)
                    if val is not None and pd.notna(val):
                        try:
                            val = float(val)
                        except (TypeError, ValueError):
                            continue
                        if m.needs_transform and m.needs_transform in transforms:
                            val = transforms[m.needs_transform](val)
                        kwargs[m.reading_field] = val

                reading = Reading(
                    timestamp=ts_val,
                    plant_uid=row_uid,
                    device_id=row_dev,
                    source=self.source_name,
                    quality=ReadingQuality.MEASURED,
                    quality_score=self.reliability,
                    **kwargs,
                )
                batch.readings.append(reading)

            except Exception as exc:
                if len(batch.errors) < 10:
                    batch.errors.append(f"Row {idx}: {exc}")

        return batch.finalize()

    # ------------------------------------------------------------------
    # DataSourceAdapter interface stubs
    # ------------------------------------------------------------------

    async def authenticate(self) -> bool:
        """No authentication needed for file uploads."""
        return True

    async def fetch_readings(
        self,
        plant_uid: str,
        start: datetime,
        end: datetime,
    ) -> ReadingBatch:
        """
        Not applicable for file uploads.

        Use :meth:`ingest_file` or :meth:`ingest_dataframe` instead.
        """
        batch = ReadingBatch(source=self.source_name, plant_uid=plant_uid,
                             requested_start=start, requested_end=end)
        batch.errors.append(
            "GenericCSVAdapter does not support remote fetch. "
            "Use ingest_file() or ingest_dataframe() to load data."
        )
        return batch.finalize()

    async def list_available_plants(self) -> list[dict[str, Any]]:
        """Not applicable — returns empty list."""
        return []

    async def health_check(self) -> HealthStatus:
        """Always healthy — no remote dependency."""
        return HealthStatus(
            source=self.source_name,
            state=HealthState.HEALTHY,
            message="File upload adapter — no remote dependency",
        )

    def get_field_mapping(self) -> list[FieldMapping]:
        """Return an empty list — mappings are dynamic per file."""
        return []
