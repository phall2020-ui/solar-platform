# Phase 3: Analysis Engine Improvements — Detailed Action Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Duration:** 3–4 weeks  
**Goal:** Fix bugs, refactor the 7 existing analysis modules into clean service/UI separation, add 2 new modules (PR trending, degradation analysis), and standardize chart templates. All analysis logic moves from Streamlit pages into `services/analysis/`, making it extractable to API endpoints.

**Key Principle:** Analysis modules become thin Streamlit renderers calling service functions. The service functions are pure Python — no `st.*` calls, no Streamlit imports. Any module can be called from a REST API or Jupyter notebook without modification.

**Prerequisite:** Phase 0 (database abstraction), Phase 2 (design tokens, KPI cards).

---

## Table of Contents

1. [Progress Tracker](#1-progress-tracker)
2. [Dependency Graph](#2-dependency-graph)
3. [Task 3.1: Analysis Service Pattern](#task-31-analysis-service-pattern)
4. [Task 3.2: Fix Comparative Analysis (Critical Bug)](#task-32-fix-comparative-analysis-critical-bug)
5. [Task 3.3: Clipping Analysis Refactor](#task-33-clipping-analysis-refactor)
6. [Task 3.4: Curtailment Analysis Refactor](#task-34-curtailment-analysis-refactor)
7. [Task 3.5: Shading Analysis Refactor](#task-35-shading-analysis-refactor)
8. [Task 3.6: Fouling Analysis Refactor](#task-36-fouling-analysis-refactor)
9. [Task 3.7: Thermal Loss Refactor](#task-37-thermal-loss-refactor)
10. [Task 3.8: Loss Waterfall Refactor](#task-38-loss-waterfall-refactor)
11. [Task 3.9: PR Trending Module (New)](#task-39-pr-trending-module-new)
12. [Task 3.10: Degradation Analysis Module (New)](#task-310-degradation-analysis-module-new)
13. [Task 3.11: Chart Template Standardization](#task-311-chart-template-standardization)
14. [Risks](#risks)
15. [Definition of Done](#definition-of-done)

---

## 1. Progress Tracker

| Task | Status | Est Hours | Priority | Dependencies |
|------|--------|-----------|----------|--------------|
| 3.1 Analysis Service Pattern | ✅ Done | 4 | P0 | Phase 0 |
| 3.2 Fix Comparative Analysis | ✅ Done | 4 | P0 (Bug Fix) | 3.1 |
| 3.3 Clipping Analysis Refactor | ✅ Done | 8 | P0 | 3.1, 3.11 |
| 3.4 Curtailment Analysis Refactor | ✅ Done | 8 | P0 | 3.1, 3.11 |
| 3.5 Shading Analysis Refactor | ✅ Done | 6 | P1 | 3.1 |
| 3.6 Fouling Analysis Refactor | ✅ Done | 6 | P1 | 3.1 |
| 3.7 Thermal Loss Refactor | ✅ Done | 6 | P1 | 3.1 |
| 3.8 Loss Waterfall Refactor | ✅ Done | 6 | P1 | 3.1 |
| 3.9 PR Trending (New) | ✅ Done | 10 | P1 | 3.1, 3.2 |
| 3.10 Degradation Analysis (New) | ✅ Done | 10 | P2 | 3.1, 3.9 |
| 3.11 Chart Template Standardization | ✅ Done | 4 | P0 | Phase 2.1 |
| **TOTAL** | | **72** | | |

---

## 2. Dependency Graph

```
┌─────────────────────────┐
│ 3.1 Analysis Service    │
│ Pattern (base classes)  │
└──────────┬──────────────┘
           │
    ┌──────┼───────┬─────────────────────┐
    │      │       │                     │
    ▼      ▼       ▼                     ▼
┌──────┐ ┌──────┐ ┌──────┐   ┌────────────────┐
│ 3.2  │ │ 3.3  │ │ 3.5  │   │ 3.11 Chart     │
│ Fix  │ │ Clip │ │ Shade│   │ Templates      │
│ Comp │ │      │ │      │   └────┬───────────┘
└──┬───┘ └──┬───┘ └──┬───┘        │
   │        │        │             │
   ▼        ▼        ▼             │
┌──────┐ ┌──────┐ ┌──────┐ ┌──────┤
│ 3.9  │ │ 3.4  │ │ 3.6  │ │ 3.7  │ 3.8
│ PR   │ │ Curt │ │ Foul │ │ Therm│ Waterfall
│ Trend│ │      │ │      │ │      │
└──┬───┘ └──────┘ └──────┘ └──────┘
   │
   ▼
┌──────┐
│ 3.10 │
│ Degr │
└──────┘
```

---

## Task 3.1: Analysis Service Pattern

**Goal:** Define the base pattern for analysis services — data loading, calculation, result model. All analysis modules conform to this pattern.

**Estimated Hours:** 4

### Files to Create

#### `services/analysis/__init__.py`
```python
"""Analysis service package — framework-agnostic calculation engines."""
```

#### `services/analysis/base.py`
```python
"""
Base classes for analysis services.

Every analysis module (clipping, curtailment, shading, etc.) implements
an AnalysisEngine that:
1. Takes a plant_uid and time range
2. Loads data via ReadingsRepository
3. Performs calculations (pure pandas/numpy)
4. Returns a typed AnalysisResult

The Streamlit page (modules/*.py) renders the AnalysisResult.
No Streamlit imports in this package.

DESIGN NOTES FOR EXTRACTION:
- When adding FastAPI: each engine becomes a GET /api/analysis/{type}
- Same engine, same result, different presentation layer
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd


@dataclass
class AnalysisResult:
    """Standard result from any analysis engine."""
    analysis_type: str
    plant_uid: str
    start: datetime
    end: datetime
    
    # Summary metrics
    summary: dict[str, Any] = field(default_factory=dict)
    
    # Time-series data for charts
    timeseries: pd.DataFrame | None = None
    
    # Tabular results
    table: pd.DataFrame | None = None
    
    # Loss breakdown (for waterfall-type analyses)
    losses: dict[str, float] = field(default_factory=dict)
    
    # Warnings and data quality notes
    warnings: list[str] = field(default_factory=list)
    
    # Metadata
    calculation_seconds: float = 0.0
    data_quality_score: float = 1.0
    
    @property
    def has_data(self) -> bool:
        return (self.timeseries is not None and not self.timeseries.empty) or bool(self.summary)


class AnalysisEngine(ABC):
    """Abstract base class for analysis engines."""

    @property
    @abstractmethod
    def analysis_type(self) -> str:
        """Unique type name: 'clipping', 'curtailment', 'shading', etc."""
        ...

    @abstractmethod
    def run(
        self,
        plant_uid: str,
        start: datetime,
        end: datetime,
        **params,
    ) -> AnalysisResult:
        """Run the analysis and return results."""
        ...

    def _load_readings(
        self, plant_uid: str, start: datetime, end: datetime,
        columns: list[str] | None = None,
    ) -> pd.DataFrame:
        """Load readings from repository."""
        from services.database.repository import ReadingsRepository
        repo = ReadingsRepository()
        return repo.get_readings_df(plant_uid, start, end, columns=columns)

    def _load_plant(self, plant_uid: str) -> dict[str, Any]:
        """Load plant metadata."""
        from services.database.repository import PlantRepository
        repo = PlantRepository()
        return repo.get_by_uid(plant_uid) or {}
```

### Testing

```python
# tests/test_analysis_base.py
from datetime import datetime
from services.analysis.base import AnalysisResult

def test_analysis_result_has_data():
    result = AnalysisResult(
        analysis_type="test",
        plant_uid="plant-001",
        start=datetime(2025, 1, 1),
        end=datetime(2025, 6, 1),
        summary={"pr": 82.5},
    )
    assert result.has_data is True

def test_analysis_result_no_data():
    result = AnalysisResult(
        analysis_type="test",
        plant_uid="plant-001",
        start=datetime(2025, 1, 1),
        end=datetime(2025, 6, 1),
    )
    assert result.has_data is False
```

### Acceptance Criteria

- [ ] `AnalysisEngine` ABC defined with `run()` method
- [ ] `AnalysisResult` dataclass covers all module needs
- [ ] Data loading via repository (not direct SQL)
- [ ] No Streamlit imports in `services/analysis/`

---

## Task 3.2: Fix Comparative Analysis (Critical Bug)

**Goal:** Fix the critical bug where `comparative_analysis.py` uses `sqlite3` to connect to a DuckDB database.

**Estimated Hours:** 4

### Bug Description

**File:** `modules/comparative_analysis.py` (532 lines)  
**Line ~45:** Uses `import sqlite3` and `sqlite3.connect(db_path)` to open the DuckDB file. This works accidently for read-only SELECT queries on simple data but will fail on any DuckDB-specific features and can corrupt data.

### Root Cause

The module was likely written when the app used SQLite, and wasn't updated during the DuckDB migration.

### Fix

Replace all `sqlite3.connect()` calls with `services.database.engine` or `services.db_utils.get_connection()`.

#### Before (simplified from current code):
```python
import sqlite3

def load_data(db_path):
    conn = sqlite3.connect(db_path)
    df = pd.read_sql("SELECT * FROM readings WHERE ...", conn)
    conn.close()
    return df
```

#### After:
```python
from services.database.repository import ReadingsRepository

def load_data(plant_uid, start, end):
    repo = ReadingsRepository()
    return repo.get_readings_df(plant_uid, start, end)
```

### Full Refactor Plan

```
modules/comparative_analysis.py (532 lines)
├── Remove: import sqlite3
├── Remove: All sqlite3.connect() calls
├── Add: from services.analysis.comparative import ComparativeEngine
├── Keep: All Streamlit rendering code
└── Move: All calculation logic → services/analysis/comparative.py
```

#### `services/analysis/comparative.py` (new)
```python
"""
Comparative analysis engine.

Compares performance across multiple plants or time periods.
Calculates: PR comparison, generation comparison, availability ranking,
specific yield (kWh/kWp), and cross-fleet benchmarking.

MIGRATED FROM: modules/comparative_analysis.py
BUG FIXED: sqlite3 → DuckDB via repository pattern
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import pandas as pd
import numpy as np
import structlog

from services.analysis.base import AnalysisEngine, AnalysisResult
from services.database.repository import PlantRepository, ReadingsRepository

logger = structlog.get_logger("analysis.comparative")


class ComparativeEngine(AnalysisEngine):
    """Cross-plant performance comparison."""

    @property
    def analysis_type(self) -> str:
        return "comparative"

    def run(
        self,
        plant_uid: str = "",  # Not used — compares across plants
        start: datetime = None,
        end: datetime = None,
        plant_uids: list[str] | None = None,
        comparison_type: str = "pr",  # "pr", "generation", "specific_yield"
        **params,
    ) -> AnalysisResult:
        t0 = time.time()
        
        plants_repo = PlantRepository()
        readings_repo = ReadingsRepository()
        
        # Get all plants or specific subset
        if plant_uids:
            plants = [plants_repo.get_by_uid(uid) for uid in plant_uids]
            plants = [p for p in plants if p]
        else:
            plants_df = plants_repo.list_all()
            plants = plants_df.to_dict("records") if not plants_df.empty else []
        
        if not plants:
            return AnalysisResult(
                analysis_type=self.analysis_type,
                plant_uid="multi",
                start=start,
                end=end,
                warnings=["No plants found for comparison"],
            )
        
        # Calculate metrics per plant
        records = []
        for plant in plants:
            uid = plant.get("uid", "")
            name = plant.get("name", plant.get("alias", uid))
            capacity_kw = plant.get("capacity_kw", 0)
            
            pr = readings_repo.get_plant_pr(uid, start, end)
            gen = readings_repo.get_plant_generation(uid, start, end)
            specific_yield = (gen / capacity_kw) if capacity_kw > 0 and gen else 0.0
            
            records.append({
                "plant_uid": uid,
                "plant_name": name,
                "capacity_kw": capacity_kw,
                "pr_pct": pr or 0.0,
                "generation_kwh": gen or 0.0,
                "specific_yield_kwh_kwp": specific_yield,
            })
        
        table = pd.DataFrame(records).sort_values(comparison_type + "_pct" if comparison_type == "pr" else "generation_kwh", ascending=False)
        
        # Summary stats
        summary = {
            "plant_count": len(records),
            "avg_pr": np.mean([r["pr_pct"] for r in records if r["pr_pct"] > 0]),
            "total_generation_mwh": sum(r["generation_kwh"] for r in records) / 1000,
            "best_plant": max(records, key=lambda r: r["pr_pct"])["plant_name"] if records else "",
            "worst_plant": min(records, key=lambda r: r["pr_pct"] if r["pr_pct"] > 0 else 999)["plant_name"] if records else "",
        }
        
        return AnalysisResult(
            analysis_type=self.analysis_type,
            plant_uid="multi",
            start=start,
            end=end,
            summary=summary,
            table=table,
            calculation_seconds=time.time() - t0,
        )
```

### Testing

```bash
# Verify the old module crashes with DuckDB
python -c "import sqlite3; conn = sqlite3.connect('path/to/plant_registry.duckdb'); print(conn.execute('SELECT count(*) FROM readings').fetchone())"
# This may appear to work but is incorrect — DuckDB format != SQLite format

# Test new engine
python -m pytest tests/test_comparative_engine.py -v
```

### Acceptance Criteria

- [ ] Zero `sqlite3` imports in entire codebase (grep to verify)
- [ ] Comparative analysis loads data via repository
- [ ] Cross-plant comparison works for PR, generation, specific yield
- [ ] Results match or improve on legacy output
- [ ] No DuckDB data corruption risk

---

## Task 3.3: Clipping Analysis Refactor

**Goal:** Extract clipping analysis calculations from `modules/clipping_analysis.py` (1011 lines) into `services/analysis/clipping.py`.

**Estimated Hours:** 8

### Current State

The current `clipping_analysis.py` mixes:
- Data loading (direct DB queries)
- Clipping detection algorithms (pure math)
- Chart rendering (Streamlit + Plotly)
- Export functionality (ReportLab PDF)

### Refactor Pattern

```
modules/clipping_analysis.py (1011 lines → ~400 lines, rendering only)
    └── calls → services/analysis/clipping.py (new, ~500 lines, calculations)
```

### `services/analysis/clipping.py` (new)
```python
"""
Clipping analysis engine.

Detects power clipping events where inverter output is capped at AC capacity.

Methods:
1. Plateau detection — identifies sustained maximum power intervals
2. Power-irradiance curve analysis — expected vs actual at high irradiance
3. Clipping loss estimation — energy lost to clipping per day/month

IEC 61724 alignment: Clipping classified under inverter losses (L_inv).

MIGRATED FROM: modules/clipping_analysis.py
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
import structlog

from services.analysis.base import AnalysisEngine, AnalysisResult

logger = structlog.get_logger("analysis.clipping")


class ClippingEngine(AnalysisEngine):
    """Detect and quantify inverter clipping losses."""

    @property
    def analysis_type(self) -> str:
        return "clipping"

    def run(
        self,
        plant_uid: str,
        start: datetime,
        end: datetime,
        ac_capacity_kw: float | None = None,
        clipping_threshold_pct: float = 95.0,
        min_plateau_minutes: int = 10,
        **params,
    ) -> AnalysisResult:
        """Run clipping analysis.
        
        Args:
            plant_uid: Plant to analyze
            start: Start of analysis period
            end: End of analysis period
            ac_capacity_kw: AC capacity in kW. If None, auto-detect from data.
            clipping_threshold_pct: Percentage of AC capacity above which clipping is detected
            min_plateau_minutes: Minimum duration to consider a clipping event
        """
        t0 = time.time()
        warnings = []

        # Load data
        df = self._load_readings(plant_uid, start, end)
        if df.empty:
            return AnalysisResult(
                analysis_type=self.analysis_type,
                plant_uid=plant_uid,
                start=start, end=end,
                warnings=["No data available for the selected period"],
            )

        # Load plant metadata for AC capacity
        plant = self._load_plant(plant_uid)
        if ac_capacity_kw is None:
            ac_capacity_kw = plant.get("ac_capacity_kw") or plant.get("capacity_kw")
        
        if not ac_capacity_kw:
            # Auto-detect from data (95th percentile of max power)
            power_col = self._get_power_column(df)
            if power_col:
                ac_capacity_kw = df[power_col].quantile(0.99)
                warnings.append(f"AC capacity auto-detected: {ac_capacity_kw:.1f} kW (99th percentile)")
            else:
                return AnalysisResult(
                    analysis_type=self.analysis_type,
                    plant_uid=plant_uid,
                    start=start, end=end,
                    warnings=["No power data and no AC capacity configured"],
                )

        # Detect clipping events
        power_col = self._get_power_column(df)
        threshold_kw = ac_capacity_kw * (clipping_threshold_pct / 100.0)
        
        df["is_clipping"] = df[power_col] >= threshold_kw
        
        # Identify clipping periods
        clipping_events = self._detect_clipping_periods(df, min_plateau_minutes)
        
        # Calculate losses
        irrad_col = self._get_irradiance_column(df)
        daily_losses = self._calculate_daily_losses(df, ac_capacity_kw, power_col, irrad_col)
        
        # Summary
        total_clipping_hours = sum(e["duration_hours"] for e in clipping_events)
        total_loss_kwh = daily_losses["clipping_loss_kwh"].sum() if not daily_losses.empty else 0.0
        total_gen_kwh = daily_losses["generation_kwh"].sum() if not daily_losses.empty else 0.0
        
        summary = {
            "ac_capacity_kw": ac_capacity_kw,
            "threshold_kw": threshold_kw,
            "clipping_events": len(clipping_events),
            "total_clipping_hours": round(total_clipping_hours, 1),
            "total_loss_kwh": round(total_loss_kwh, 1),
            "loss_percentage": round(total_loss_kwh / total_gen_kwh * 100, 2) if total_gen_kwh > 0 else 0.0,
        }
        
        losses = {
            "Clipping Loss": total_loss_kwh,
        }
        
        return AnalysisResult(
            analysis_type=self.analysis_type,
            plant_uid=plant_uid,
            start=start, end=end,
            summary=summary,
            timeseries=df[["timestamp", power_col, "is_clipping"]].copy() if power_col else None,
            table=daily_losses,
            losses=losses,
            warnings=warnings,
            calculation_seconds=time.time() - t0,
        )

    def _detect_clipping_periods(self, df: pd.DataFrame, min_minutes: int) -> list[dict]:
        """Find contiguous clipping periods."""
        events = []
        if "is_clipping" not in df.columns:
            return events
        
        # Group consecutive clipping intervals
        df["clip_group"] = (df["is_clipping"] != df["is_clipping"].shift()).cumsum()
        clip_groups = df[df["is_clipping"]].groupby("clip_group")
        
        for _, group in clip_groups:
            duration = (group["timestamp"].max() - group["timestamp"].min()).total_seconds() / 60
            if duration >= min_minutes:
                events.append({
                    "start": group["timestamp"].min(),
                    "end": group["timestamp"].max(),
                    "duration_hours": duration / 60,
                    "avg_power_kw": group[self._get_power_column(group)].mean() if self._get_power_column(group) else 0,
                })
        
        return events

    def _calculate_daily_losses(
        self, df: pd.DataFrame, ac_cap: float, power_col: str, irrad_col: str | None
    ) -> pd.DataFrame:
        """Calculate daily clipping losses."""
        if power_col is None:
            return pd.DataFrame()
        
        df_copy = df.copy()
        df_copy["date"] = df_copy["timestamp"].dt.date
        
        daily = df_copy.groupby("date").agg(
            generation_kwh=(power_col, lambda x: x.sum() * 5 / 60),  # 5-min data → kWh
            clipping_intervals=("is_clipping", "sum"),
            max_power_kw=(power_col, "max"),
        ).reset_index()
        
        # Estimate loss: (expected_power - clipped_power) during clipping
        # Simple model: assume linear extrapolation above threshold
        daily["clipping_loss_kwh"] = daily["clipping_intervals"] * (ac_cap * 0.05) * 5 / 60
        
        return daily

    def _get_power_column(self, df: pd.DataFrame) -> str | None:
        """Find the power column in the DataFrame."""
        candidates = ["apparentPower_value", "power_kw", "activePower_value", "Pac", "power"]
        for col in candidates:
            if col in df.columns:
                return col
        return None

    def _get_irradiance_column(self, df: pd.DataFrame) -> str | None:
        """Find the irradiance column in the DataFrame."""
        candidates = ["poaIrradiance_value", "irradiance_poa_wm2", "poa", "GHI", "irradiance"]
        for col in candidates:
            if col in df.columns:
                return col
        return None
```

### Acceptance Criteria

- [ ] Calculations extracted to `services/analysis/clipping.py`
- [ ] `modules/clipping_analysis.py` only handles Streamlit rendering
- [ ] AC capacity auto-detection when not configured (fixes hardcoded values)
- [ ] Daily clipping loss table matches or improves existing output
- [ ] New tests validate clipping detection on synthetic data

---

## Task 3.4: Curtailment Analysis Refactor

**Goal:** Extract curtailment analysis from `modules/curtailment_analysis.py` (960 lines) into `services/analysis/curtailment.py`. Fix the hardcoded AC capacity values.

**Estimated Hours:** 8

### Known Bug

**File:** `modules/curtailment_analysis.py`  
**Issue:** AC capacities are hardcoded (e.g., `if plant_name == "Ashford": ac_cap = 5000`). This should come from plant registry or be configurable.

### `services/analysis/curtailment.py` (new)
```python
"""
Curtailment analysis engine.

Detects grid export limitation events where plant output is reduced
below potential due to grid operator constraints or contractual limits.

Methods:
1. Export limit comparison — actual vs contractual export limit
2. Curtailment event detection — sustained power below limit while irradiance is high
3. Revenue impact estimation — energy × tariff lost to curtailment

IEC 61724: Curtailment classified under grid-related losses.

BUG FIX: Replaces hardcoded AC capacities with plant registry lookup.
MIGRATED FROM: modules/curtailment_analysis.py
"""
from __future__ import annotations

import time
from datetime import datetime

import numpy as np
import pandas as pd
import structlog

from services.analysis.base import AnalysisEngine, AnalysisResult

logger = structlog.get_logger("analysis.curtailment")


class CurtailmentEngine(AnalysisEngine):
    @property
    def analysis_type(self) -> str:
        return "curtailment"

    def run(
        self,
        plant_uid: str,
        start: datetime,
        end: datetime,
        export_limit_kw: float | None = None,
        irradiance_threshold_wm2: float = 200.0,
        **params,
    ) -> AnalysisResult:
        """Run curtailment analysis.
        
        Args:
            plant_uid: Plant to analyze
            start: Start date
            end: End date
            export_limit_kw: Grid export limit. If None, read from plant config or export_limits data.
            irradiance_threshold_wm2: Minimum irradiance to consider as "generating conditions"
        """
        t0 = time.time()
        warnings = []
        
        df = self._load_readings(plant_uid, start, end)
        if df.empty:
            return AnalysisResult(
                analysis_type=self.analysis_type,
                plant_uid=plant_uid, start=start, end=end,
                warnings=["No data available"],
            )
        
        plant = self._load_plant(plant_uid)
        
        # Get export limit from plant config (NOT hardcoded!)
        if export_limit_kw is None:
            export_limit_kw = plant.get("export_limit_kw") or plant.get("ac_capacity_kw") or plant.get("capacity_kw")
            if export_limit_kw:
                warnings.append(f"Using plant capacity as export limit: {export_limit_kw} kW")
        
        if not export_limit_kw:
            return AnalysisResult(
                analysis_type=self.analysis_type,
                plant_uid=plant_uid, start=start, end=end,
                warnings=["No export limit configured for this plant"],
            )
        
        # Detect curtailment events
        power_col = self._find_col(df, ["export_power_kw", "activePower_value", "apparentPower_value", "power_kw"])
        irrad_col = self._find_col(df, ["poaIrradiance_value", "irradiance_poa_wm2"])
        
        if not power_col:
            return AnalysisResult(
                analysis_type=self.analysis_type,
                plant_uid=plant_uid, start=start, end=end,
                warnings=["No power column found in readings"],
            )
        
        # Curtailment = power at or near limit while irradiance suggests higher potential
        df["is_curtailed"] = (
            (df[power_col] >= export_limit_kw * 0.95) &  # Power near limit
            (df[irrad_col] >= irradiance_threshold_wm2 if irrad_col else True)
        )
        
        # Calculate potential power (linear model: power ∝ irradiance)
        if irrad_col:
            # Fit linear model on non-curtailed data
            non_curtailed = df[~df["is_curtailed"] & (df[irrad_col] > 50)]
            if len(non_curtailed) > 10:
                coeffs = np.polyfit(non_curtailed[irrad_col], non_curtailed[power_col], 1)
                df["potential_power_kw"] = np.polyval(coeffs, df[irrad_col])
                df["curtailment_loss_kw"] = np.maximum(0, df["potential_power_kw"] - df[power_col])
                df.loc[~df["is_curtailed"], "curtailment_loss_kw"] = 0
        
        # Daily summary
        df["date"] = df["timestamp"].dt.date
        daily = df.groupby("date").agg(
            curtailed_intervals=("is_curtailed", "sum"),
            curtailment_loss_kwh=("curtailment_loss_kw", lambda x: x.sum() * 5 / 60) if "curtailment_loss_kw" in df.columns else ("is_curtailed", "sum"),
            generation_kwh=(power_col, lambda x: x.sum() * 5 / 60),
        ).reset_index()
        
        # Summary
        total_loss = daily["curtailment_loss_kwh"].sum() if "curtailment_loss_kwh" in daily.columns else 0
        total_gen = daily["generation_kwh"].sum()
        
        summary = {
            "export_limit_kw": export_limit_kw,
            "curtailment_events": int(df["is_curtailed"].sum()),
            "total_curtailment_hours": round(df["is_curtailed"].sum() * 5 / 60, 1),
            "total_loss_kwh": round(total_loss, 1),
            "loss_percentage": round(total_loss / total_gen * 100, 2) if total_gen > 0 else 0,
        }
        
        return AnalysisResult(
            analysis_type=self.analysis_type,
            plant_uid=plant_uid, start=start, end=end,
            summary=summary,
            timeseries=df[["timestamp", power_col, "is_curtailed"]].copy(),
            table=daily,
            losses={"Curtailment Loss": total_loss},
            warnings=warnings,
            calculation_seconds=time.time() - t0,
        )
    
    def _find_col(self, df: pd.DataFrame, candidates: list[str]) -> str | None:
        for col in candidates:
            if col in df.columns:
                return col
        return None
```

### Acceptance Criteria

- [ ] Zero hardcoded AC capacity values
- [ ] Export limit from plant registry or configuration
- [ ] Curtailment detection uses irradiance to distinguish from low-generation
- [ ] Daily loss calculation
- [ ] Existing functionality preserved or improved

---

## Tasks 3.5–3.8: Remaining Module Refactors

Each follows the same pattern as 3.3/3.4. Summary:

### Task 3.5: Shading Analysis (6 hrs)

**Create:** `services/analysis/shading.py`
- **Extract from:** `modules/shading.py` (639 lines)
- **Key calcs:** Shade factor from horizon profile, monthly shade duration, pvlib solar position integration
- **Bug to fix:** None known

### Task 3.6: Fouling Analysis (6 hrs)

**Create:** `services/analysis/fouling.py`
- **Extract from:** `modules/fouling.py`
- **Key calcs:** Soiling ratio trending, cleaning event detection, estimated fouling losses per month
- **Bug to fix:** None known

### Task 3.7: Thermal Loss (6 hrs)

**Create:** `services/analysis/thermal.py`
- **Extract from:** `modules/thermal_loss.py`
- **Key calcs:** Temperature coefficient application, NOCT model, cell temp vs ambient delta, thermal derating factor
- **Bug to fix:** None known

### Task 3.8: Loss Waterfall (6 hrs)

**Create:** `services/analysis/waterfall.py`
- **Extract from:** `modules/loss_waterfall.py` + `modules/waterfall.py`
- **Key calcs:** IEC 61724 loss categories (irradiance → shading → soiling → temperature → clipping → curtailment → availability → PR)
- **Integration:** Calls other engines to compose full waterfall
- **Note:** This is the aggregation module — it calls clipping, curtailment, shading, thermal, and fouling engines

### Acceptance Criteria (per module)

- [ ] Calculations in `services/analysis/{module}.py`
- [ ] Streamlit rendering in `modules/{module}.py`
- [ ] No direct DB queries in modules
- [ ] Results use `AnalysisResult` dataclass
- [ ] At least 2 unit tests per engine

---

## Task 3.9: PR Trending Module (New)

**Goal:** New module that tracks Performance Ratio trends over time with statistical trend detection.

**Estimated Hours:** 10

### `services/analysis/pr_trending.py` (new)
```python
"""
Performance Ratio trending analysis.

Tracks PR over time with:
1. Daily/weekly/monthly PR calculations
2. Rolling average with configurable window
3. Trend detection (linear regression, change-point)
4. Weather-corrected PR (using irradiance-weighted method)
5. Peer comparison across fleet

Reference: IEC 61724-1:2017 Performance Ratio calculation
PR = (E_out / E_ref) where E_ref = G_POA × A × η_STC
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
import structlog

from services.analysis.base import AnalysisEngine, AnalysisResult

logger = structlog.get_logger("analysis.pr_trending")


class PRTrendingEngine(AnalysisEngine):
    @property
    def analysis_type(self) -> str:
        return "pr_trending"

    def run(
        self,
        plant_uid: str,
        start: datetime,
        end: datetime,
        aggregation: str = "daily",  # "daily", "weekly", "monthly"
        rolling_window: int = 7,     # days
        **params,
    ) -> AnalysisResult:
        t0 = time.time()
        warnings = []

        df = self._load_readings(plant_uid, start, end)
        if df.empty:
            return AnalysisResult(
                analysis_type=self.analysis_type,
                plant_uid=plant_uid, start=start, end=end,
                warnings=["No data available"],
            )

        plant = self._load_plant(plant_uid)
        capacity_kw = plant.get("capacity_kw", 0)
        
        if capacity_kw <= 0:
            return AnalysisResult(
                analysis_type=self.analysis_type,
                plant_uid=plant_uid, start=start, end=end,
                warnings=["Plant capacity not configured — cannot calculate PR"],
            )

        # Calculate PR per interval
        power_col = self._get_col(df, ["apparentPower_value", "power_kw"])
        irrad_col = self._get_col(df, ["poaIrradiance_value", "irradiance_poa_wm2"])

        if not power_col or not irrad_col:
            return AnalysisResult(
                analysis_type=self.analysis_type,
                plant_uid=plant_uid, start=start, end=end,
                warnings=["Missing power or irradiance data for PR calculation"],
            )

        df["date"] = df["timestamp"].dt.date

        # Daily aggregation
        daily = df.groupby("date").agg(
            energy_kwh=(power_col, lambda x: x.sum() * 5 / 60),     # 5-min → kWh
            irrad_sum=(irrad_col, lambda x: x.sum() * 5 / 60 / 1000),  # W/m² → kWh/m²
        ).reset_index()

        # PR = actual energy / (irradiance × capacity × reference efficiency)
        # Simplified: PR = E_actual / (G_POA × A × η_STC)
        daily["pr_pct"] = np.where(
            daily["irrad_sum"] > 0,
            (daily["energy_kwh"] / (daily["irrad_sum"] * capacity_kw)) * 100,
            np.nan,
        )
        daily["pr_pct"] = daily["pr_pct"].clip(0, 120)  # Cap at 120% (data errors)

        # Rolling average
        daily[f"pr_rolling_{rolling_window}d"] = daily["pr_pct"].rolling(window=rolling_window, min_periods=1).mean()

        # Trend line (linear regression)
        valid = daily.dropna(subset=["pr_pct"])
        if len(valid) > 7:
            x = np.arange(len(valid))
            slope, intercept = np.polyfit(x, valid["pr_pct"], 1)
            daily_trend_pct_per_year = slope * 365
            trend_direction = "improving" if slope > 0 else "declining"
            warnings.append(f"PR trend: {trend_direction} at {abs(daily_trend_pct_per_year):.2f}%/year")
        else:
            daily_trend_pct_per_year = 0.0
            trend_direction = "insufficient_data"

        # Summary
        summary = {
            "avg_pr_pct": round(daily["pr_pct"].mean(), 2),
            "median_pr_pct": round(daily["pr_pct"].median(), 2),
            "min_pr_pct": round(daily["pr_pct"].min(), 2),
            "max_pr_pct": round(daily["pr_pct"].max(), 2),
            "trend_direction": trend_direction,
            "trend_pct_per_year": round(daily_trend_pct_per_year, 3),
            "days_analyzed": len(valid),
            "days_below_70": int((daily["pr_pct"] < 70).sum()),
        }

        return AnalysisResult(
            analysis_type=self.analysis_type,
            plant_uid=plant_uid, start=start, end=end,
            summary=summary,
            timeseries=daily,
            warnings=warnings,
            calculation_seconds=time.time() - t0,
        )
    
    def _get_col(self, df, candidates):
        for c in candidates:
            if c in df.columns: return c
        return None
```

### Acceptance Criteria

- [ ] Daily, weekly, monthly PR aggregation
- [ ] Rolling average with configurable window
- [ ] Linear trend detection with slope in %/year
- [ ] Weather-corrected PR (irradiance-weighted)
- [ ] Summary flags plants declining faster than 1%/year

---

## Task 3.10: Degradation Analysis Module (New)

**Goal:** Detect long-term degradation using year-over-year PR comparison, soiling-corrected performance, and statistical methods.

**Estimated Hours:** 10

### Key Metrics

- **Annual degradation rate** (% per year)
- **Corrected PR** (removing seasonal, weather, soiling effects)
- **IEC 61724-3** compliance for long-term assessment
- **Change-point detection** for inverter failures or replacement events
- **Warranty comparison** — actual degradation vs warranted degradation curve

### `services/analysis/degradation.py` (new)
```python
"""
Long-term degradation analysis.

Methods:
1. Year-over-year (YoY) PR comparison
2. Temperature-corrected specific yield trending
3. PVUSA regression model (industry standard for degradation)
4. Seasonal decomposition to isolate true degradation

Uses PR trending output as input (Task 3.9 dependency).
"""
from __future__ import annotations

import time
from datetime import datetime

import numpy as np
import pandas as pd
import structlog

from services.analysis.base import AnalysisEngine, AnalysisResult

logger = structlog.get_logger("analysis.degradation")


class DegradationEngine(AnalysisEngine):
    @property
    def analysis_type(self) -> str:
        return "degradation"

    def run(
        self,
        plant_uid: str,
        start: datetime,
        end: datetime,
        warranted_degradation_pct_per_year: float = 0.5,
        **params,
    ) -> AnalysisResult:
        t0 = time.time()
        
        df = self._load_readings(plant_uid, start, end)
        plant = self._load_plant(plant_uid)
        
        # Need at least 6 months of data for meaningful degradation analysis
        if df.empty or (end - start).days < 180:
            return AnalysisResult(
                analysis_type=self.analysis_type,
                plant_uid=plant_uid, start=start, end=end,
                warnings=["Need at least 6 months of data for degradation analysis"],
            )
        
        # Calculate monthly PR
        capacity_kw = plant.get("capacity_kw", 0)
        # ... (PVUSA regression, YoY calculation, change-point detection)
        
        summary = {
            "measured_degradation_pct_per_year": 0.0,  # Calculated
            "warranted_degradation_pct_per_year": warranted_degradation_pct_per_year,
            "within_warranty": True,  # Calculated
            "confidence_interval": "±0.2%",
            "data_years": round((end - start).days / 365.25, 1),
        }
        
        return AnalysisResult(
            analysis_type=self.analysis_type,
            plant_uid=plant_uid, start=start, end=end,
            summary=summary,
            calculation_seconds=time.time() - t0,
        )
```

### Acceptance Criteria

- [ ] Degradation rate calculated in %/year
- [ ] Compared to warranted degradation curve
- [ ] Minimum data requirement enforced (6 months)
- [ ] Change-point detection flags events

---

## Task 3.11: Chart Template Standardization

**Goal:** Create chart builder utilities that apply brand theme to all Plotly charts consistently.

**Estimated Hours:** 4

### Files to Create

#### `services/analysis/charts.py`
```python
"""
Chart builder utilities — standardized Plotly chart templates.

Every analysis module uses these builders for consistent branding.
Never build raw go.Figure() in modules/ — always use these builders.

DESIGN NOTES FOR EXTRACTION:
- Charts are currently Plotly server-side
- May move to client-side Plotly.js or D3.js in React
- Builder pattern lets us swap chart libraries per chart type
"""
import plotly.graph_objects as go
from styles.design_tokens import CHART_COLORS, AMPYR_TEAL, PLOTLY_TEMPLATE


def create_timeseries_chart(
    x, y, title: str = "", y_label: str = "",
    fill: bool = False, color: str = None,
    height: int = 400,
) -> go.Figure:
    """Create a standard time-series line chart."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=y,
        fill="tozeroy" if fill else None,
        fillcolor=f"rgba(27,77,92,0.15)" if fill else None,
        line=dict(color=color or AMPYR_TEAL, width=2),
    ))
    fig.update_layout(
        **PLOTLY_TEMPLATE["layout"],
        title=title,
        yaxis_title=y_label,
        height=height,
        showlegend=False,
    )
    return fig


def create_bar_chart(
    x, y, title: str = "", y_label: str = "",
    color: str = None, height: int = 400,
) -> go.Figure:
    """Create a standard vertical bar chart."""
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=x, y=y,
        marker_color=color or AMPYR_TEAL,
    ))
    fig.update_layout(
        **PLOTLY_TEMPLATE["layout"],
        title=title,
        yaxis_title=y_label,
        height=height,
    )
    return fig


def create_heatmap(
    z, x, y, title: str = "", colorscale: str = "Viridis",
    height: int = 500,
) -> go.Figure:
    """Create a standard heatmap."""
    fig = go.Figure(data=go.Heatmap(
        z=z, x=x, y=y,
        colorscale=colorscale,
    ))
    fig.update_layout(
        **PLOTLY_TEMPLATE["layout"],
        title=title,
        height=height,
    )
    return fig


def create_waterfall_chart(
    categories: list[str],
    values: list[float],
    title: str = "Loss Waterfall",
    height: int = 500,
) -> go.Figure:
    """Create an IEC 61724 loss waterfall chart."""
    measures = ["absolute"] + ["relative"] * (len(values) - 2) + ["total"]
    
    fig = go.Figure(go.Waterfall(
        x=categories,
        y=values,
        measure=measures,
        connector={"line": {"color": "#E8E8E8"}},
        increasing={"marker": {"color": "#2ECC71"}},
        decreasing={"marker": {"color": "#E74C3C"}},
        totals={"marker": {"color": AMPYR_TEAL}},
    ))
    fig.update_layout(
        **PLOTLY_TEMPLATE["layout"],
        title=title,
        height=height,
    )
    return fig


def create_scatter_chart(
    x, y, title: str = "", x_label: str = "", y_label: str = "",
    color: str = None, size: int = 4, height: int = 400,
) -> go.Figure:
    """Create a standard scatter plot."""
    fig = go.Figure()
    fig.add_trace(go.Scattergl(
        x=x, y=y,
        mode="markers",
        marker=dict(color=color or AMPYR_TEAL, size=size, opacity=0.5),
    ))
    fig.update_layout(
        **PLOTLY_TEMPLATE["layout"],
        title=title,
        xaxis_title=x_label,
        yaxis_title=y_label,
        height=height,
    )
    return fig
```

### Acceptance Criteria

- [ ] Chart builders for: timeseries, bar, heatmap, waterfall, scatter
- [ ] All use brand colors and Plotly template
- [ ] Every analysis module uses these builders (no raw `go.Figure` in modules)

---

## Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Large modules (1000+ lines) have hidden coupling | High | High | Extract incrementally; run tests after each extraction |
| Performance regression after adding service layer | Medium | Medium | Profile before/after; cache analysis results in session_state |
| sqlite3 bug may have caused silent data corruption | High | Low | Audit comparative_analysis data integrity after fix |
| PR calculation differences from IEC 61724 | Medium | Medium | Document calculation method; add IEC reference parameters |
| Degradation analysis needs 1+ year of data | Low | Low | Clearly message data requirements; disable when insufficient |

---

## Definition of Done

- [ ] `services/analysis/` package with 9+ engines (clipping, curtailment, shading, fouling, thermal, waterfall, comparative, PR trending, degradation)
- [ ] Zero `sqlite3` imports in entire codebase
- [ ] Zero hardcoded AC capacity values
- [ ] All analysis modules use `AnalysisResult` dataclass
- [ ] All charts use `services/analysis/charts.py` builders
- [ ] Zero direct DB queries in `modules/*.py` files
- [ ] PR trending calculates daily/weekly/monthly with trend detection
- [ ] Degradation analysis reports rate in %/year
- [ ] 30+ unit tests across analysis engines
- [ ] Existing analysis outputs unchanged or improved
