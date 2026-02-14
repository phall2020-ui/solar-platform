import sys
import os
from unified_config import config

# Path
toolkit_path = str(config.SOLAR_TOOLKIT_PATH)
app_path = os.path.join(toolkit_path, 'streamlit_app.py')

print(f"Reading: {app_path}")

try:
    # Use utf-8-sig to handle BOM that caused previous error
    with open(app_path, 'r', encoding='utf-8-sig') as f:
        lines = f.readlines()
        
    print(f"\n--- Total Lines: {len(lines)} ---")
    
    # 1. Print Imports
    print("\n--- Imports ---")
    for line in lines[:50]:
        if line.startswith('import') or line.startswith('from'):
            print(line.strip())

    # 2. Look for UI Structure (tabs, sidebar, etc)
    print("\n--- UI Structure Hints ---")
    for i, line in enumerate(lines):
        if any(keyword in line for keyword in ['st.tabs', 'st.sidebar', 'render_', 'tab1', 'tab_']):
            print(f"{i+1}: {line.strip()}")

except Exception as e:
    print(f"Error reading file: {e}")
