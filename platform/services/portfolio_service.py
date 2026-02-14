"""
Portfolio-level business logic.

Provides aggregated KPIs, plant statuses, and trend data.
Called by modules/dashboard.py — never import Streamlit here.

DESIGN NOTES FOR EXTRACTION:
- When adding FastAPI, expose this as GET /api/portfolio/summary
- Same service, different transport
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd

from services.alerts import AlertEngine, AlertRepository, AlertSeverity, AlertStatus
from services.database.repository import PlantRepository, ReadingsRepository
from services.logging import get_logger

logger = get_logger("services.portfolio")


@dataclass
class PortfolioSummary:
    """Portfolio-level KPI summary."""
    total_capacity_mwp: float = 0.0
    plant_count: int = 0
    total_generation_mwh: float = 0.0
    generation_delta_pct: float = 0.0
    fleet_pr_pct: float = 0.0
    pr_delta_pct: float = 0.0
    active_alerts: int = 0
    critical_alerts: int = 0


class PortfolioService:
    """Portfolio-level operations.
    
    All methods are framework-agnostic — no Streamlit imports.
    """

    def __init__(self):
        self._plants = PlantRepository()
        self._readings = ReadingsRepository()
        self._alerts = AlertRepository()

    # ── Public API ──────────────────────────────────────────────────

    def get_summary(self, time_range: str = "Last 24 Hours") -> PortfolioSummary:
        """Get aggregated portfolio KPIs."""
        start, end = self._parse_time_range(time_range)

        # Get all plants
        plants_df = self._plants.get_all()
        if plants_df.empty:
            return PortfolioSummary()

        total_capacity = plants_df["dc_size_kw"].sum() / 1000 if "dc_size_kw" in plants_df.columns else 0.0

        # Get generation data
        generation = self._get_total_generation(plants_df, start, end)
        prev_start = start - (end - start)
        prev_generation = self._get_total_generation(plants_df, prev_start, start)

        gen_delta = (
            ((generation - prev_generation) / prev_generation * 100)
            if prev_generation > 0 else 0.0
        )

        # Fleet PR calculation
        fleet_pr = self._calculate_fleet_pr(plants_df, start, end)

        return PortfolioSummary(
            total_capacity_mwp=total_capacity,
            plant_count=len(plants_df),
            total_generation_mwh=generation / 1000 if generation else 0.0,
            generation_delta_pct=gen_delta,
            fleet_pr_pct=fleet_pr,
            active_alerts=len(self._alerts.list_alerts(status=AlertStatus.ACTIVE)),
            critical_alerts=len(
                self._alerts.list_alerts(status=AlertStatus.ACTIVE, severity=AlertSeverity.CRITICAL)
            ),
        )

    def get_plant_statuses(self, time_range: str = "Last 24 Hours") -> list[dict[str, Any]]:
        """Get status for each plant."""
        start, end = self._parse_time_range(time_range)
        plants_df = self._plants.get_all()
        statuses: list[dict[str, Any]] = []

        if plants_df.empty:
            return statuses

        for _, plant in plants_df.iterrows():
            uid = plant.get("plant_uid", "")
            pr = self._get_plant_pr(uid, start, end)
            gen = self._get_plant_generation(uid, start, end)

            if pr is not None:
                if pr >= 85:
                    status = "excellent"
                elif pr >= 70:
                    status = "good"
                elif pr >= 50:
                    status = "warning"
                else:
                    status = "critical"
            else:
                status = "offline"

            statuses.append({
                "uid": uid,
                "name": plant.get("alias", plant.get("name", "Unknown")),
                "status": status,
                "pr": pr,
                "generation_mwh": (gen or 0) / 1000,
                "alerts": len(self._alerts.list_alerts(plant_uid=uid, status=AlertStatus.ACTIVE)),
                "lat": plant.get("latitude"),
                "lng": plant.get("longitude"),
                "capacity_kw": plant.get("dc_size_kw", 0),
            })

        return sorted(statuses, key=lambda p: p.get("pr") or 0, reverse=True)

    def get_generation_trend(self, days: int = 7) -> list[dict[str, Any]]:
        """Get daily generation trend for the portfolio."""
        end = datetime.now(UTC)
        start = end - timedelta(days=days)
        return self._get_daily_generation_trend(start, end)

    def get_alert_summary(self) -> list[dict[str, Any]]:
        """Get current active alert summary for dashboard panel."""
        alerts = self._alerts.list_alerts(status=AlertStatus.ACTIVE)
        grouped: dict[str, int] = {"critical": 0, "warning": 0, "info": 0}
        for alert in alerts:
            grouped[alert.severity.value] = grouped.get(alert.severity.value, 0) + 1
        return [
            {"severity": severity, "type": severity.title(), "count": count}
            for severity, count in grouped.items()
            if count > 0
        ]

    def evaluate_alerts(self, plant_uid: str | None = None) -> int:
        """Run alert rule evaluation and return number of triggered alerts."""
        engine = AlertEngine()
        alerts = engine.evaluate_plant(plant_uid) if plant_uid else engine.evaluate_all()
        return len(alerts)

    # ── Time Range Parsing ──────────────────────────────────────────

    @staticmethod
    def _parse_time_range(label: str) -> tuple[datetime, datetime]:
        now = datetime.now(UTC)
        if label == "Last 24 Hours":
            return now - timedelta(hours=24), now
        elif label == "Last 7 Days":
            return now - timedelta(days=7), now
        elif label == "Last 30 Days":
            return now - timedelta(days=30), now
        elif label == "Month to Date":
            return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0), now
        elif label == "Year to Date":
            return now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0), now
        return now - timedelta(hours=24), now

    # ── Private Calculation Methods ─────────────────────────────────

    def _get_total_generation(self, plants_df: pd.DataFrame, start: datetime, end: datetime) -> float:
        """Sum generation across all plants for the given period."""
        total = 0.0
        for _, plant in plants_df.iterrows():
            uid = plant.get("plant_uid", "")
            gen = self._get_plant_generation(uid, start, end)
            if gen:
                total += gen
        return total

    def _get_plant_generation(self, plant_uid: str, start: datetime, end: datetime) -> float | None:
        """Get total generation (kWh) for a plant over a period.
        
        Attempts to sum an energy column from the readings table.
        Returns None if no data available.
        """
        try:
            df = self._readings.get_readings(plant_uid, start=start, end=end)
            if df.empty:
                return None
            # Try common energy/power column names
            energy_cols = [c for c in df.columns if any(
                kw in c.lower() for kw in ["energy", "generation", "yield", "kwh", "e_grid"]
            )]
            if energy_cols:
                return float(df[energy_cols[0]].sum())
            # If no energy column, try power columns and estimate
            power_cols = [c for c in df.columns if any(
                kw in c.lower() for kw in ["power", "pac", "p_grid", "kw"]
            )]
            if power_cols:
                # Rough estimate: power * time_interval
                return float(df[power_cols[0]].sum()) * 0.25  # Assume 15-min intervals
            return None
        except Exception as e:
            logger.warning("generation_calc_failed", plant_uid=plant_uid, error=str(e))
            return None

    def _get_plant_pr(self, plant_uid: str, start: datetime, end: datetime) -> float | None:
        """Calculate Performance Ratio for a plant.
        
        PR = Actual Energy / (POA Irradiance × Capacity × time)
        Returns None if insufficient data.
        """
        try:
            df = self._readings.get_readings(plant_uid, start=start, end=end)
            if df.empty:
                return None

            # Look for PR column directly
            pr_cols = [c for c in df.columns if "pr" in c.lower() or "performance_ratio" in c.lower()]
            if pr_cols:
                pr_val = df[pr_cols[0]].mean()
                return float(pr_val) if pd.notna(pr_val) else None

            return None
        except Exception as e:
            logger.warning("pr_calc_failed", plant_uid=plant_uid, error=str(e))
            return None

    def _get_daily_generation_trend(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        """Get daily total generation across all plants."""
        try:
            plants_df = self._plants.get_all()
            if plants_df.empty:
                return []

            # Collect readings from all plants
            all_readings: list[pd.DataFrame] = []
            for _, plant in plants_df.iterrows():
                uid = plant.get("plant_uid", "")
                try:
                    df = self._readings.get_readings(uid, start=start, end=end)
                    if not df.empty:
                        all_readings.append(df)
                except Exception:
                    continue

            if not all_readings:
                return []

            combined = pd.concat(all_readings, ignore_index=True)

            # Find timestamp column
            ts_col = None
            for candidate in ["timestamp", "ts", "date", "datetime"]:
                if candidate in combined.columns:
                    ts_col = candidate
                    break
            if ts_col is None:
                return []

            combined[ts_col] = pd.to_datetime(combined[ts_col])
            combined["date"] = combined[ts_col].dt.date

            # Find energy column
            energy_cols = [c for c in combined.columns if any(
                kw in c.lower() for kw in ["energy", "generation", "yield", "kwh", "e_grid"]
            )]
            if not energy_cols:
                return []

            daily = combined.groupby("date")[energy_cols[0]].sum().reset_index()
            daily.columns = ["date", "generation_kwh"]

            return [
                {
                    "date": str(row["date"]),
                    "generation_mwh": row["generation_kwh"] / 1000,
                }
                for _, row in daily.iterrows()
            ]
        except Exception as e:
            logger.warning("daily_trend_failed", error=str(e))
            return []

    def _calculate_fleet_pr(self, plants_df: pd.DataFrame, start: datetime, end: datetime) -> float:
        """Capacity-weighted fleet PR."""
        total_weighted_pr = 0.0
        total_capacity = 0.0
        cap_col = "dc_size_kw" if "dc_size_kw" in plants_df.columns else "capacity_kw"

        for _, plant in plants_df.iterrows():
            uid = plant.get("plant_uid", "")
            pr = self._get_plant_pr(uid, start, end)
            cap = plant.get(cap_col, 0) or 0
            if pr is not None and cap > 0:
                total_weighted_pr += pr * cap
                total_capacity += cap

        return total_weighted_pr / total_capacity if total_capacity > 0 else 0.0
