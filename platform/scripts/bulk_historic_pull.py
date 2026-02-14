#!/usr/bin/env python3
"""
Bulk Historic Data Pull for All Sites.
Pulls missing data from April 1, 2025 to the present.
Uses adaptive chunking and optimized database storage.
"""
import sys
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

# Add project root and Solar Toolkit to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "Solar Toolkit"))

from solar_toolkit.utils import setup_logging
setup_logging(verbose=False)

# Target start date
START_DATE = datetime(2025, 4, 1)
END_DATE = datetime.now()

# Large sites that require 1-day chunks to avoid 413 error
LARGE_SITES = ["AMP:00001", "AMP:00020"]

def main():
    from services import toolkit
    
    if not toolkit.is_available():
        print("ERROR: Toolkit not available. Check configuration.")
        sys.exit(1)
    
    plants = toolkit.get_plants()
    if not plants:
        print("No registered plants found.")
        return
        
    print("=" * 70)
    print("BULK HISTORIC DATA PULL (FROM APR 2025)")
    print("=" * 70)
    print(f"Plants to process: {len(plants)}")
    print(f"Date range: {START_DATE.strftime('%Y-%m-%d')} to {END_DATE.strftime('%Y-%m-%d')}")
    print("=" * 70)
    
    grand_total_readings = 0
    start_time = time.time()
    
    for plant in plants:
        alias = plant.get('alias', 'Unknown')
        uid = plant.get('plant_uid') or plant.get('uid')
        
        if not uid:
            print(f"\n⚠️  {alias}: No UID found, skipping")
            continue
            
        print(f"\n📡 PROCESSING: {alias} ({uid})")
        
        # Determine chunk size
        chunk_days = 1 if uid in LARGE_SITES else 7
        print(f"   Strategy: {chunk_days}-day chunks")
        
        site_readings = 0
        current_date = START_DATE
        
        while current_date < END_DATE:
            next_date = min(current_date + timedelta(days=chunk_days), END_DATE)
            
            start_str = current_date.strftime("%Y%m%d")
            end_str = next_date.strftime("%Y%m%d")
            
            try:
                # fetch_readings now uses optimized batch storage
                rows = toolkit.fetch_readings(
                    plant_uid=uid,
                    start_date=start_str,
                    end_date=end_str
                )
                
                if rows > 0:
                    site_readings += rows
                    print(f"      ✅ {current_date.strftime('%Y-%m-%d')} to {next_date.strftime('%Y-%m-%d')}: {rows:,} readings")
                else:
                    print(f"      ℹ️  {current_date.strftime('%Y-%m-%d')} to {next_date.strftime('%Y-%m-%d')}: No new data")
                    
            except Exception as e:
                print(f"      ❌ {current_date.strftime('%Y-%m-%d')}: {str(e)[:100]}")
            
            current_date = next_date
            time.sleep(0.5)  # Be nice to the API
            
        print(f"   DONE: {site_readings:,} total readings for {alias}")
        grand_total_readings += site_readings
        
    duration = time.time() - start_time
    print("\n" + "=" * 70)
    print("OVERALL SUMMARY")
    print("=" * 70)
    print(f"Total readings fetched: {grand_total_readings:,}")
    print(f"Total time: {duration/60:.1f} minutes")
    print(f"Completed at: {datetime.now().isoformat()}")
    print("=" * 70)

if __name__ == "__main__":
    main()
