"""Anomaly detection for solar plant time-series data.

Provides statistical, contextual, and (optional) isolation-forest detectors
that are orchestrated through a single :class:`AnomalyService`.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd
import structlog

logger = structlog.get_logger("services.analytics.anomaly_detection")

# ---------------------------------------------------------------------------
# Optional sklearn import
# ---------------------------------------------------------------------------
_HAS_SKLEARN = False
try:
    from sklearn.ensemble import IsolationForest  # type: ignore[import-untyped]

    _HAS_SKLEARN = True
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------
class AnomalyType(str, Enum):
    """Classification of anomaly root cause."""

    STATISTICAL = "statistical"
    CONTEXTUAL = "contextual"
    ISOLATION_FOREST = "isolation_forest"
    GENERATION_IRRADIANCE = "generation_irradiance"


@dataclass
class Anomaly:
    """Single detected anomaly instance."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    plant_uid: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    anomaly_type: AnomalyType = AnomalyType.STATISTICAL
    metric: str = ""
    value: float = 0.0
    expected_value: float | None = None
    z_score: float | None = None
    severity: str = "warning"
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Detector ABC
# ---------------------------------------------------------------------------
class AnomalyDetector(ABC):
    """Abstract base for all anomaly detectors."""

    @property
    @abstractmethod
    def detector_name(self) -> str:
        """Unique detector identifier."""

    @abstractmethod
    def detect(self, df: pd.DataFrame, plant_uid: str) -> list[Anomaly]:
        """Run detection on *df* and return anomalies."""


# ---------------------------------------------------------------------------
# Z-score based detector
# ---------------------------------------------------------------------------
class StatisticalDetector(AnomalyDetector):
    """Flag readings whose z-score exceeds a configurable threshold."""

    METRICS = ("pr", "generation_kwh", "specific_yield")

    def __init__(self, z_threshold: float = 3.0):
        self.z_threshold = z_threshold

    @property
    def detector_name(self) -> str:
        return "statistical_z_score"

    def detect(self, df: pd.DataFrame, plant_uid: str) -> list[Anomaly]:
        anomalies: list[Anomaly] = []
        for metric in self.METRICS:
            if metric not in df.columns:
                continue
            series = pd.to_numeric(df[metric], errors="coerce").dropna()
            if len(series) < 10:
                continue

            mean = series.mean()
            std = series.std()
            if std == 0 or np.isnan(std):
                continue

            z_scores = (series - mean) / std
            outlier_mask = z_scores.abs() > self.z_threshold

            for idx in series.index[outlier_mask]:
                ts = _resolve_timestamp(df, idx)
                val = float(series.loc[idx])
                z_val = float(z_scores.loc[idx])
                severity = "critical" if abs(z_val) > self.z_threshold + 1 else "warning"
                anomalies.append(
                    Anomaly(
                        plant_uid=plant_uid,
                        timestamp=ts,
                        anomaly_type=AnomalyType.STATISTICAL,
                        metric=metric,
                        value=val,
                        expected_value=float(mean),
                        z_score=z_val,
                        severity=severity,
                        description=(
                            f"{metric} value {val:.2f} deviates from mean "
                            f"{mean:.2f} (z={z_val:+.2f})"
                        ),
                    )
                )
        return anomalies


# ---------------------------------------------------------------------------
# Isolation Forest detector (optional sklearn)
# ---------------------------------------------------------------------------
class IsolationForestDetector(AnomalyDetector):
    """Multivariate outlier detection via ``sklearn.ensemble.IsolationForest``.

    Gracefully returns an empty list when *scikit-learn* is not installed.
    """

    FEATURE_COLS = ("pr", "generation_kwh", "specific_yield", "irradiance")

    def __init__(self, contamination: float = 0.05, random_state: int = 42):
        self.contamination = contamination
        self.random_state = random_state

    @property
    def detector_name(self) -> str:
        return "isolation_forest"

    def detect(self, df: pd.DataFrame, plant_uid: str) -> list[Anomaly]:
        if not _HAS_SKLEARN:
            logger.warning("sklearn_not_available", detector=self.detector_name)
            return []

        available = [c for c in self.FEATURE_COLS if c in df.columns]
        if len(available) < 2:
            return []

        features = df[available].apply(pd.to_numeric, errors="coerce").dropna()
        if len(features) < 20:
            return []

        model = IsolationForest(
            contamination=self.contamination,
            random_state=self.random_state,
            n_estimators=100,
        )
        predictions = model.fit_predict(features.values)

        anomalies: list[Anomaly] = []
        for row_pos, pred in enumerate(predictions):
            if pred == -1:
                idx = features.index[row_pos]
                ts = _resolve_timestamp(df, idx)
                vals = {c: float(features.iloc[row_pos][c]) for c in available}
                anomalies.append(
                    Anomaly(
                        plant_uid=plant_uid,
                        timestamp=ts,
                        anomaly_type=AnomalyType.ISOLATION_FOREST,
                        metric=",".join(available),
                        value=vals.get("generation_kwh", 0.0),
                        severity="warning",
                        description=f"Isolation-forest outlier across {available}",
                        metadata=vals,
                    )
                )
        return anomalies


# ---------------------------------------------------------------------------
# Contextual detector — generation vs irradiance regression
# ---------------------------------------------------------------------------
class ContextualDetector(AnomalyDetector):
    """Detect anomalies where generation deviates from expected given irradiance.

    Uses a simple linear regression (numpy polyfit) of generation_kwh vs
    irradiance and flags residuals > *residual_threshold* standard deviations.
    """

    def __init__(self, residual_threshold: float = 2.5):
        self.residual_threshold = residual_threshold

    @property
    def detector_name(self) -> str:
        return "contextual_gen_irradiance"

    def detect(self, df: pd.DataFrame, plant_uid: str) -> list[Anomaly]:
        if "generation_kwh" not in df.columns or "irradiance" not in df.columns:
            return []

        subset = (
            df[["generation_kwh", "irradiance"]]
            .apply(pd.to_numeric, errors="coerce")
            .dropna()
        )
        # Only keep positive irradiance (daytime)
        subset = subset[subset["irradiance"] > 0]
        if len(subset) < 20:
            return []

        x = subset["irradiance"].values
        y = subset["generation_kwh"].values

        # Linear fit
        coeffs = np.polyfit(x, y, deg=1)
        predicted = np.polyval(coeffs, x)
        residuals = y - predicted
        res_std = float(np.std(residuals))
        if res_std == 0:
            return []

        z_residuals = residuals / res_std
        outlier_mask = np.abs(z_residuals) > self.residual_threshold

        anomalies: list[Anomaly] = []
        indices = subset.index[outlier_mask]
        for pos, idx in enumerate(indices):
            ts = _resolve_timestamp(df, idx)
            val = float(y[subset.index.get_loc(idx)])
            expected = float(predicted[subset.index.get_loc(idx)])
            z_val = float(z_residuals[subset.index.get_loc(idx)])
            severity = "critical" if abs(z_val) > self.residual_threshold + 1 else "warning"
            anomalies.append(
                Anomaly(
                    plant_uid=plant_uid,
                    timestamp=ts,
                    anomaly_type=AnomalyType.GENERATION_IRRADIANCE,
                    metric="generation_kwh",
                    value=val,
                    expected_value=expected,
                    z_score=z_val,
                    severity=severity,
                    description=(
                        f"Generation {val:.1f} kWh deviates from irradiance-"
                        f"predicted {expected:.1f} kWh (z={z_val:+.2f})"
                    ),
                    metadata={"irradiance": float(subset.loc[idx, "irradiance"])},
                )
            )
        return anomalies


# ---------------------------------------------------------------------------
# Orchestrating service
# ---------------------------------------------------------------------------
class AnomalyService:
    """Orchestrate multiple detectors and de-duplicate results."""

    def __init__(
        self,
        detectors: list[AnomalyDetector] | None = None,
        z_threshold: float = 3.0,
        contamination: float = 0.05,
        residual_threshold: float = 2.5,
    ):
        if detectors is not None:
            self.detectors = detectors
        else:
            self.detectors: list[AnomalyDetector] = [
                StatisticalDetector(z_threshold=z_threshold),
                IsolationForestDetector(contamination=contamination),
                ContextualDetector(residual_threshold=residual_threshold),
            ]

    def detect(self, df: pd.DataFrame, plant_uid: str) -> list[Anomaly]:
        """Run all detectors and return de-duplicated anomalies."""
        all_anomalies: list[Anomaly] = []
        for detector in self.detectors:
            try:
                results = detector.detect(df, plant_uid)
                logger.info(
                    "detector_completed",
                    detector=detector.detector_name,
                    plant_uid=plant_uid,
                    anomaly_count=len(results),
                )
                all_anomalies.extend(results)
            except Exception:
                logger.exception(
                    "detector_failed",
                    detector=detector.detector_name,
                    plant_uid=plant_uid,
                )
        return self._deduplicate(all_anomalies)

    @staticmethod
    def _deduplicate(anomalies: list[Anomaly]) -> list[Anomaly]:
        """Remove near-duplicate anomalies (same plant, timestamp, metric)."""
        seen: set[tuple[str, str, str]] = set()
        unique: list[Anomaly] = []
        for a in anomalies:
            key = (a.plant_uid, str(a.timestamp), a.metric)
            if key not in seen:
                seen.add(key)
                unique.append(a)
        return unique


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _resolve_timestamp(df: pd.DataFrame, idx: Any) -> datetime:
    """Best-effort extraction of a timestamp for a given row index."""
    for col in ("timestamp", "ts", "date"):
        if col in df.columns:
            val = df.loc[idx, col]
            if isinstance(val, datetime):
                return val
            if isinstance(val, pd.Timestamp):
                return val.to_pydatetime()
            try:
                return pd.Timestamp(val).to_pydatetime()
            except Exception:
                pass
    if isinstance(idx, (datetime, pd.Timestamp)):
        return pd.Timestamp(idx).to_pydatetime()
    return datetime.now(UTC)
