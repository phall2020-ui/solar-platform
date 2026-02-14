import os
import sys
import json
from datetime import date
from fetch_inverter_data import Config, fetch_all_readings

JUGGLE_API_KEY = "380fe299-a626-48f1-8456-e701c7383a23"

def val(x):
    return x.get('value') if isinstance(x, dict) else x

def get_juggle_monthly_data_debug(plant_uid, emig_id, start_date, end_date):
    print(f"Fetching {emig_id} from {start_date} to {end_date}...")
    cfg = Config(api_key=JUGGLE_API_KEY, plant_uid=plant_uid, start_date=start_date.replace("-", ""), end_date=end_date.replace("-", ""), min_interval_s=1800)
    
    try:
        readings = fetch_all_readings(cfg, emig_id)
        print(f"Readings count: {len(readings)}")
        if readings:
            print(f"First reading: {readings[0]}")
            return # Exit early to inspect structure
    except Exception as e:
        print(f"Error fetching: {e}")
        return

    daily_map = {}
    grouped = {}
    for r in readings:
        ts = r.get('timestamp') 
        if not ts: 
            print("Skipping reading without timestamp")
            continue
        val_ = val(r.get('importEnergy')) 
        if val_ is None: val_ = val(r.get('exportEnergy')) 
        if val_ is None: 
            # print("Skipping reading without energy value")
            continue
        
        dt_str = ts.split("T")[0]
        if dt_str not in grouped: grouped[dt_str] = []
        grouped[dt_str].append(float(val_))
        
    for dt, vals in grouped.items():
        if vals:
            daily_kwh = (max(vals) - min(vals)) / 1000.0
            daily_map[dt] = daily_kwh
            print(f"  {dt}: count={len(vals)}, min={min(vals)}, max={max(vals)}, kwh={daily_kwh}")
            
    return daily_map

if __name__ == "__main__":
    # Test for Feb 1 to Feb 10
    get_juggle_monthly_data_debug("ERS:00001", "INVERT:002946", "2026-02-01", "2026-02-10")
