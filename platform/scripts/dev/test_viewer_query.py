
import sys
import os
import pandas as pd
from unified_config import config

# Ensure imports work
if str(config.SOLAR_TOOLKIT_PATH) not in sys.path:
    sys.path.insert(0, str(config.SOLAR_TOOLKIT_PATH))

from solar_toolkit.data_viewer import DataViewer
from solar_toolkit.config import settings as toolkit_settings

print(f"Using DB: {toolkit_settings.DB_PATH}")
viewer = DataViewer(db_path=toolkit_settings.DB_PATH)

plant_uid = "AMP:00001"
start_date = "2025-09-09"
end_date = "2025-12-08"

print(f"Querying for {plant_uid} from {start_date} to {end_date}")

try:
    df, count = viewer.get_readings_data(
        plant_uid=plant_uid,
        start_date=start_date,
        end_date=end_date,
        limit=100  # Small limit just to check existence
    )
    print(f"Result count: {count}")
    print(f"DataFrame shape: {df.shape}")
    if not df.empty:
        print("Sample data:")
        print(df[['ts']].head())
    else:
        print("DataFrame is empty.")
        
except Exception as e:
    print(f"Error querying: {e}")
