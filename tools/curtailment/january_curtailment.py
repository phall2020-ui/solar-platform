import requests
import datetime
import os
import csv
from collections import defaultdict
import datetime

API_KEY = "380fe299-a626-48f1-8456-e701c7383a23"
BASE_URL = "https://www.emig.co.uk/p/api"

SITES = {
    "Blachford UK": {"uid": "AMP:00024", "type": "INVERTER"},
    "Casepak (Sunningdale Road)": {"uid": "HARP:00024", "type": "LIMITATION"},
    "Smeed Dean Works": {"uid": "AMP:00034", "type": "INVERTER"},
    "Smithy's Mushrooms PH1": {"uid": "AMP:00028", "type": "LIMITATION"},
    "Smithy's Mushrooms PH1+2": {"uid": "AMP:00036", "type": "LIMITATION"},
    "Newfold Farm": {"uid": "ERS:00001", "type": "PLC"},
    "Cromwell Tools": {"uid": "AMP:00001", "type": "INVERTER"},
    "Man City FC Training Ground": {"uid": "AMP:00019", "type": "LIMITATION"},
    "Merry Hill Shopping Centre": {"uid": "AMP:00025", "type": "INVERTER"},
    "Metrocentre": {"uid": "AMP:00027", "type": "INVERTER"},
    "Smithy's Mushrooms PH2": {"uid": "AMP:00033", "type": "LIMITATION"},
    "Sofina Foods": {"uid": "AMP:00029", "type": "LIMITATION"}
}

SITE_TO_IRRADIANCE_FILE = {
    "Blachford UK": "2026-02-09-2026-01-Spreadsheet-Blachford-v01.csv",
    "Casepak (Sunningdale Road)": "2026-02-09-2026-01-Spreadsheet-Casepak-Sunningdale-v01.csv",
    "Smeed Dean Works": "2026-02-09-2026-01-Spreadsheet-Wienerberger---Smeed-v01.csv",
    "Smithy's Mushrooms PH1": "2026-02-09-2026-01-Spreadsheet-Smithys-Mushrooms-v01.csv",
    "Smithy's Mushrooms PH1+2": "2026-02-09-2026-01-Spreadsheet-Smithys-Mushrooms-v01.csv", # Assuming Phase 1 covers this or we combine
    "Newfold Farm": "2026-02-09-2026-01-Spreadsheet-Bae-Fylde-v01.csv",
    "Cromwell Tools": "2026-02-09-2026-01-Spreadsheet-Cromwell-Tools-v01.csv",
    "Man City FC Training Ground": "2026-02-09-2026-01-Spreadsheet-City-Football-Group-Phase-1-v01.csv",
    "Merry Hill Shopping Centre": "2026-02-09-2026-01-Spreadsheet-Merry-Hill-v01.csv",
    "Metrocentre": "2026-02-09-2026-01-Spreadsheet-Metro-Centre-v01.csv",
    "Smithy's Mushrooms PH2": "2026-02-09-2026-01-Spreadsheet-Smithys-Mushrooms-Phase-2-v01.csv",
    "Sofina Foods": "2026-02-09-2026-01-Spreadsheet-Sofina-Haverhill-v01.csv"
}

def load_canonical_capacities():
    capacities = {}
    path = "/Users/peterhall/Documents/Irradiation Data/2026-01-12-Irradiation-Data-Spreadsheet-Summary-Annual-All-Sites-New-v01.csv"
    if not os.path.exists(path): return capacities
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            capacities[row["name"].replace("_", " ")] = float(row["total_capacity_kwp"])
    return capacities

def load_theoretical_hourly(file_path):
    # Returns a dict of timestamp string (e.g. "2026-01-01T12:00:00Z") to theoretical kWh generation
    target_path = os.path.join("/Users/peterhall/Documents/Irradiation Data/2026 01", file_path)
    output = defaultdict(float)
    if not os.path.exists(target_path):
        print(f"Warning: {target_path} not found.")
        return output
        
    with open(target_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            time_str = row["time"] # format 2026-01-01 12:00:30+00:00
            if "2026-01" not in time_str:
                continue
                
            try:
                gti = float(row["gti"])
                cap = float(row["array_capacity"])
                
                # Snap 12:00:30 to 12:00:00 
                # (API usually does flat 15m marks: 00:00, 15:00, 30:00, 45:00)
                dt = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S%z")
                
                # Standardize to 15 minute interval bucket
                minute = (dt.minute // 15) * 15
                dt = dt.replace(minute=minute, second=0, microsecond=0)
                std_time = dt.strftime("%Y-%m-%dT%H:%M:00.000000Z")
                
                # gti is assumed to be kWh/m2 per 15 mins.
                # Theoretical energy in kWh = gti * array_capacity * PR (0.8)
                output[std_time] += gti * cap * 0.8
            except Exception as e:
                pass
                
    return output

def fetch_plant_devices(plant_id):
    resp = requests.get(f"{BASE_URL}/plant/{plant_id}", params={"apikey": API_KEY})
    resp.raise_for_status()
    return resp.json().get("meters", [])

def fetch_bulk_data(devices, start_date_str, end_date_str):
    all_readings = []
    
    for d in devices:
        print(f"    -> Fetching {d} from {start_date_str} to {end_date_str}...")
        
        resp = requests.get(
            f"{BASE_URL}/meter/{d}/readings",
            params={
                "apikey": API_KEY, 
                "startDate": start_date_str, 
                "endDate": end_date_str,
                "minIntervalS": 900
            },
            timeout=30
        )
        if resp.status_code == 200:
            readings = resp.json().get("readings", [])
            # Standardize for later processing
            for r in readings:
                # Add device id into reading 
                r["deviceId"] = d
            all_readings.extend(readings)
        else:
            print(f"      Failed for device {d}: {resp.status_code}")
            
    return all_readings

def process_site_january(name, site_data, notion_capacities):
    print(f"[{name}] Analyzing January Data...")
    
    # 1. Find matched devices
    meters = fetch_plant_devices(site_data["uid"])
    target_type = site_data["type"]
    limitation_devices = [m["emigId"] for m in meters if m.get("type", "") == target_type]
    inverter_devices = [m["emigId"] for m in meters if m.get("type", "") in ("INVERTER", "PV")]

    if not limitation_devices:
        print(f"  -> WARNING: No {target_type} limitation device found!")
        return []
        
    # 2. Load PVGIS/SolarGIS theoretical data
    file_mapping = SITE_TO_IRRADIANCE_FILE.get(name)
    theoretical_map = load_theoretical_hourly(file_mapping) if file_mapping else {}
    
    # 3. Pull EMIG Data
    START = "20260101"
    END = "20260201"
    
    limitation_data = fetch_bulk_data(limitation_devices, START, END)
    inverter_data = fetch_bulk_data(inverter_devices, START, END)
    
    eventsByTime = defaultdict(dict)
    
    # Process readings returned in the form {'timestamp': ..., 'exportLimitKW': ... }
    for reading in limitation_data:
        t = reading.get("ts", reading.get("timestamp"))
        
        limit_val = None
        for f in ("activePowerRatio", "activePowerRatioL1", "activePowerSetLimit", "activePowerSetLimitL1", "limitProfile", "exportLimitKW"):
            if reading.get(f) is not None:
                if "Ratio" in f:
                    limit_val = reading[f]
                elif "Limit" in f and reading[f] != "OFF":
                    pass
                elif "Profile" in f:
                     # Some APIs return strings. We just want numbers if it's there
                     try:
                         limit_val = float(reading[f])
                     except:
                         pass
                break
                
        if limit_val is not None:
            if "export_limit_pct" not in eventsByTime[t] or limit_val < eventsByTime[t]["export_limit_pct"]:
                 eventsByTime[t]["export_limit_pct"] = limit_val
                 
    for reading in inverter_data:
        t = reading.get("ts", reading.get("timestamp"))
        val = reading.get("activePower") or reading.get("activePowerL1")
        if val is not None:
            eventsByTime[t]["generation_actual_kw"] = eventsByTime[t].get("generation_actual_kw", 0) + abs(val / 1000.0)

    # 4. Calculate Loss
    records = []
    total_loss = 0.0
    
    for t, data in sorted(eventsByTime.items()):
        limit = data.get("export_limit_pct")
        
        if limit is not None and limit < 100.0:
            actual_kw = data.get("generation_actual_kw", 0.0)
            theo_kwh_15m = theoretical_map.get(t, 0.0)
            
            # Theoretical kW
            theo_kw = theo_kwh_15m / 0.25
            
            # If our actual generation drops BELOW theoretical, consider it curtailed.
            if limit < 100.0 and theo_kw > actual_kw:
                lost_kw = theo_kw - actual_kw
                loss_kwh = lost_kw * 0.25
                total_loss += loss_kwh
                
                records.append({
                    "site": name,
                    "time": t,
                    "export_limit_pct": limit,
                    "actual_gen_kw": round(actual_kw, 2),
                    "theoretical_gen_kw": round(theo_kw, 2),
                    "curtailment_loss_kwh": round(loss_kwh, 2)
                })

    print(f"  -> Total January Loss: {total_loss:.2f} kWh across {len(records)} curtailed intervals.")
    return records

def main():
    notion_capacities = load_canonical_capacities()
    all_records = []
    
    print("Starting January Curtailment Analysis...")
    for name, site_data in SITES.items():
         records = process_site_january(name, site_data, notion_capacities)
         all_records.extend(records)
         
    # Save to CSV
    output_path = "/Users/peterhall/Documents/january_curtailment_report.csv"
    with open(output_path, "w", newline='') as f:
        if not all_records:
            print("No records found.")
            return
            
        writer = csv.DictWriter(f, fieldnames=all_records[0].keys())
        writer.writeheader()
        writer.writerows(all_records)
        
    print(f"\\nAnalysis Complete. Saved detailed output to {output_path}")
    
if __name__ == "__main__":
    main()
