import sys
from unified_config import config
import inspect

# Add path
report_path = str(config.MONTHLY_REPORTING_PATH)
if report_path not in sys.path:
    sys.path.insert(0, report_path)

try:
    import ui_tabs
    print("\n--- ui_tabs module ---")
    print(dir(ui_tabs))
    # Look for functions that start with render
    for name, obj in inspect.getmembers(ui_tabs):
        if name.startswith('render') and inspect.isfunction(obj):
            print(f"\nFunction: {name}")
            print(inspect.signature(obj))
            print(obj.__doc__)
            
except ImportError as e:
    print(f"Could not import ui_tabs: {e}")

try:
    import app
    # This might be tricky if app.py runs code on import, but usually it's safeish
    print("\n--- app module (legacy) ---")
    print(dir(app))
except ImportError as e:
    print(f"Could not import app: {e}")
