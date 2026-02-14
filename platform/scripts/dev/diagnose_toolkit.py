
import sys
import os
from unified_config import config

# Ensure we can import services
sys.path.append(os.getcwd())

print("Attempting to import services.toolkit_bridge...")
try:
    from services.toolkit_bridge import toolkit
    print(f"Toolkit imported. Available: {toolkit.is_available()}")
    if not toolkit.is_available():
        print("Toolkit is NOT available.")
        # Try to manually run the import block from bridge to see the error
        print("Re-running bridge import logic to capture error...")
        if str(config.SOLAR_TOOLKIT_PATH) not in sys.path:
            sys.path.insert(0, str(config.SOLAR_TOOLKIT_PATH))
        
        from solar_toolkit.orchestrator import AnalysisOrchestrator
        from solar_toolkit.data_viewer import DataViewer
        from solar_toolkit.config import settings as toolkit_settings
        print("Manual import successful (weird!)")
        
except Exception as e:
    print(f"Error importing/using toolkit: {e}")
    import traceback
    traceback.print_exc()
