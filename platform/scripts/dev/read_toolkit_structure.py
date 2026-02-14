import sys
import os
from unified_config import config

# Path
toolkit_path = str(config.SOLAR_TOOLKIT_PATH)
app_path = os.path.join(toolkit_path, 'streamlit_app.py')

print(f"Reading: {app_path}")

try:
    with open(app_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
        
    print(f"\n--- Total Lines: {len(lines)} ---")
    
    # Capture the sidebar radio list
    capturing = False
    options = []
    
    for line in lines:
        if 'st.sidebar.radio' in line:
            capturing = True
            print(f"DEBUG: Found radio: {line.strip()}")
        
        if capturing:
            if ']' in line:
                capturing = False
            
            # Simple parsing of string literals
            parts = line.split('"')
            for i, part in enumerate(parts):
                # If it's a string literal (odd index if split by ")
                if i % 2 == 1:
                    clean = part.strip()
                    if clean and clean not in ['Go to', 'Navigation']:
                        options.append(clean)
    
    print("\n--- Legacy Pages Detected ---")
    for opt in options:
        print(f"- {opt}")
        
    # Also look for the "if selection ==" blocks to find code boundaries
    print("\n--- Code Boundaries ---")
    for i, line in enumerate(lines):
        if 'if selection ==' in line or 'elif selection ==' in line:
            print(f"Line {i+1}: {line.strip()}")

except Exception as e:
    print(f"Error reading file: {e}")
