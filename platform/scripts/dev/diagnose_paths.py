
import sys
import os
from pathlib import Path
from unified_config import config
import traceback

print(f"Monthly Reporting Path: {config.MONTHLY_REPORTING_PATH}")

if str(config.MONTHLY_REPORTING_PATH) not in sys.path:
    sys.path.insert(0, str(config.MONTHLY_REPORTING_PATH))

try:
    print("Importing data_access...")
    from data_access import SolarDataExtractor
    print("Successfully imported SolarDataExtractor")
except Exception:
    traceback.print_exc()

try:
    print("Importing analysis...")
    from analysis import SolarDataAnalyzer
    print("Successfully imported SolarDataAnalyzer")
except Exception:
    traceback.print_exc()
