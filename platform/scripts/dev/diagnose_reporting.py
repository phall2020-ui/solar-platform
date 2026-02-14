
import sys
import os
import inspect
from unified_config import config

if str(config.MONTHLY_REPORTING_PATH) not in sys.path:
    sys.path.insert(0, str(config.MONTHLY_REPORTING_PATH))

try:
    from analysis import SolarDataAnalyzer
    print(f"SolarDataAnalyzer init signature: {inspect.signature(SolarDataAnalyzer.__init__)}")
except Exception as e:
    print(f"Error inspecting SolarDataAnalyzer: {e}")
