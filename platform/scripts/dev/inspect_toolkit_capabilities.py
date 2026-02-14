
import sys
from pathlib import Path
import os
import inspect

# Setup paths based on standard config
# unified_app is at .../unified_app
# Solar Toolkit should be at .../Solar Toolkit
current_dir = Path(os.getcwd())
parent_dir = current_dir.parent
toolkit_path = parent_dir / "Solar Toolkit"

print(f"Adding to path: {toolkit_path}")
sys.path.insert(0, str(toolkit_path))




try:
    from solar_toolkit.data_viewer import DataViewer
    print("\n[OK] Successfully imported DataViewer")
    
    methods_to_inspect = [
        "get_readings_data",
        "get_unique_device_ids",
        "get_date_range"
    ]
    
    print("\nMethod Signatures:")
    for method_name in methods_to_inspect:
        if hasattr(DataViewer, method_name):
            method = getattr(DataViewer, method_name)
            sig = inspect.signature(method)
            print(f" - {method_name}{sig}")
        else:
            print(f" - {method_name} NOT FOUND")

except ImportError as e:
    print(f"\n[X] Failed to import: {e}")




