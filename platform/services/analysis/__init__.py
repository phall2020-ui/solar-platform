"""Framework-agnostic analysis services."""

from services.analysis.base import AnalysisEngine, AnalysisResult
from services.analysis.clipping import ClippingEngine
from services.analysis.comparative import ComparativeEngine
from services.analysis.curtailment import CurtailmentEngine
from services.analysis.degradation import DegradationEngine
from services.analysis.fouling import FoulingEngine
from services.analysis.pr_trending import PRTrendingEngine
from services.analysis.shading import ShadingEngine
from services.analysis.thermal import ThermalLossEngine
from services.analysis.waterfall import LossWaterfallEngine

__all__ = [
    "AnalysisEngine",
    "AnalysisResult",
    "ComparativeEngine",
    "ClippingEngine",
    "CurtailmentEngine",
    "ShadingEngine",
    "FoulingEngine",
    "ThermalLossEngine",
    "LossWaterfallEngine",
    "PRTrendingEngine",
    "DegradationEngine",
]
