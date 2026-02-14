import sys
import os
from unified_config import config

# Path
toolkit_path = str(config.SOLAR_TOOLKIT_PATH)
app_path = os.path.join(toolkit_path, 'streamlit_app.py')

print(f"Reading head of: {app_path}")

try:
    with open(app_path, 'r', encoding='utf-8', errors='ignore') as f:
        # Read first 223 lines (approx based on previous scan)
        lines = [f.readline() for _ in range(224)]
        
    print(f"\n--- Shared Code Analysis ---")
    
    # Check for functions
    for line in lines:
        if line.startswith('def ') or line.startswith('class '):
            print(line.strip())
            
    # Check for important global variables
    for line in lines:
        if lines and '=' in line and not line.startswith(' ') and not line.startswith('def') and not line.startswith('import'):
             # Very simple heuristic
             print(f"Global? {line.strip()}")

except Exception as e:
    print(f"Error reading file: {e}")
