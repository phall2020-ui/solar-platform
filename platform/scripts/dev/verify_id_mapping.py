
import sys
from unified_config import config
import pandas as pd

# Ensure paths
if str(config.SOLAR_TOOLKIT_PATH) not in sys.path:
    sys.path.insert(0, str(config.SOLAR_TOOLKIT_PATH))
if str(config.MONTHLY_REPORTING_PATH) not in sys.path:
    sys.path.insert(0, str(config.MONTHLY_REPORTING_PATH))

try:
    from services.toolkit_bridge import toolkit
    from services.reporting_bridge import reporting
    
    print("Checking Plant ID Alignment...")
    
    # 1. Get all sites from Reporting DB
    df = reporting.get_table_data("solar_data")
    if df is not None:
        reporting_sites = sorted(df['Site'].unique())
        print(f"\nReporting DB has {len(reporting_sites)} sites.")
    else:
        print("Could not fetch reporting sites.")
        reporting_sites = []

    # 2. Check resolution for each
    print(f"\n{'Reporting Alias':<40} | {'Resolves To Toolkit UID':<40} | {'Status'}")
    print("-" * 100)
    
    valid_count = 0
    for site in reporting_sites:
        uid = toolkit.resolve_plant_uid(site)
        status = "MATCH" if uid else "NO MATCH"
        if uid: valid_count += 1
        print(f"{site:<40} | {str(uid):<40} | {status}")
        
    print("-" * 100)
    print(f"Summary: {valid_count}/{len(reporting_sites)} sites map to Toolkit UIDs.")

except Exception as e:
    print(f"Error: {e}")
