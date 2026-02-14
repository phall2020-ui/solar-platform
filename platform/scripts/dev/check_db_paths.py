
import sys
import os
from pathlib import Path

# Setup paths
current_dir = Path(os.getcwd())
parent_dir = current_dir.parent
toolkit_path = parent_dir / "Solar Toolkit"
sys.path.insert(0, str(toolkit_path))

try:
    from solar_toolkit.config import settings
    print(f"Legacy DB_PATH: {settings.DB_PATH}")
    
    # Check unified config as well
    sys.path.append(str(current_dir))
    from unified_config import config
    print(f"Unified TOOLKIT_DB: {config.TOOLKIT_DB}")
    
    # Check equality
    legacy_str = str(settings.DB_PATH).lower().replace('\\', '/')
    unified_str = str(config.TOOLKIT_DB).lower().replace('\\', '/')
    
    if legacy_str == unified_str:
        print("✅ Paths match")
    else:
        print("❌ Paths DO NOT match")

except ImportError as e:
    print(f"Import failed: {e}")
