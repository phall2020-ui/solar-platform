
import sys
import os
from unified_config import config

path = config.MONTHLY_REPORTING_PATH
print(f"Reporting Path: {path}")

ui_tabs_path = path / "ui_tabs.py"
print(f"ui_tabs path: {ui_tabs_path}")

if ui_tabs_path.exists():
    with open(ui_tabs_path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    print("\n--- ui_tabs.py (Delete related lines) ---")
    lines = content.splitlines()
    for i, line in enumerate(lines):
        if "delete" in line.lower() or "clear" in line.lower() or "remove" in line.lower():
            print(f"{i+1}: {line.strip()}")
            
    # Also define a function to clear the DB
    print("\n--- Analyzing DB tables ---")
    db_path = config.REPORTING_DB
    print(f"DB Path: {db_path}") 
else:
    print("ui_tabs.py not found.")
