"""Base classes and result model for analysis engines."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd


@dataclass
class AnalysisResult:
    """Standard result model returned by analysis engines."""

    analysis_type: str
    plant_uid: str
    start: datetime
    end: datetime

    summary: dict[str, Any] = field(default_factory=dict)
    timeseries: pd.DataFrame | None = None
    table: pd.DataFrame | None = None
    losses: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    calculation_seconds: float = 0.0
    data_quality_score: float = 1.0

    @property
    def has_data(self) -> bool:
        """True when any primary result payload exists."""
        has_timeseries = self.timeseries is not None and not self.timeseries.empty
        has_table = self.table is not None and not self.table.empty
        return has_timeseries or has_table or bool(self.summary)


class AnalysisEngine(ABC):
    """Abstract base class for framework-agnostic analysis engines."""

    @property
    @abstractmethod
    def analysis_type(self) -> str:
        """Unique engine type identifier (for example: clipping)."""

    @abstractmethod
    def run(
        self,
        plant_uid: str,
        start: datetime,
        end: datetime,
        **params: Any,
    ) -> AnalysisResult:
        """Run the analysis and return a typed result object."""

    def _load_readings(
        self,
        plant_uid: str,
        start: datetime,
        end: datetime,
        columns: list[str] | None = None,
    ) -> pd.DataFrame:
        """Load reading data through repository abstraction."""
        from services.database.repository import ReadingsRepository

        repo = ReadingsRepository()
        return repo.get_readings_df(plant_uid=plant_uid, start=start, end=end, columns=columns)

    def _load_plant(self, plant_uid: str) -> dict[str, Any]:
        """Load plant metadata through repository abstraction."""
        from services.database.repository import PlantRepository

        repo = PlantRepository()
        return repo.get_by_uid(plant_uid) or {}
