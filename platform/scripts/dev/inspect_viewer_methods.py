
import sys
import inspect
from unified_config import config

sys.path.append(str(config.SOLAR_TOOLKIT_PATH))

try:
    from solar_toolkit.data_viewer import DataViewer
    print("--- Source of get_date_range ---")
    print(inspect.getsource(DataViewer.get_date_range))
    
    print("\n--- Source of get_readings_data (Snippet) ---")
    # We already saw this but good to double check the WHERE clause part again
    print(inspect.getsource(DataViewer.get_readings_data))
    
except Exception as e:
    print(f"Error: {e}")
