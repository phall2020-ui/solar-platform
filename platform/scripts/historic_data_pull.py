#!/usr/bin/env python3
"""
Historic Data Pull for Failed Sites.
Uses 1-day chunks to avoid 413 rate limits.
Pulls from September 1, 2025 to today.
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path
import time

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Failed sites with their UIDs
SITES_TO_PULL = {
    "Cromwell Tools": "AMP:00001",
    "Sheldons Bakery": "AMP:00020",
}

# Date range: Sep 1, 2025 to today
START_DATE = datetime(2025, 9, 1)
END_DATE = datetime.now()

def main():
    """Pull historic data using 1-day chunks."""
    from services import toolkit
    
    if not toolkit.is_available():
        print("ERROR: Toolkit not available. Check configuration.")
        sys.exit(1)
    
    total_days = (END_DATE - START_DATE).days
    print("=" * 70)
    print("HISTORIC DATA PULL FOR FAILED SITES")
    print("=" * 70)
    print(f"Sites: {', '.join(SITES_TO_PULL.keys())}")
    print(f"Date range: {START_DATE.strftime('%Y-%m-%d')} to {END_DATE.strftime('%Y-%m-%d')}")
    print(f"Total days: {total_days}")
    print("Strategy: 1-day chunks to avoid 413 rate limits")
    print("=" * 70)
    
    grand_total = 0
    
    for alias, uid in SITES_TO_PULL.items():
        print(f"\n{'='*70}")
        print(f"📡 SITE: {alias}")
        print(f"   UID: {uid}")
        print(f"{'='*70}")
        
        site_readings = 0
        successful_days = 0
        failed_days = 0
        
        # Process each day
        current_date = START_DATE
        day_num = 0
        
        while current_date < END_DATE:
            day_num += 1
            next_date = current_date + timedelta(days=1)
            
            start_str = current_date.strftime("%Y%m%d")
            end_str = next_date.strftime("%Y%m%d")
            
            # Progress indicator every 10 days
            if day_num % 10 == 1 or day_num == 1:
                print(f"\n   [{day_num}/{total_days}] {current_date.strftime('%Y-%m-%d')}...")
            
            try:
                rows = toolkit.fetch_readings(
                    plant_uid=uid,
                    start_date=start_str,
                    end_date=end_str
                )
                
                if rows > 0:
                    site_readings += rows
                    successful_days += 1
                    print(f"      ✅ {current_date.strftime('%Y-%m-%d')}: {rows:,} readings")
                else:
                    # Don't count days with no data as failures
                    pass
                    
            except Exception as e:
                error_str = str(e)
                if "413" in error_str:
                    failed_days += 1
                    print(f"      ⚠️ {current_date.strftime('%Y-%m-%d')}: 413 rate limit")
                else:
                    failed_days += 1
                    print(f"      ❌ {current_date.strftime('%Y-%m-%d')}: {error_str[:50]}")
            
            current_date = next_date
            
            # Small delay to be nice to the API
            time.sleep(0.5)
        
        print(f"\n   {'─'*50}")
        print(f"   SITE SUMMARY: {alias}")
        print(f"   Total readings: {site_readings:,}")
        print(f"   Successful days: {successful_days}")
        print(f"   Failed days: {failed_days}")
        
        grand_total += site_readings
    
    # Grand summary
    print("\n" + "=" * 70)
    print("OVERALL SUMMARY")
    print("=" * 70)
    print(f"Sites processed: {len(SITES_TO_PULL)}")
    print(f"Total readings fetched: {grand_total:,}")
    print(f"Completed at: {datetime.now().isoformat()}")

if __name__ == "__main__":
    main()
