import sys
import os
import inspect
from unified_config import config

# Add path
toolkit_path = str(config.SOLAR_TOOLKIT_PATH)
if toolkit_path not in sys.path:
    sys.path.insert(0, toolkit_path)

print(f"Path: {toolkit_path}")

# 1. List files
try:
    print("\n--- Files in Solar Toolkit ---")
    files = os.listdir(toolkit_path)
    print(files)
except Exception as e:
    print(f"Cannot list files: {e}")

# 2. Check for main app file (streamlit_app.py or app.py)
potential_apps = ['streamlit_app.py', 'app.py', 'main.py']
for app_file in potential_apps:
    full_path = os.path.join(toolkit_path, app_file)
    if os.path.exists(full_path):
        print(f"\n--- Found Main App: {app_file} ---")
        try:
            # We can't easily import a file with dashes or spaces without importlib
            # But we can read its content to see imports
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read(1000) # Read first 1000 chars
                print(content)
        except Exception as e:
            print(f"Error reading app file: {e}")

# 3. Inspect 'ui' or 'pages' directory if exists
for subdir in ['ui', 'pages', 'modules']:
    full_path = os.path.join(toolkit_path, subdir)
    if os.path.exists(full_path) and os.path.isdir(full_path):
        print(f"\n--- Files in {subdir} ---")
        print(os.listdir(full_path))
