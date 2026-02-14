import sys
import os
from unified_config import config

# Path
toolkit_path = str(config.SOLAR_TOOLKIT_PATH)
app_path = os.path.join(toolkit_path, 'streamlit_app.py')

def extract_block(start_line, end_line, output_file):
    print(f"Extracting lines {start_line}-{end_line} to {output_file}...")
    try:
        with open(app_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            
        block = lines[start_line-1:end_line]
        
        with open(output_file, 'w', encoding='utf-8') as out:
            out.writelines(block)
            
        print("Done.")
    except Exception as e:
        print(f"Error: {e}")

# Based on previous structure analysis
# Header: 1-223
# Plants: 224-444
# POA: 445-802
# Fouling: 803-990
# Shading: 991-1706
# Clipping: 1707-1852
# Overview: 1853-2229 (Overview + DB Viewer)

target_dir = r"c:/Users/PeterHall/OneDrive - AMPYR IDEA UK Ltd/Python scripts/unified_app/legacy_extracts"
if not os.path.exists(target_dir):
    os.makedirs(target_dir)

extract_block(1, 223, os.path.join(target_dir, "header_utils.py"))
extract_block(224, 444, os.path.join(target_dir, "plant_mgmt.py"))
extract_block(445, 802, os.path.join(target_dir, "poa.py"))
extract_block(803, 990, os.path.join(target_dir, "fouling.py"))
extract_block(991, 1706, os.path.join(target_dir, "shading.py"))
extract_block(1707, 1852, os.path.join(target_dir, "clipping.py"))
extract_block(1853, 2229, os.path.join(target_dir, "overview.py"))
