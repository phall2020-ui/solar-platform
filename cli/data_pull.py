#!/usr/bin/env python3
"""
Automated Data Pull Script for Solar Portfolio Manager.
This script fetches the latest readings for all registered plants.
Can be run manually or via GitHub Actions.
"""
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path (scripts is one level down from root)
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

def main():
    """Main data pull function."""
    from solar_platform.services import toolkit
    
    if not toolkit.is_available():
        print("ERROR: Toolkit not available. Check configuration.")
        sys.exit(1)
    
    # Get all registered plants
    plants = toolkit.get_plants()
    if not plants:
        print("No registered plants found.")
        return
    
    print(f"Found {len(plants)} registered plants")
    print("=" * 60)
    
    # Date range: last 7 days (to catch any missed data)
    # API expects YYYYMMDD format
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=7)).strftime("%Y%m%d")
    
    total_rows = 0
    success_count = 0
    error_count = 0
    
    for plant in plants:
        alias = plant.get('alias', 'Unknown')
        uid = plant.get('uid') or plant.get('plant_uid')
        
        if not uid:
            print(f"⚠️  {alias}: No UID found, skipping")
            continue
        
        try:
            print(f"\n📡 Fetching: {alias}")
            print(f"   UID: {uid}")
            print(f"   Date range: {start_date} to {end_date}")
            
            rows = toolkit.fetch_readings(
                plant_uid=uid,
                start_date=start_date,
                end_date=end_date
            )
            
            if rows > 0:
                print(f"   ✅ Fetched {rows:,} readings")
                total_rows += rows
                success_count += 1
            else:
                print(f"   ℹ️  No new data available")
                success_count += 1
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
            error_count += 1
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Plants processed: {len(plants)}")
    print(f"Successful: {success_count}")
    print(f"Errors: {error_count}")
    print(f"Total readings fetched: {total_rows:,}")
    print(f"Completed at: {datetime.now().isoformat()}")
    
    if error_count > 0:
        sys.exit(1)

if __name__ == "__main__":
    main()
