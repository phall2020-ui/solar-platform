# Phase 7: Advanced Features — Detailed Action Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Duration:** 4 weeks  
**Goal:** Add advanced analytics (anomaly detection, forecasting), financial tracking (revenue, tariffs, budget vs. actual), PVsyst import, granular access control, and an external REST API for third-party integration.

**Key Principle:** Each feature is a self-contained service module. The Streamlit pages consume services — when extracted to FastAPI + React, only UI rebuilds are needed.

**Prerequisite:** Phase 0 (database), Phase 1 (data), Phase 3 (analysis), Phase 4 (alerts), Phase 6 (quality).

---

## Table of Contents

1. [Progress Tracker](#1-progress-tracker)
2. [Dependency Graph](#2-dependency-graph)
3. [Task 7.1: Anomaly Detection Service](#task-71-anomaly-detection-service)
4. [Task 7.2: Forecasting Integration](#task-72-forecasting-integration)
5. [Task 7.3: Financial Module — Revenue Tracking](#task-73-financial-module--revenue-tracking)
6. [Task 7.4: Financial Module — Tariff Management](#task-74-financial-module--tariff-management)
7. [Task 7.5: Financial Module — Budget vs. Actual](#task-75-financial-module--budget-vs-actual)
8. [Task 7.6: PVsyst Import](#task-76-pvsyst-import)
9. [Task 7.7: Granular Access Control](#task-77-granular-access-control)
10. [Task 7.8: External REST API](#task-78-external-rest-api)
11. [Task 7.9: Anomaly Detection UI](#task-79-anomaly-detection-ui)
12. [Task 7.10: Financial Dashboard UI](#task-710-financial-dashboard-ui)
13. [Risks](#risks)
14. [Definition of Done](#definition-of-done)

---

## 1. Progress Tracker

| Task | Status | Est Hours | Priority | Dependencies |
|------|--------|-----------|----------|--------------|
| 7.1 Anomaly Detection Service | ✅ Done | 10 | P1 | Phase 3, Phase 6 |
| 7.2 Forecasting Integration | ✅ Done | 8 | P1 | Phase 1 |
| 7.3 Revenue Tracking | ✅ Done | 8 | P1 | — |
| 7.4 Tariff Management | ✅ Done | 6 | P1 | 7.3 |
| 7.5 Budget vs. Actual | ✅ Done | 6 | P1 | 7.3, 7.4, 7.6 |
| 7.6 PVsyst Import | ✅ Done | 8 | P2 | Phase 0 |
| 7.7 Granular Access Control | ✅ Done | 8 | P1 | Phase 0 |
| 7.8 External REST API | ✅ Done | 10 | P2 | All services |
| 7.9 Anomaly Detection UI | ✅ Done | 6 | P1 | 7.1 |
| 7.10 Financial Dashboard UI | ✅ Done | 6 | P1 | 7.3, 7.4, 7.5 |
| **TOTAL** | | **76** | | |

---

## 2. Dependency Graph

```
┌────────────┐   ┌────────────┐   ┌────────────┐
│ 7.1 Anomaly│   │ 7.2 Fore-  │   │ 7.6 PVsyst │
│ Detection  │   │ casting    │   │ Import     │
└─────┬──────┘   └────────────┘   └─────┬──────┘
      │                                 │
      ▼                                 │
┌────────────┐                          │
│ 7.9 Anomaly│                          │
│ UI         │                          │
└────────────┘                          │
                                        │
┌────────────┐   ┌────────────┐         │
│ 7.3 Revenue│───▶ 7.4 Tariff │         │
│ Tracking   │   │ Mgmt       │         │
└─────┬──────┘   └─────┬──────┘         │
      │                │                │
      └────────┬───────┘                │
               │                        │
               ▼                        │
         ┌────────────┐                 │
         │ 7.5 Budget │◄────────────────┘
         │ vs. Actual │
         └─────┬──────┘
               │
               ▼
         ┌────────────┐
         │ 7.10 Fin.  │
         │ Dashboard  │
         └────────────┘

┌────────────┐   ┌────────────┐
│ 7.7 Access │   │ 7.8 REST   │
│ Control    │   │ API        │
└────────────┘   └────────────┘
```

---

## Task 7.1: Anomaly Detection Service

**Goal:** Detect anomalous plant behavior using statistical and ML-based methods.

**Estimated Hours:** 10

### `services/analytics/anomaly_detection.py`
```python
"""
Anomaly detection for solar plant performance.

Three detection methods:
1. Statistical (Z-score / IQR on PR, generation/capacity)
2. Isolation Forest (scikit-learn based, trained on plant history)
3. Contextual (weather-adjusted — e.g., low generation on a sunny day)

Each method produces AnomalyResult objects with confidence scores.

NOTE: scikit-learn is an optional dependency. If not installed,
only statistical methods are available.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd
import structlog

logger = structlog.get_logger("analytics.anomaly")


class AnomalyType(str, Enum):
    LOW_PR = "low_pr"
    LOW_GENERATION = "low_generation"
    HIGH_GENERATION = "high_generation"
    GENERATION_DROP = "generation_drop"
    IRRADIANCE_MISMATCH = "irradiance_mismatch"
    SENSOR_STUCK = "sensor_stuck"
    UNKNOWN = "unknown"


@dataclass
class Anomaly:
    """A detected anomaly."""
    plant_uid: str
    timestamp: datetime
    anomaly_type: AnomalyType
    confidence: float       # 0.0 to 1.0
    deviation: float        # How far from normal (z-score or similar)
    expected_value: float
    actual_value: float
    metric: str             # e.g., "pr", "generation_kwh"
    method: str             # "statistical", "isolation_forest", "contextual"
    details: dict[str, Any] = field(default_factory=dict)


class AnomalyDetector(ABC):
    """Base class for anomaly detectors."""
    
    @abstractmethod
    def detect(self, df: pd.DataFrame, plant_uid: str) -> list[Anomaly]:
        """Run anomaly detection on a timeseries DataFrame."""
        ...


class StatisticalDetector(AnomalyDetector):
    """Z-score and IQR based anomaly detection."""
    
    def __init__(self, z_threshold: float = 2.5, min_samples: int = 30):
        self.z_threshold = z_threshold
        self.min_samples = min_samples
    
    def detect(self, df: pd.DataFrame, plant_uid: str) -> list[Anomaly]:
        anomalies = []
        
        for col in ["pr", "generation_kwh", "specific_yield"]:
            if col not in df.columns:
                continue
            
            series = df[col].dropna()
            if len(series) < self.min_samples:
                continue
            
            mean = series.mean()
            std = series.std()
            if std == 0:
                continue
            
            z_scores = (series - mean) / std
            
            for idx, z in z_scores.items():
                if abs(z) > self.z_threshold:
                    ts = df.loc[idx, "timestamp"] if "timestamp" in df.columns else idx
                    anomaly_type = AnomalyType.LOW_PR if col == "pr" and z < 0 else AnomalyType.UNKNOWN
                    
                    anomalies.append(Anomaly(
                        plant_uid=plant_uid,
                        timestamp=ts,
                        anomaly_type=anomaly_type,
                        confidence=min(1.0, abs(z) / 5.0),  # Normalize confidence
                        deviation=round(z, 2),
                        expected_value=round(mean, 2),
                        actual_value=round(series.loc[idx], 2),
                        metric=col,
                        method="statistical",
                    ))
        
        return anomalies


class IsolationForestDetector(AnomalyDetector):
    """Isolation Forest for multivariate anomaly detection.
    
    Requires scikit-learn. Trains on plant's historical data using
    features: PR, specific yield, temperature, irradiance.
    """
    
    def __init__(self, contamination: float = 0.05):
        self.contamination = contamination
    
    def detect(self, df: pd.DataFrame, plant_uid: str) -> list[Anomaly]:
        try:
            from sklearn.ensemble import IsolationForest
        except ImportError:
            logger.warning("sklearn_not_available", msg="Isolation Forest requires scikit-learn")
            return []
        
        feature_cols = [c for c in ["pr", "generation_kwh", "irradiance_kwh_m2", "temperature_c"]
                        if c in df.columns]
        if len(feature_cols) < 2:
            return []
        
        features = df[feature_cols].dropna()
        if len(features) < 50:
            return []
        
        model = IsolationForest(contamination=self.contamination, random_state=42, n_jobs=-1)
        predictions = model.fit_predict(features)
        scores = model.decision_function(features)
        
        anomalies = []
        for i, (pred, score) in enumerate(zip(predictions, scores)):
            if pred == -1:  # Anomaly
                idx = features.index[i]
                ts = df.loc[idx, "timestamp"] if "timestamp" in df.columns else idx
                anomalies.append(Anomaly(
                    plant_uid=plant_uid,
                    timestamp=ts,
                    anomaly_type=AnomalyType.UNKNOWN,
                    confidence=min(1.0, abs(score) * 2),
                    deviation=round(float(score), 3),
                    expected_value=0,
                    actual_value=0,
                    metric="multivariate",
                    method="isolation_forest",
                    details={"features": {c: round(float(features.loc[idx, c]), 3) for c in feature_cols}},
                ))
        
        return anomalies


class ContextualDetector(AnomalyDetector):
    """Weather-adjusted anomaly detection.

    Detects: generation is low compared to what irradiance suggests.
    Trains a simple model: expected_gen = f(irradiance, temperature).
    """
    
    def __init__(self, residual_threshold: float = 2.0):
        self.residual_threshold = residual_threshold
    
    def detect(self, df: pd.DataFrame, plant_uid: str) -> list[Anomaly]:
        required = {"generation_kwh", "irradiance_kwh_m2"}
        if not required.issubset(set(df.columns)):
            return []
        
        clean = df[list(required)].dropna()
        if len(clean) < 30:
            return []
        
        # Simple linear relationship: gen ~ irradiance
        x = clean["irradiance_kwh_m2"]
        y = clean["generation_kwh"]
        
        # Linear regression
        slope = np.cov(x, y)[0, 1] / np.var(x) if np.var(x) > 0 else 0
        intercept = y.mean() - slope * x.mean()
        predicted = slope * x + intercept
        residuals = y - predicted
        
        std_res = residuals.std()
        if std_res == 0:
            return []
        
        anomalies = []
        for idx in residuals.index:
            z = residuals.loc[idx] / std_res
            if z < -self.residual_threshold:  # Low generation relative to irradiance
                ts = df.loc[idx, "timestamp"] if "timestamp" in df.columns else idx
                anomalies.append(Anomaly(
                    plant_uid=plant_uid,
                    timestamp=ts,
                    anomaly_type=AnomalyType.IRRADIANCE_MISMATCH,
                    confidence=min(1.0, abs(z) / 4.0),
                    deviation=round(float(z), 2),
                    expected_value=round(float(predicted.loc[idx]), 2),
                    actual_value=round(float(y.loc[idx]), 2),
                    metric="generation_kwh",
                    method="contextual",
                ))
        
        return anomalies


class AnomalyService:
    """Orchestrates anomaly detection across methods."""
    
    def __init__(self):
        self.detectors: list[AnomalyDetector] = [
            StatisticalDetector(),
            IsolationForestDetector(),
            ContextualDetector(),
        ]
    
    def analyze(self, df: pd.DataFrame, plant_uid: str) -> list[Anomaly]:
        """Run all detectors and merge results."""
        all_anomalies = []
        for detector in self.detectors:
            try:
                results = detector.detect(df, plant_uid)
                all_anomalies.extend(results)
                logger.info("anomaly_detection", detector=type(detector).__name__, count=len(results))
            except Exception as e:
                logger.error("anomaly_detection_error", detector=type(detector).__name__, error=str(e))
        
        # Deduplicate: same plant + timestamp + metric → keep highest confidence
        unique: dict[str, Anomaly] = {}
        for a in all_anomalies:
            key = f"{a.plant_uid}_{a.timestamp}_{a.metric}"
            if key not in unique or a.confidence > unique[key].confidence:
                unique[key] = a
        
        return sorted(unique.values(), key=lambda a: a.confidence, reverse=True)
```

### Testing

```bash
python -c "
import pandas as pd
import numpy as np
from services.analytics.anomaly_detection import StatisticalDetector

# Generate normal data with 3 anomalies
np.random.seed(42)
n = 100
df = pd.DataFrame({
    'timestamp': pd.date_range('2025-01-01', periods=n, freq='h'),
    'pr': np.random.normal(0.82, 0.03, n),
    'generation_kwh': np.random.normal(500, 30, n),
})
# Inject anomalies
df.loc[10, 'pr'] = 0.4  # Very low PR
df.loc[50, 'generation_kwh'] = 50  # Very low generation
df.loc[90, 'pr'] = 1.1  # Unusually high PR

detector = StatisticalDetector(z_threshold=2.5)
anomalies = detector.detect(df, 'test_plant')
print(f'Detected {len(anomalies)} anomalies')
for a in anomalies:
    print(f'  {a.metric}: z={a.deviation}, actual={a.actual_value}, expected={a.expected_value}')
assert len(anomalies) >= 2, 'Should detect at least 2 anomalies'
print('PASS')
"
```

### Acceptance Criteria

- [ ] Statistical detector finds outliers by z-score
- [ ] Isolation Forest runs if scikit-learn installed
- [ ] Contextual detector catches irradiance vs. generation mismatch
- [ ] Results deduplicated across methods
- [ ] Confidence scores normalized to 0-1

---

## Task 7.2: Forecasting Integration

**Goal:** Integrate generation forecasting using weather data and historical patterns.

**Estimated Hours:** 8

### `services/analytics/forecasting.py`
```python
"""
Generation forecasting service.

Methods:
1. Persistence forecast: tomorrow = today (Baseline)
2. Simple statistical: hourly profile × irradiance forecast
3. Weather-based: use SolarGIS/pvlib clear-sky model

Forecasts are stored in a `forecasts` table and displayed alongside actuals.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import structlog

logger = structlog.get_logger("analytics.forecasting")


@dataclass
class Forecast:
    """A generation forecast for a plant."""
    plant_uid: str
    timestamp: datetime
    generation_kwh: float
    method: str               # "persistence", "statistical", "weather"
    confidence_low: float     # 10th percentile
    confidence_high: float    # 90th percentile


class ForecastMethod(ABC):
    @abstractmethod
    def forecast(self, plant_uid: str, historical: pd.DataFrame, horizon_hours: int) -> list[Forecast]:
        ...


class PersistenceForecast(ForecastMethod):
    """Tomorrow = last equivalent day."""
    
    def forecast(self, plant_uid: str, historical: pd.DataFrame, horizon_hours: int = 24) -> list[Forecast]:
        if historical.empty:
            return []
        
        # Use last day's profile
        last_day = historical.tail(24)
        if len(last_day) < 24:
            return []
        
        forecasts = []
        for i, (_, row) in enumerate(last_day.iterrows()):
            gen = row.get("generation_kwh", 0)
            forecasts.append(Forecast(
                plant_uid=plant_uid,
                timestamp=datetime.utcnow().replace(hour=i, minute=0, second=0) + timedelta(days=1),
                generation_kwh=gen,
                method="persistence",
                confidence_low=gen * 0.7,
                confidence_high=gen * 1.3,
            ))
        
        return forecasts


class StatisticalForecast(ForecastMethod):
    """Hourly profile from historical data with seasonal adjustment."""
    
    def forecast(self, plant_uid: str, historical: pd.DataFrame, horizon_hours: int = 24) -> list[Forecast]:
        if len(historical) < 168:  # Need at least 1 week
            return []
        
        historical["hour"] = pd.to_datetime(historical["timestamp"]).dt.hour
        profile = historical.groupby("hour")["generation_kwh"].agg(["mean", "std"]).reset_index()
        
        forecasts = []
        now = datetime.utcnow()
        for h in range(horizon_hours):
            ts = now + timedelta(hours=h)
            hour_data = profile[profile["hour"] == ts.hour]
            if hour_data.empty:
                continue
            
            mean = float(hour_data["mean"].iloc[0])
            std = float(hour_data["std"].iloc[0])
            
            forecasts.append(Forecast(
                plant_uid=plant_uid,
                timestamp=ts,
                generation_kwh=round(mean, 2),
                method="statistical",
                confidence_low=round(max(0, mean - 1.645 * std), 2),
                confidence_high=round(mean + 1.645 * std, 2),
            ))
        
        return forecasts
```

### Database Table

```sql
CREATE TABLE IF NOT EXISTS forecasts (
    id              VARCHAR PRIMARY KEY DEFAULT gen_random_uuid()::VARCHAR,
    plant_uid       VARCHAR NOT NULL,
    timestamp       TIMESTAMP NOT NULL,
    generation_kwh  DOUBLE,
    method          VARCHAR,
    confidence_low  DOUBLE,
    confidence_high DOUBLE,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(plant_uid, timestamp, method)
);
```

### Acceptance Criteria

- [ ] Persistence and statistical forecast methods implemented
- [ ] Forecasts stored in DuckDB
- [ ] Confidence bounds displayed as shaded area on charts
- [ ] Extensible for weather-based forecasting (pvlib)

---

## Task 7.3: Financial Module — Revenue Tracking

**Goal:** Track revenue per plant per month from generation × tariff.

**Estimated Hours:** 8

### `services/financial/__init__.py`
```python
"""Financial services package."""
```

### `services/financial/revenue.py`
```python
"""
Revenue tracking service.

Revenue = sum(generation_kwh × tariff_per_kwh) per period.

Supports:
- Fixed tariff per plant
- Time-of-use tariff (peak/off-peak)
- FiT (Feed-in Tariff) with annual degression
- PPA (Power Purchase Agreement) with price escalation
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

import pandas as pd
import structlog

logger = structlog.get_logger("financial.revenue")


class TariffType(str, Enum):
    FIXED = "fixed"
    TIME_OF_USE = "time_of_use"
    FIT = "feed_in_tariff"
    PPA = "ppa"


@dataclass
class RevenueResult:
    plant_uid: str
    period_start: datetime
    period_end: datetime
    generation_mwh: float
    revenue_gbp: float
    tariff_type: TariffType
    avg_tariff_per_mwh: float
    currency: str = "GBP"


class RevenueService:
    """Calculate revenue from generation and tariffs."""
    
    def __init__(self, db_engine):
        self.db = db_engine
    
    def calculate_monthly(
        self,
        plant_uid: str,
        year: int,
        month: int,
        tariff_per_mwh: float = 50.0,
        tariff_type: TariffType = TariffType.FIXED,
    ) -> RevenueResult:
        """Calculate revenue for one plant for one month."""
        query = """
            SELECT SUM(generation_kwh) / 1000.0 AS generation_mwh
            FROM readings
            WHERE plant_uid = ?
              AND EXTRACT(YEAR FROM timestamp) = ?
              AND EXTRACT(MONTH FROM timestamp) = ?
        """
        with self.db.connect() as conn:
            result = conn.execute(query, [plant_uid, year, month]).fetchone()
        
        gen_mwh = result[0] if result and result[0] else 0.0
        revenue = gen_mwh * tariff_per_mwh
        
        return RevenueResult(
            plant_uid=plant_uid,
            period_start=datetime(year, month, 1),
            period_end=datetime(year, month + 1, 1) if month < 12 else datetime(year + 1, 1, 1),
            generation_mwh=round(gen_mwh, 2),
            revenue_gbp=round(revenue, 2),
            tariff_type=tariff_type,
            avg_tariff_per_mwh=tariff_per_mwh,
        )
    
    def portfolio_summary(self, year: int, month: int) -> pd.DataFrame:
        """Revenue summary across all plants."""
        query = """
            SELECT 
                p.uid AS plant_uid,
                p.name,
                COALESCE(SUM(r.generation_kwh) / 1000.0, 0) AS generation_mwh
            FROM plants p
            LEFT JOIN readings r ON p.uid = r.plant_uid
              AND EXTRACT(YEAR FROM r.timestamp) = ?
              AND EXTRACT(MONTH FROM r.timestamp) = ?
            GROUP BY p.uid, p.name
            ORDER BY generation_mwh DESC
        """
        with self.db.connect() as conn:
            df = pd.read_sql(query, conn, params=[year, month])
        
        return df
```

### Database Table

```sql
CREATE TABLE IF NOT EXISTS plant_tariffs (
    plant_uid       VARCHAR NOT NULL,
    tariff_type     VARCHAR NOT NULL DEFAULT 'fixed',
    tariff_per_mwh  DOUBLE NOT NULL,
    currency        VARCHAR DEFAULT 'GBP',
    start_date      DATE NOT NULL,
    end_date        DATE,
    escalation_pct  DOUBLE DEFAULT 0.0,
    peak_rate       DOUBLE DEFAULT NULL,
    off_peak_rate   DOUBLE DEFAULT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (plant_uid, start_date)
);
```

### Acceptance Criteria

- [ ] Revenue = generation × tariff for each plant
- [ ] Supports fixed, FiT, PPA tariff types
- [ ] Monthly and yearly aggregation
- [ ] Portfolio-wide revenue summary

---

## Task 7.4: Tariff Management

**Goal:** UI and storage for managing plant tariff schedules.

**Estimated Hours:** 6

### Features

- Tariff per plant with date ranges
- Support for escalation (annual % increase)
- Import tariff schedules from CSV
- Historical tariff lookup for past revenue calculations

### Acceptance Criteria

- [ ] CRUD for plant tariffs
- [ ] Date-ranged tariff lookup
- [ ] Annual escalation calculated automatically
- [ ] CSV import of tariff schedules

---

## Task 7.5: Financial Module — Budget vs. Actual

**Goal:** Compare actual generation/revenue against budgeted values (from PVsyst or manual entry).

**Estimated Hours:** 6

### `services/financial/budget.py`
```python
"""
Budget vs. Actual analysis.

Compares:
- Actual generation vs. budgeted (PVsyst P50/P75/P90)
- Actual revenue vs. budgeted
- Actual PR vs. budgeted

Results used for investor reporting.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd


@dataclass
class BudgetComparison:
    plant_uid: str
    period: str                    # e.g., "Jan 2025"
    budget_mwh: float             # From PVsyst or manual entry
    actual_mwh: float
    variance_mwh: float           # actual - budget
    variance_pct: float           # (actual - budget) / budget × 100
    budget_revenue_gbp: float
    actual_revenue_gbp: float
    
    @property
    def on_track(self) -> bool:
        """Is actual within ±5% of budget?"""
        return abs(self.variance_pct) <= 5.0


class BudgetService:
    """Budget vs. actual tracking."""
    
    def __init__(self, db_engine):
        self.db = db_engine
    
    def compare(self, plant_uid: str, year: int, month: int) -> BudgetComparison:
        """Compare actual vs budget for one month."""
        # Get budget
        budget_query = """
            SELECT generation_mwh, revenue_gbp 
            FROM plant_budgets 
            WHERE plant_uid = ? AND year = ? AND month = ?
        """
        actual_query = """
            SELECT COALESCE(SUM(generation_kwh) / 1000.0, 0) AS actual_mwh
            FROM readings
            WHERE plant_uid = ? 
              AND EXTRACT(YEAR FROM timestamp) = ?
              AND EXTRACT(MONTH FROM timestamp) = ?
        """
        with self.db.connect() as conn:
            budget_row = conn.execute(budget_query, [plant_uid, year, month]).fetchone()
            actual_row = conn.execute(actual_query, [plant_uid, year, month]).fetchone()
        
        budget_mwh = budget_row[0] if budget_row else 0.0
        budget_rev = budget_row[1] if budget_row and len(budget_row) > 1 else 0.0
        actual_mwh = actual_row[0] if actual_row else 0.0
        
        variance = actual_mwh - budget_mwh
        variance_pct = (variance / budget_mwh * 100) if budget_mwh > 0 else 0.0
        
        return BudgetComparison(
            plant_uid=plant_uid,
            period=f"{datetime(year, month, 1).strftime('%b %Y')}",
            budget_mwh=budget_mwh,
            actual_mwh=round(actual_mwh, 2),
            variance_mwh=round(variance, 2),
            variance_pct=round(variance_pct, 1),
            budget_revenue_gbp=budget_rev,
            actual_revenue_gbp=0.0,  # To be calculated with tariff
        )
```

### Database Table

```sql
CREATE TABLE IF NOT EXISTS plant_budgets (
    plant_uid       VARCHAR NOT NULL,
    year            INTEGER NOT NULL,
    month           INTEGER NOT NULL,
    generation_mwh  DOUBLE NOT NULL,
    revenue_gbp     DOUBLE DEFAULT 0.0,
    pr_budget       DOUBLE DEFAULT NULL,
    scenario        VARCHAR DEFAULT 'P50',  -- P50, P75, P90
    source          VARCHAR DEFAULT 'manual', -- 'manual', 'pvsyst'
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (plant_uid, year, month, scenario)
);
```

### Acceptance Criteria

- [ ] Budget table stores P50/P75/P90 scenarios
- [ ] Variance calculated for generation and revenue
- [ ] Color coding: green ≤ ±5%, amber ±5-15%, red > ±15%
- [ ] YTD cumulative budget vs. actual tracking

---

## Task 7.6: PVsyst Import

**Goal:** Import PVsyst simulation results as budget/reference values.

**Estimated Hours:** 8

### Supported Formats

1. **PVsyst CSV export** (most common)
   - Monthly summary rows with columns: Month, E_Grid (kWh), GlobInc (kWh/m²), PR (%)
   
2. **PVsyst .PAN/.OND files** (module/inverter specs)
   - Parse for AC/DC specifications

### `services/pvsyst_import.py`
```python
"""
PVsyst simulation result importer.

Parses PVsyst CSV exports and loads monthly budget values
into the plant_budgets table.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import structlog

logger = structlog.get_logger("pvsyst.import")


class PVsystImporter:
    """Import PVsyst simulation results."""
    
    # PVsyst CSV column name mappings (handles variants)
    COLUMN_MAP = {
        "E_Grid": "generation_kwh",
        "EGrid": "generation_kwh",
        "E Grid": "generation_kwh",
        "GlobInc": "irradiance_kwh_m2",
        "GlobHor": "irradiance_horizontal",
        "PR": "pr",
        "Yf": "specific_yield",
    }
    
    def parse_csv(self, filepath: str | Path) -> pd.DataFrame:
        """Parse a PVsyst monthly CSV export.
        
        Returns DataFrame with columns: month, generation_kwh, irradiance_kwh_m2, pr
        """
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"PVsyst file not found: {filepath}")
        
        # PVsyst CSVs often have metadata rows at the top
        # Try to find the header row
        with open(filepath) as f:
            lines = f.readlines()
        
        header_idx = 0
        for i, line in enumerate(lines):
            if any(col in line for col in ["E_Grid", "EGrid", "GlobInc"]):
                header_idx = i
                break
        
        df = pd.read_csv(filepath, skiprows=header_idx, sep=";|,", engine="python")
        
        # Rename columns
        for old_name, new_name in self.COLUMN_MAP.items():
            if old_name in df.columns:
                df = df.rename(columns={old_name: new_name})
        
        # Filter to 12 monthly rows
        if len(df) > 12:
            df = df.head(12)
        
        df["month"] = range(1, len(df) + 1)
        
        return df
    
    def import_as_budget(
        self,
        filepath: str | Path,
        plant_uid: str,
        year: int,
        scenario: str = "P50",
        db_engine=None,
    ) -> int:
        """Import PVsyst data as budget values for a plant.
        
        Returns number of rows imported.
        """
        df = self.parse_csv(filepath)
        
        if db_engine is None:
            logger.warning("no_db_engine", msg="Dry run — not saving to database")
            return len(df)
        
        count = 0
        with db_engine.connect() as conn:
            for _, row in df.iterrows():
                conn.execute("""
                    INSERT OR REPLACE INTO plant_budgets 
                    (plant_uid, year, month, generation_mwh, pr_budget, scenario, source)
                    VALUES (?, ?, ?, ?, ?, ?, 'pvsyst')
                """, [
                    plant_uid, year, int(row["month"]),
                    row.get("generation_kwh", 0) / 1000.0,
                    row.get("pr", None),
                    scenario,
                ])
                count += 1
        
        logger.info("pvsyst_imported", plant_uid=plant_uid, year=year, rows=count)
        return count
```

### Acceptance Criteria

- [ ] Parses PVsyst monthly CSV exports (semicolon and comma separated)
- [ ] Handles metadata header rows
- [ ] Imports as P50/P75/P90 budget scenarios
- [ ] Validates data ranges (no negative, reasonable values)

---

## Task 7.7: Granular Access Control

**Goal:** Extend the existing RBAC system with per-plant permissions.

**Estimated Hours:** 8

### Current State

The existing auth system (`services/auth_service.py`) has 4 roles: `admin`, `manager`, `analyst`, `viewer`. Authorization is page-level only.

### New Model

```python
# services/access_control.py
"""
Granular access control.

Extends role-based auth with:
- Per-plant access (user can only see assigned plants)
- Per-feature access (user can access specific modules)
- Data export permissions
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class UserPermissions:
    """Resolved permissions for a user."""
    user_id: str
    role: str
    plant_uids: list[str] = field(default_factory=list)  # Empty = all plants
    features: list[str] = field(default_factory=list)     # Empty = all features
    can_export: bool = True
    can_generate_reports: bool = True
    can_manage_alerts: bool = True
    can_manage_users: bool = False
    
    def has_plant_access(self, plant_uid: str) -> bool:
        """Check if user has access to a specific plant."""
        if not self.plant_uids:  # Empty = all plants
            return True
        return plant_uid in self.plant_uids
    
    def filter_plants(self, plant_uids: list[str]) -> list[str]:
        """Filter a list of plant UIDs to only those the user can access."""
        if not self.plant_uids:
            return plant_uids
        return [uid for uid in plant_uids if uid in self.plant_uids]
```

### Database Table

```sql
CREATE TABLE IF NOT EXISTS user_plant_access (
    user_id     VARCHAR NOT NULL,
    plant_uid   VARCHAR NOT NULL,
    granted_by  VARCHAR,
    granted_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, plant_uid)
);

CREATE TABLE IF NOT EXISTS user_feature_access (
    user_id     VARCHAR NOT NULL,
    feature     VARCHAR NOT NULL,   -- e.g., 'data_export', 'report_builder', 'alert_management'
    granted_by  VARCHAR,
    granted_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, feature)
);
```

### Integration with Streamlit

```python
# In any module page:
from services.access_control import get_current_permissions

permissions = get_current_permissions()
plants = permissions.filter_plants(all_plant_uids)

if not permissions.has_plant_access(selected_plant):
    st.error("You don't have access to this plant.")
    st.stop()
```

### Acceptance Criteria

- [ ] Per-plant access control stored in database
- [ ] Admin UI for assigning plants to users
- [ ] All data queries filtered by user's plant access
- [ ] Backward compatible — existing users get access to all plants

---

## Task 7.8: External REST API

**Goal:** Expose a lightweight REST API for third-party integrations using FastAPI (run as a sidecar or future replacement).

**Estimated Hours:** 10

### `api/__init__.py`
```python
"""External REST API for third-party integrations."""
```

### `api/main.py`
```python
"""
External REST API using FastAPI.

DEPLOYMENT OPTIONS:
1. Sidecar: docker-compose runs FastAPI on port 8001 alongside Streamlit on 8501
2. Future: Replace Streamlit with FastAPI + React frontend

This module is the extraction point — when migrating to FastAPI,
this file becomes the main application.

NOTE: This is a READ-ONLY API for now. Write operations (ingestion)
remain in the Streamlit app until full migration.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

app = FastAPI(
    title="AMPYR Solar Portfolio API",
    version="1.0.0",
    description="Read-only API for solar portfolio data",
)


class PlantResponse(BaseModel):
    uid: str
    name: str
    capacity_kwp: float
    status: str
    latitude: float | None = None
    longitude: float | None = None


class ReadingsResponse(BaseModel):
    plant_uid: str
    period: str
    readings_count: int
    generation_mwh: float
    avg_pr: float | None


@app.get("/api/v1/plants", response_model=list[PlantResponse])
async def list_plants():
    """List all plants in the portfolio."""
    from services.portfolio_service import PortfolioService
    svc = PortfolioService()
    plants = svc.get_all_plants()
    return [PlantResponse(**p) for p in plants]


@app.get("/api/v1/plants/{plant_uid}/readings")
async def get_readings(
    plant_uid: str,
    start: datetime = Query(..., description="Start timestamp (ISO 8601)"),
    end: datetime = Query(..., description="End timestamp (ISO 8601)"),
):
    """Get readings for a plant within a time range."""
    from services.portfolio_service import PortfolioService
    svc = PortfolioService()
    data = svc.get_readings(plant_uid, start, end)
    if data is None:
        raise HTTPException(status_code=404, detail="Plant not found")
    return data


@app.get("/api/v1/portfolio/summary")
async def portfolio_summary(period: str = "Last 30 Days"):
    """Get portfolio summary KPIs."""
    from services.portfolio_service import PortfolioService
    svc = PortfolioService()
    return svc.get_summary(period)


@app.get("/health")
async def health():
    return {"status": "healthy"}
```

### Docker Integration

```yaml
# Addition to docker-compose.yml
  api:
    build: .
    command: uvicorn api.main:app --host 0.0.0.0 --port 8001
    ports:
      - "8001:8001"
    volumes:
      - solar_data:/root/.solar_toolkit
    environment:
      - ENVIRONMENT=production
```

### Acceptance Criteria

- [ ] FastAPI app with OpenAPI docs at `/docs`
- [ ] Plant listing, readings, portfolio summary endpoints
- [ ] API key authentication (simple header-based)
- [ ] Docker Compose sidecar deployment
- [ ] Read-only initially — no write endpoints

---

## Task 7.9: Anomaly Detection UI

**Goal:** Streamlit page for viewing and managing detected anomalies.

**Estimated Hours:** 6

### Layout

```
┌──────────────────────────────────────────────────────────────┐
│ 🔍 Anomaly Detection                                        │
├──────────────────────────────────────────────────────────────┤
│ Plant: [All Plants ▼]   Period: [Last 30 Days ▼]            │
│ Method: [All ▼]         Min Confidence: [0.5 ━━━━○━━━ 1.0]  │
│                                                              │
│ ┌──────────────────────────────────────────────────────┐     │
│ │ Timeline (scatter: x=time, y=metric, color=type)    │     │
│ │                                                      │     │
│ │     ●                                                │     │
│ │   ● ● ●        ●                    ●               │     │
│ │   ▲             ● ●                                 │     │
│ │     ‒ normal ‒ ‒ ‒ ‒ ‒ ‒ ‒ ‒ ‒ ‒ ‒ ‒ ‒ ‒ ‒ ‒     │     │
│ │                                                      │     │
│ └──────────────────────────────────────────────────────┘     │
│                                                              │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │ Anomaly List                                            │ │
│ │ ┌────────┬──────┬─────────┬──────┬──────────┬────────┐  │ │
│ │ │ Plant  │ Time │ Type    │ Conf │ Metric   │ Action │  │ │
│ │ ├────────┼──────┼─────────┼──────┼──────────┼────────┤  │ │
│ │ │ Oak... │ Jan5 │ Low PR  │ 0.92 │ PR=0.41  │ [View] │  │ │
│ │ │ Sun... │ Jan8 │ IRR Mis │ 0.78 │ Gen=50kW │ [View] │  │ │
│ │ └────────┴──────┴─────────┴──────┴──────────┴────────┘  │ │
│ └──────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

### Acceptance Criteria

- [ ] Filter by plant, period, method, confidence
- [ ] Timeline visualization of anomalies
- [ ] Drill-down to plant detail from anomaly

---

## Task 7.10: Financial Dashboard UI

**Goal:** Streamlit page for financial overview — revenue, budget, tariffs.

**Estimated Hours:** 6

### Layout

```
┌──────────────────────────────────────────────────────────────┐
│ 💰 Financial Overview                                        │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐        │
│ │ YTD Rev  │ │ Budget   │ │ Variance │ │ Avg Tariff│        │
│ │ £1.2M    │ │ £1.1M    │ │ +£100k   │ │ £45/MWh  │        │
│ │          │ │          │ │ +9.1%  🟢│ │          │        │
│ └──────────┘ └──────────┘ └──────────┘ └──────────┘        │
│                                                              │
│ ┌──────────────────────────────────────────────────────┐     │
│ │ Monthly Revenue: Actual vs Budget (bar chart)       │     │
│ │                                                      │     │
│ │  ██ budget  ██ actual                                │     │
│ │  ██ ██   ██ ██   ██ ██   ██ ██   ██                 │     │
│ │  Jan      Feb      Mar      Apr      May            │     │
│ └──────────────────────────────────────────────────────┘     │
│                                                              │
│ ┌──────────────────────────────────────────────────────┐     │
│ │ Plant Revenue Breakdown (table)                     │     │
│ │ Plant      │ Tariff  │ Gen MWh │ Revenue │ vs Bgt  │     │
│ │ Oakfield   │ £45/MWh │ 1,200   │ £54,000 │ +5% 🟢  │     │
│ │ Sunderland │ £50/MWh │ 800     │ £40,000 │ -3% 🟡  │     │
│ └──────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────┘
```

### Acceptance Criteria

- [ ] YTD and monthly revenue with budget comparison
- [ ] Bar chart: actual vs. budget per month
- [ ] Per-plant breakdown table
- [ ] Color-coded variance indicators

---

## Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| scikit-learn adds heavy dependency | Low | Medium | Make optional import; statistical detection works without it |
| Anomaly detection generates too many false positives | Medium | High | Start with high threshold (z=3); allow manual suppression |
| Financial data sensitive; access control critical | High | Medium | Per-plant permissions; audit log for financial access |
| PVsyst CSV format varies across versions | Medium | High | Flexible column mapping; manual mapping UI fallback |
| FastAPI sidecar adds deployment complexity | Medium | Low | Optional service; document deployment clearly |
| Tariff calculations complex (TOU, escalation) | Medium | Medium | Start with fixed tariff; add complexity incrementally |

---

## Definition of Done

- [ ] 3 anomaly detection methods implemented and tested
- [ ] Forecasting service with persistence and statistical methods
- [ ] Revenue tracking with fixed tariff support
- [ ] Budget vs. actual comparison with PVsyst import
- [ ] Per-plant access control enforced across all pages
- [ ] REST API running as sidecar with 4+ endpoints
- [ ] Anomaly detection UI with filtering and timeline
- [ ] Financial dashboard with revenue vs. budget chart
- [ ] 20+ unit tests across all new services
- [ ] scikit-learn optional (graceful fallback)
