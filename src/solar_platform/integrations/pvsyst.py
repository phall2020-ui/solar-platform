"""PVsyst simulation-output importer.

Parses PVsyst CSV export files and imports them as budget rows into the
``plant_budgets`` table via :class:`services.financial.budget.BudgetService`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import structlog

logger = structlog.get_logger("services.pvsyst_import")

# ---------------------------------------------------------------------------
# Column-name mapping for common PVsyst header variants
# ---------------------------------------------------------------------------
COLUMN_MAP: dict[str, str] = {
    # Energy / generation
    "E_Grid": "generation_kwh",
    "EGrid": "generation_kwh",
    "E Grid": "generation_kwh",
    "EArray": "generation_kwh",
    "E_Array": "generation_kwh",
    "E Array": "generation_kwh",
    "Eout": "generation_kwh",
    # Irradiance
    "GlobHor": "ghi",
    "GHI": "ghi",
    "GlobInc": "poa_irradiance",
    "GlobEff": "effective_irradiance",
    "POA": "poa_irradiance",
    # Performance ratio
    "PR": "pr",
    "Performance Ratio": "pr",
    # Temperature
    "T_Amb": "ambient_temp",
    "TAmb": "ambient_temp",
    "T Amb": "ambient_temp",
    "TArray": "module_temp",
    "T_Array": "module_temp",
    # Other
    "Month": "month",
    "Year": "year",
}


class PVsystImporter:
    """Parse and import PVsyst CSV exports."""

    def __init__(self, column_map: dict[str, str] | None = None):
        self.column_map = column_map or COLUMN_MAP

    def parse_csv(self, filepath: str | Path) -> pd.DataFrame:
        """Read a PVsyst CSV and return a normalised DataFrame.

        Handles both comma- and semicolon-separated files, automatically
        detects the header row, and renames columns via ``COLUMN_MAP``.
        """
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"PVsyst file not found: {filepath}")

        raw_text = filepath.read_text(errors="replace")
        sep = ";" if ";" in raw_text.split("\n")[0] else ","

        # PVsyst files often have metadata rows before the real header.
        # We look for the first row that actually has recognisable headers.
        header_row = self._find_header_row(raw_text, sep)

        df = pd.read_csv(filepath, sep=sep, header=header_row, skipinitialspace=True)

        # Strip leading/trailing whitespace from column names
        df.columns = [str(c).strip() for c in df.columns]

        # Rename known PVsyst columns
        rename = {}
        for col in df.columns:
            if col in self.column_map:
                rename[col] = self.column_map[col]
        if rename:
            df = df.rename(columns=rename)

        # Coerce numeric columns
        for col in ("generation_kwh", "ghi", "poa_irradiance", "pr", "ambient_temp", "module_temp"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # Validate reasonable ranges
        self._validate(df)

        return df

    def import_as_budget(
        self,
        filepath: str | Path,
        plant_uid: str,
        year: int,
        scenario: str = "pvsyst",
        db_engine: Any | None = None,
    ) -> int:
        """Parse a PVsyst CSV and insert monthly generation as budget rows.

        Returns the number of budget rows imported.
        """
        from solar_platform.financial.budget import BudgetService

        df = self.parse_csv(filepath)

        if "generation_kwh" not in df.columns:
            raise ValueError("Parsed PVsyst file has no generation_kwh column.")

        # Determine monthly aggregation
        if "month" in df.columns:
            monthly = df.groupby("month")["generation_kwh"].sum().reset_index()
        elif len(df) == 12:
            # Assume each row is a month (Jan–Dec)
            monthly = pd.DataFrame({
                "month": range(1, 13),
                "generation_kwh": df["generation_kwh"].values[:12],
            })
        else:
            raise ValueError(
                f"Cannot determine monthly structure from PVsyst data "
                f"({len(df)} rows, no 'month' column)."
            )

        budget_svc = BudgetService(engine=db_engine)
        count = 0
        for _, row in monthly.iterrows():
            m = int(row["month"])
            kwh = float(row["generation_kwh"])
            if kwh <= 0:
                continue
            budget_svc.set_budget(
                plant_uid=plant_uid,
                year=year,
                month=m,
                budget_kwh=kwh,
                scenario=scenario,
                source="pvsyst",
            )
            count += 1

        logger.info(
            "pvsyst_imported",
            filepath=str(filepath),
            plant_uid=plant_uid,
            year=year,
            months_imported=count,
        )
        return count

    # ---- internal --------------------------------------------------------

    @staticmethod
    def _find_header_row(raw_text: str, sep: str) -> int:
        """Heuristic: the header row is the first row containing ≥3
        recognised PVsyst column names."""
        known = set(COLUMN_MAP.keys())
        for i, line in enumerate(raw_text.split("\n")):
            tokens = {t.strip() for t in line.split(sep)}
            if len(tokens & known) >= 2:
                return i
        return 0

    @staticmethod
    def _validate(df: pd.DataFrame) -> None:
        """Log warnings for values outside expected physical ranges."""
        if "generation_kwh" in df.columns:
            neg = (df["generation_kwh"] < 0).sum()
            if neg:
                logger.warning("pvsyst_negative_generation", count=int(neg))
        if "pr" in df.columns:
            bad_pr = ((df["pr"] < 0) | (df["pr"] > 1.5)).sum()
            if bad_pr:
                logger.warning("pvsyst_pr_out_of_range", count=int(bad_pr))
