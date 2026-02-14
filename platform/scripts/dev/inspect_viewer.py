
import sys
import os
import inspect
from unified_config import config

if str(config.SOLAR_TOOLKIT_PATH) not in sys.path:
    sys.path.insert(0, str(config.SOLAR_TOOLKIT_PATH))

try:
    from solar_toolkit.data_viewer import DataViewer
    print("--- AnalysisOrchestrator.run_fouling_analysis_from_db ---")
    try:
        from solar_toolkit.orchestrator import AnalysisOrchestrator
        print(inspect.getsource(AnalysisOrchestrator.run_fouling_analysis_from_db))
    except Exception as e:
        print(e)
        
except Exception as e:
    print(e)
