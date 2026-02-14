
import sys
import os
from unified_config import config

path = config.SOLAR_TOOLKIT_PATH
print(f"Configured Path: {path}")
print(f"Exists? {path.exists()}")

if path.exists():
    print(f"Contents: {os.listdir(path)}")
    
    app_file = path / "streamlit_app.py"
    print(f"App file: {app_file}")
    print(f"App file exists? {app_file.exists()}")
