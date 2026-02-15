"""Comparative analysis engine (DuckDB repository based)."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import pandas as pd

from solar_platform.analysis.base import AnalysisEngine, AnalysisResult
from solar_platform.analysis.helpers import (
    coerce_datetime,
    date_bounds_or_default,
    detect_time_column,
    estimate_energy_kwh,
    find_numeric_column,
)
from solar_platform.db.engine import DatabaseEngine
from solar_platform.db.repository import PlantRepository, ReadingsRepository


class ComparativeEngine(AnalysisEngine):
    """Cross-plant comparison service with no Streamlit dependencies."""

    def __init__(self, engine: DatabaseEngine | None = None):
        self._plants = PlantRepository(engine=engine)
        self._readings = ReadingsRepository(engine=engine)

    @property
    def analysis_type(self) -> str:
        return "comparative"

    def run(
        self,
        plant_uid: str = "",
        start: datetime | None = None,
        end: datetime | None = None,
        **params: Any,
    ) -> AnalysisResult:
        t0 = time.perf_counter()
        start, end = date_bounds_or_default(start, end, days=30)

        plants_df = self._plants.list_all()
        if plants_df.empty:
            return AnalysisResult(
                analysis_type=self.analysis_type,
                plant_uid=plant_uid,
                start=start,
                end=end,
                warnings=["No plants found."],
            )

        uid_col = "plant_uid" if "plant_uid" in plants_df.columns else "uid"
        name_col = "alias" if "alias" in plants_df.columns else "plant_name"

        requested_uids: list[str] = params.get("plant_uids", []) or []
        if requested_uids:
            plants_df = plants_df[plants_df[uid_col].isin(requested_uids)]

        summaries: list[dict[str, Any]] = []
        daily_points: list[pd.DataFrame] = []

        for _, plant in plants_df.iterrows():
            uid = str(plant.get(uid_col, ""))
            if not uid:
                continue
            name = str(plant.get(name_col, uid))
            df = self._readings.get_readings(uid, start=start, end=end)
            if df.empty:
                continue

            ts_col = detect_time_column(df)
            if not ts_col:
                continue
            df = coerce_datetime(df, ts_col)

            power_col = find_numeric_column(df, ["activepower", "power", "pac", "p_grid", "kw"])
            pr_col = find_numeric_column(df, ["performance_ratio", "pr"])
            availability_col = find_numeric_column(df, ["availability"])

            energy_kwh = estimate_energy_kwh(df, power_col, ts_col) if power_col else 0.0
            mean_pr = float(pd.to_numeric(df[pr_col], errors="coerce").mean()) if pr_col else None
            if availability_col:
                availability_pct = float(pd.to_numeric(df[availability_col], errors="coerce").mean())
            else:
                availability_pct = float(pd.to_numeric(df[power_col], errors="coerce").notna().mean() * 100) if power_col else None

            clipping_loss_pct = 0.0
            if power_col:
                p = pd.to_numeric(df[power_col], errors="coerce")
                threshold = float(p.quantile(0.98))
                clipped_share = float((p >= threshold).mean())
                clipping_loss_pct = clipped_share * 4.0

            summaries.append(
                {
                    "plant_uid": uid,
                    "plant_name": name,
                    "Energy (kWh)": round(energy_kwh, 2),
                    "PR (%)": round(mean_pr, 2) if mean_pr is not None else None,
                    "Availability (%)": round(availability_pct, 2) if availability_pct is not None else None,
                    "Clipping Loss (%)": round(clipping_loss_pct, 2),
                }
            )

            if power_col:
                daily = (
                    df.assign(date=df[ts_col].dt.date)
                    .groupby("date", as_index=False)[power_col]
                    .sum()
                    .rename(columns={power_col: "energy_proxy"})
                )
                daily["plant_uid"] = uid
                daily["plant_name"] = name
                daily_points.append(daily)

        if not summaries:
            return AnalysisResult(
                analysis_type=self.analysis_type,
                plant_uid=plant_uid,
                start=start,
                end=end,
                warnings=["No readings available for selected plants."],
            )

        summary_df = pd.DataFrame(summaries)
        timeseries = pd.concat(daily_points, ignore_index=True) if daily_points else None

        result = AnalysisResult(
            analysis_type=self.analysis_type,
            plant_uid=plant_uid,
            start=start,
            end=end,
            summary={
                "plants_compared": int(summary_df["plant_uid"].nunique()),
                "total_energy_kwh": float(summary_df["Energy (kWh)"].fillna(0.0).sum()),
                "mean_pr_pct": float(summary_df["PR (%)"].dropna().mean()) if summary_df["PR (%)"].notna().any() else None,
            },
            table=summary_df,
            timeseries=timeseries,
            calculation_seconds=round(time.perf_counter() - t0, 3),
        )
        return result
