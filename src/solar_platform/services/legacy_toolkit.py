"""
Legacy Solar Toolkit Services
Wraps the initialization and shared utilities from the original Solar Toolkit app.
"""
import functools
import io
import logging
import sys

from solar_platform.config import SOLAR_TOOLKIT_PATH

logger = logging.getLogger(__name__)

# Ensure toolkit path is available for imports
toolkit_path = str(SOLAR_TOOLKIT_PATH)
if toolkit_path not in sys.path:
    sys.path.insert(0, toolkit_path)

# Import legacy core modules
try:
    from solar_toolkit.config import settings
    from solar_toolkit.orchestrator import AnalysisOrchestrator
    from solar_toolkit.utils import setup_logging
    
    LEGACY_AVAILABLE = True
except ImportError as e:
    LEGACY_AVAILABLE = False
    print(f"Legacy Toolkit Import Error: {e}")

# Global state for logs
log_capture_string = io.StringIO()

def initialize_logging():
    """Setup logging to capture output."""
    if not LEGACY_AVAILABLE: return
    
    setup_logging(verbose=True, log_to_file=None)
    capture_handler = logging.StreamHandler(log_capture_string)
    capture_handler.setLevel(logging.INFO)
    logging.getLogger("solar_toolkit").addHandler(capture_handler)
    logging.getLogger().addHandler(capture_handler)

@functools.lru_cache(maxsize=1)
def get_orchestrator():
    """Initializes the Orchestrator (cached resource)."""
    if not LEGACY_AVAILABLE: return None
    return AnalysisOrchestrator(db_path=settings.DB_PATH)

def clear_logs():
    """Clears the captured log output."""
    log_capture_string.truncate(0)
    log_capture_string.seek(0)
    
def get_logs() -> str:
    """Return the captured log output as a string."""
    return log_capture_string.getvalue()
