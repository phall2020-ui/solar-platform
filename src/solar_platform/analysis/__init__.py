"""Framework-agnostic analysis services."""

from solar_platform.analysis.base import AnalysisEngine, AnalysisResult
from solar_platform.analysis.clipping import ClippingEngine
from solar_platform.analysis.comparative import ComparativeEngine
from solar_platform.analysis.curtailment import CurtailmentEngine
from solar_platform.analysis.degradation import DegradationEngine
from solar_platform.analysis.fouling import FoulingEngine
from solar_platform.analysis.pr_trending import PRTrendingEngine
from solar_platform.analysis.shading import ShadingEngine
from solar_platform.analysis.thermal import ThermalLossEngine
from solar_platform.analysis.waterfall import LossWaterfallEngine

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
