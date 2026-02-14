"""Loss waterfall engine that composes analysis engines."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import pandas as pd

from services.analysis.base import AnalysisEngine, AnalysisResult
from services.analysis.clipping import ClippingEngine
from services.analysis.curtailment import CurtailmentEngine
from services.analysis.fouling import FoulingEngine
from services.analysis.shading import ShadingEngine
from services.analysis.thermal import ThermalLossEngine
from services.database.engine import DatabaseEngine


class LossWaterfallEngine(AnalysisEngine):
    """Aggregate losses from all individual engines into one breakdown."""

    def __init__(self, engine: DatabaseEngine | None = None):
        self._clipping = ClippingEngine(engine=engine)
        self._curtailment = CurtailmentEngine(engine=engine)
        self._shading = ShadingEngine(engine=engine)
        self._fouling = FoulingEngine(engine=engine)
        self._thermal = ThermalLossEngine(engine=engine)

    @property
    def analysis_type(self) -> str:
        return "loss_waterfall"

    def run(self, plant_uid: str, start: datetime | None, end: datetime | None, **params: Any) -> AnalysisResult:
        t0 = time.perf_counter()
        clipping = self._clipping.run(plant_uid, start, end, **params)
        curtailment = self._curtailment.run(plant_uid, start, end, **params)
        shading = self._shading.run(plant_uid, start, end, **params)
        fouling = self._fouling.run(plant_uid, start, end, **params)
        thermal = self._thermal.run(plant_uid, start, end, **params)

        losses = {
            "clipping": float(clipping.losses.get("clipping", 0.0)),
            "curtailment": float(curtailment.losses.get("curtailment", 0.0)),
            "shading": float(shading.losses.get("shading", 0.0)),
            "fouling": float(fouling.losses.get("fouling", 0.0)),
            "thermal": float(thermal.losses.get("thermal", 0.0)),
        }
        total_loss = float(sum(losses.values()))

        table = pd.DataFrame(
            [{"loss_type": name, "loss_pct": value} for name, value in losses.items()]
        ).sort_values("loss_pct", ascending=False)

        warnings = clipping.warnings + curtailment.warnings + shading.warnings + fouling.warnings + thermal.warnings

        return AnalysisResult(
            analysis_type=self.analysis_type,
            plant_uid=plant_uid,
            start=clipping.start,
            end=clipping.end,
            summary={
                "total_estimated_loss_pct": round(total_loss, 2),
                "largest_loss_component": table.iloc[0]["loss_type"] if not table.empty else None,
            },
            table=table,
            losses=losses,
            warnings=warnings,
            calculation_seconds=round(time.perf_counter() - t0, 3),
        )
