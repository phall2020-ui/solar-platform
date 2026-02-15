from __future__ import annotations

import runpy
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "app"
APP_MAIN = APP_DIR / "main.py"

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

runpy.run_path(str(APP_MAIN), run_name="__main__")