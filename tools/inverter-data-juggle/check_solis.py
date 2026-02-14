import os
import sys
# Ensure imports work
sys.path.insert(0, '.')
from solis_api import get_station_month

# Stations from mapping
# Smithy's: 1298491919449898612
# Sofina: 1298491919449993293

SITES = {
    "Smithys": "1298491919449898612",
    "Sofina": "1298491919449993293"
}

def check_solis():
    print("Checking Solis API...")
    for name, site_id in SITES.items():
        print(f"  {name} ({site_id})...")
        try:
            # Check Feb 2026 data
            data = get_station_month(site_id, "2026-02")
            if data:
                 print(f"    Success: Retrieved data.")
                 # print(data)
            else:
                 print(f"    Failed: No data returned.")
        except Exception as e:
            print(f"    Error: {e}")

if __name__ == "__main__":
    check_solis()
