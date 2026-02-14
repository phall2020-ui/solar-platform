#!/usr/bin/env python3
"""
Retry Data Pull for Failed Sites with smaller date ranges.
Fetches data in 2-day chunks to avoid 413 rate limits.
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Failed sites with their UIDs
FAILED_SITES = {
    "Cromwell Tools": "AMP:00001",
    "Sheldons Bakery": "AMP:00020",
}

def main():
    """Retry data pull for failed sites with smaller date chunks."""
    from services import toolkit
    
    if not toolkit.is_available():
        print("ERROR: Toolkit not available. Check configuration.")
        sys.exit(1)
    
    print("=" * 60)
    print("RETRY DATA PULL FOR FAILED SITES")
    print("=" * 60)
    print(f"Sites to retry: {', '.join(FAILED_SITES.keys())}")
    print("Strategy: 2-day chunks to avoid 413 rate limits")
    print("=" * 60)
    
    total_rows = 0
    success_count = 0
    error_count = 0
    
    # Use 2-day chunks for last 7 days
    end_date = datetime.now()
    
    for alias, uid in FAILED_SITES.items():
        print(f"\n📡 Fetching: {alias}")
        print(f"   UID: {uid}")
        
        site_readings = 0
        
        # Process in 2-day chunks
        for chunk_num in range(4):  # 4 chunks of 2 days = 8 days
            chunk_end = end_date - timedelta(days=chunk_num * 2)
            chunk_start = chunk_end - timedelta(days=2)
            
            start_str = chunk_start.strftime("%Y%m%d")
            end_str = chunk_end.strftime("%Y%m%d")
            
            print(f"   📅 Chunk {chunk_num + 1}/4: {start_str} to {end_str}")
            
            try:
                rows = toolkit.fetch_readings(
                    plant_uid=uid,
                    start_date=start_str,
                    end_date=end_str
                )
                
                if rows > 0:
                    print(f"      ✅ Got {rows:,} readings")
                    site_readings += rows
                else:
                    print(f"      ℹ️  No data for this chunk")
                    
            except Exception as e:
                print(f"      ❌ Error: {e}")
        
        if site_readings > 0:
            print(f"   ✅ Total for {alias}: {site_readings:,} readings")
            total_rows += site_readings
            success_count += 1
        else:
            print(f"   ⚠️  No data fetched for {alias}")
            error_count += 1
    
    # Summary
    print("\n" + "=" * 60)
    print("RETRY SUMMARY")
    print("=" * 60)
    print(f"Sites retried: {len(FAILED_SITES)}")
    print(f"Successful: {success_count}")
    print(f"Still failing: {error_count}")
    print(f"Total readings fetched: {total_rows:,}")
    print(f"Completed at: {datetime.now().isoformat()}")

if __name__ == "__main__":
    main()
