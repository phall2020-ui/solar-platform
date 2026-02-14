"""
Unified Multi-Source Comparison
===============================
Pulls data from Juggle (inverters + PV meters) and Solis,
then outputs a single consolidated table.

Excludes dets/consett sites per user request.
"""
import io, sys, os, json, time
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, '.')
from datetime import datetime, timedelta
from fetch_inverter_data import BASE_URL, Config, fetch_all_readings
from solis_api import list_stations, list_inverters, get_station_month
import requests
import pandas as pd

API_KEY = os.environ.get('JUGGLE_API_KEY', '380fe299-a626-48f1-8456-e701c7383a23')
HEADERS = {'Authorization': f'token {API_KEY}'}
DATE = (datetime.today() - timedelta(days=1)).strftime("%Y%m%d")
DATE_DISPLAY = (datetime.today() - timedelta(days=1)).strftime("%Y-%m-%d")
DATE_MONTH = (datetime.today() - timedelta(days=1)).strftime("%Y-%m")

def val(x):
# ... (rest of file)


    return x.get('value') if isinstance(x, dict) else x

def juggle_daily_energy(plant_uid, emig_id, field='importEnergy'):
    """Get daily energy delta for a single device from Juggle."""
    cfg = Config(api_key=API_KEY, plant_uid=plant_uid, start_date=DATE, end_date=DATE, min_interval_s=1800)
    readings = fetch_all_readings(cfg, emig_id)
    if not readings:
        return 0.0
    vals = [val(r.get(field)) for r in readings if val(r.get(field)) is not None]
    if not vals:
        # Try exportEnergy as fallback
        vals = [val(r.get('exportEnergy')) for r in readings if val(r.get('exportEnergy')) is not None]
        if not vals:
            return 0.0
    delta = max(vals) - min(vals)
    return delta / 1000.0  # Wh -> kWh

def get_juggle_devices(plant_uid):
    """Get device lists for a Juggle plant."""
    try:
        resp = requests.get(f"{BASE_URL}/plant/{plant_uid}", headers=HEADERS, timeout=30)
        if resp.status_code != 200:
            return [], [], None
        data = resp.json()
        name = data.get('name', plant_uid)
        devices = data.get('meters', [])
        inverters = [d['emigId'] for d in devices if d.get('type') == 'INVERTER']
        pv_meters = [d['emigId'] for d in devices if d.get('type') == 'PV']
        return inverters, pv_meters, name
    except:
        return [], [], None

# ---- Discover all Juggle plants ----
print(f"Date: {DATE_DISPLAY}")
print("Discovering Juggle plants...")
juggle_plants = []
for prefix in ["ERS", "AMP"]:
    for i in range(1, 101):
        uid = f"{prefix}:{i:05d}"
        try:
            resp = requests.get(f"{BASE_URL}/plant/{uid}", headers=HEADERS, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                name = data.get('name', uid)
                devices = data.get('meters', [])
                inverters = [d['emigId'] for d in devices if d.get('type') == 'INVERTER']
                pv_meters = [d['emigId'] for d in devices if d.get('type') == 'PV']
                if inverters or pv_meters:
                    juggle_plants.append({
                        'uid': uid, 'name': name,
                        'inverters': inverters, 'pv_meters': pv_meters
                    })
        except:
            continue

print(f"  Found {len(juggle_plants)} Juggle plants with devices")

# ---- Discover Solis stations (exclude dets) ----
print("Discovering Solis stations...")
solis_result = list_stations()
solis_stations = solis_result.get("data", {}).get("page", {}).get("records", [])
solis_data = {}
for s in solis_stations:
    name = s.get("stationName", s.get("sno", "?"))
    if "dets" in name.lower() or "consett" in name.lower():
        continue
    sid = str(s.get("id"))
    month_kwh = s.get("monthEnergy1", s.get("monthEnergy", 0) * 1000 if s.get("monthEnergy", 0) < 100 else s.get("monthEnergy", 0))
    total_mwh = s.get("allEnergy1", s.get("allEnergy", 0))
    
    # Get inverter etotals
    try:
        inv_result = list_inverters(sid)
        inv_records = inv_result.get("data", {}).get("page", {}).get("records", [])
        inv_etoday_sum = sum(float(inv.get("etoday", 0) or 0) for inv in inv_records)
    except:
        inv_etoday_sum = 0
    
    # Get YESTERDAY's energy for fair comparison using stationMonth endpoint (returns daily energy list)
    try:
        month_data = get_station_month(sid, DATE_MONTH)
        days = month_data.get("data", [])
        # Find record for yesterday
        solis_yesterday = 0.0
        for d in days:
            if d.get("dateStr") == DATE_DISPLAY:
                solis_yesterday = float(d.get("energy") or d.get("eToday") or 0.0)
                break
    except:
        solis_yesterday = 0.0

    solis_data[name.lower().strip()] = {
        'name': name,
        'capacity_kw': s.get("capacity1", 0),
        'inv_count': s.get("inverterCount", 0),
        'inv_online': s.get("inverterOnlineCount", 0),
        'month_kwh': month_kwh,
        'total_mwh': total_mwh / 1000 if total_mwh > 10000 else total_mwh,
        'day_energy': solis_yesterday,  # Now using YESTERDAY's data
        'inv_etoday': inv_etoday_sum,
    }
    time.sleep(0.2)

print(f"  Found {len(solis_data)} Solis stations (excluding dets/consett)")

# ---- Name matching between Juggle and Solis ----
MANUAL_MAP = {
    'Smithy\'s Mushrooms PH1': 'smithy mushroom',
    'Smithy\'s Mushrooms PH2': 'smithy mushroom',
    'Smithy\'s Mushrooms PH1+2': 'smithy mushroom',
    'Hibernian FC Training Centre': 'hibernian training ground',
    'Sofina Foods': 'haverhill',
}

def match_solis(juggle_name):
    jn = juggle_name.lower().strip()
    # Direct match
    if jn in solis_data:
        return solis_data[jn]
    # Manual map
    if juggle_name in MANUAL_MAP:
        key = MANUAL_MAP[juggle_name].lower()
        if key in solis_data:
            return solis_data[key]
    # Fuzzy: check if juggle name is substring of solis name or vice versa
    for sk, sv in solis_data.items():
        if jn in sk or sk in jn:
            return sv
    return None

# ---- Pull Juggle daily data for each site ----
print("\nFetching Juggle daily energy for each site (this may take a few minutes)...")
rows = []
solis_matched = set()

for jp in juggle_plants:
    uid = jp['uid']
    name = jp['name']
    inv_ids = jp['inverters']
    pv_ids = jp['pv_meters']
    
    print(f"  {name} ({uid})...", end=" ", flush=True)
    
    # Juggle inverter total
    inv_total = 0
    for eid in inv_ids:
        inv_total += juggle_daily_energy(uid, eid)
    
    # Juggle PV meter total
    pv_total = 0
    for eid in pv_ids:
        pv_total += juggle_daily_energy(uid, eid)
    
    # Find matching Solis station
    solis = match_solis(name)
    solis_day = solis['day_energy'] if solis else None
    solis_month = solis['month_kwh'] if solis else None
    solis_name = solis['name'] if solis else ''
    if solis:
        solis_matched.add(solis_name.lower().strip())
    
    rows.append({
        'Site': name,
        'Juggle UID': uid,
        'Juggle Inv (kWh)': round(inv_total, 1),
        'Juggle PV (kWh)': round(pv_total, 1),
        'Solis Day (kWh)': round(solis_day, 1) if solis_day is not None else '',
        'Solis Month (kWh)': round(solis_month, 1) if solis_month is not None else '',
        'Solis Station': solis_name,
    })
    print(f"Inv={inv_total:.1f}, PV={pv_total:.1f}, Solis={solis_day if solis_day else 'N/A'}")

# Add Solis-only stations
for sk, sv in solis_data.items():
    if sk not in solis_matched:
        rows.append({
            'Site': sv['name'],
            'Juggle UID': '',
            'Juggle Inv (kWh)': '',
            'Juggle PV (kWh)': '',
            'Solis Day (kWh)': round(sv['day_energy'], 1),
            'Solis Month (kWh)': round(sv['month_kwh'], 1),
            'Solis Station': sv['name'],
        })

# ---- Output ----
df = pd.DataFrame(rows)
print(f"\n{'='*100}")
print(f"  UNIFIED COMPARISON TABLE — {DATE_DISPLAY}")
print(f"{'='*100}")
print(df.to_string(index=False))

# Save to Excel
outfile = f"unified_comparison_{DATE}.xlsx"
df.to_excel(outfile, index=False, sheet_name="Comparison")
print(f"\nSaved to {outfile}")
