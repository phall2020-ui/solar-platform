# ARCHIVED — 2026-04-04
#
# This script was a one-off analysis tool.  It should not be used for new
# curtailment pulls.  Use cli/export_limit_pull.py instead, which discovers
# LIMITATION devices dynamically and stores results in platform/data/export_limits/.
#
# Kept here for reference only.  Known issues in this file:
#   - API key was previously hardcoded (now read from env); rotate if exposed.
#   - Phantom-record bug fixed below: Smeed Dean proxy timestamps are no longer
#     added to all_timestamps; they only fill irradiance for existing timestamps.
#   - Only the first target device per site is used; multi-device sites incomplete.

import requests
from datetime import datetime, timedelta
import collections
import os
import csv

API_KEY = os.getenv("JUGGLE_API_KEY", "")
BASE_URL = "https://www.emig.co.uk/p/api"

# Mapping of plants we know have exportLimit data.
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

def get_site_info(uid: str, target_type: str) -> dict:
    """Gets the target devices, weather station, and DC capacity for a site."""
    try:
        resp = requests.get(f"{BASE_URL}/plant/{uid}", params={"apikey": API_KEY}, timeout=30)
        resp.raise_for_status()
        details = resp.json()
        
        meters = details.get("meters", [])
        
        target_devices = [m.get("emigId") for m in meters if m.get("type", "") == target_type and "emigId" in m]
        weather_devices = [m.get("emigId") for m in meters if m.get("type", "") in ("WEATHER", "WEATHER_STATION") and "emigId" in m]
        pv_inverter_devices = [m.get("emigId") for m in meters if m.get("type", "") in ("INVERTER", "PV") and "emigId" in m]
        
        # Get DC Capacity
        # 1. Try plant level capacity
        capacity = details.get("capacity") or details.get("dcCapacity")
        
        # 2. If not, sum up the individual inverter level DC capacities
        if not capacity:
            inverter_caps = [m.get("dcCapacity", 0) for m in meters if m.get("type", "") == "INVERTER" and m.get("dcCapacity")]
            if inverter_caps:
                capacity = sum(inverter_caps)
                
        # 3. Ultimate fallback (should be rare)
        capacity = capacity or 100.0
                
        return {
            "target_devices": target_devices,
            "weather_devices": weather_devices,
            "power_devices": pv_inverter_devices,
            "dc_capacity_kw": float(capacity)
        }
    except Exception as exc:
        print(f"Error discovering devices for {uid}: {exc}")
        return {"target_devices": [], "weather_devices": [], "power_devices": [], "dc_capacity_kw": 100.0}

def fetch_readings(device_id: str, start_str: str, end_str: str) -> dict:
    """Fetches 15-min readings for a device and returns them indexed by timestamp."""
    try:
        resp = requests.get(
            f"{BASE_URL}/meter/{device_id}/readings",
            params={
                "apikey": API_KEY,
                "startDate": start_str,
                "endDate": end_str,
                "minIntervalS": 900 # 15 min chunks
            },
            timeout=30,
        )
        resp.raise_for_status()
        readings = resp.json().get("readings", [])
        
        # Index by timestamp
        indexed = {}
        for r in readings:
            ts = r.get("ts", r.get("timestamp"))
            if ts:
                indexed[ts] = r
        return indexed
    except Exception as exc:
        print(f"  -> ERROR fetching readings for {device_id}: {exc}")
        return {}

def pull_curtailment_data(days_back=7):
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)
    start_str = start_date.strftime("%Y%m%d")
    end_str = end_date.strftime("%Y%m%d")
    
    print(f"Pulling curtailment data from {start_str} to {end_str}...\n")
    
    all_records = []
    
    # Fetch Smeed Dean Weather data separately as a baseline proxy for all dry run metrics
    print(f"\n[DRY RUN SETUP] Pre-fetching Smeed Dean Weather Data to use as proxy...")
    smeed_info = get_site_info("AMP:00034", "INVERTER")
    smeed_weather_device = smeed_info["weather_devices"][0] if smeed_info["weather_devices"] else None
    smeed_weather_readings = {}
    if smeed_weather_device:
        smeed_weather_readings = fetch_readings(smeed_weather_device, start_str, end_str)

    for site_name, config in SITES.items():
        uid = config["uid"]
        target_type = config["type"]
        
        print(f"[{site_name}] Fetching data...")
        site_info = get_site_info(uid, target_type)
        
        if not site_info["target_devices"]:
            print(f"  -> WARNING: No {target_type} devices found.")
            continue
            
        dc_capacity = site_info["dc_capacity_kw"]
        
        # We will use the first target device (for export limit)
        target_device = site_info["target_devices"][0]
        # First weather device (for irradiance)
        weather_device = site_info["weather_devices"][0] if site_info["weather_devices"] else None
        # First power device (for actual generation if the target device doesn't have it)
        power_device = site_info["power_devices"][0] if site_info["power_devices"] else None
        
        # Fetch readings
        limit_readings = fetch_readings(target_device, start_str, end_str)
        weather_readings = fetch_readings(weather_device, start_str, end_str) if weather_device else {}
        power_readings = fetch_readings(power_device, start_str, end_str) if power_device else {}
        
        # Merge by timestamp.
        # Do NOT include Smeed Dean timestamps — the proxy only fills irradiance for
        # intervals the site itself reported.  Including Smeed Dean keys created phantom
        # records where actual_power defaulted to 0.
        all_timestamps = set(limit_readings.keys()) | set(weather_readings.keys()) | set(power_readings.keys())
        
        for ts in sorted(all_timestamps):
            limit_r = limit_readings.get(ts, {})
            weather_r = weather_readings.get(ts, {})
            power_r = power_readings.get(ts, {})
            
            # EXTRACT EXPORT LIMIT
            export_limit = None
            if "exportLimit" in limit_r and isinstance(limit_r["exportLimit"], dict):
                export_limit = limit_r["exportLimit"].get("value")
            elif f"{target_type}.exportLimit" in limit_r:
                export_limit = limit_r[f"{target_type}.exportLimit"]
                
             # EXTRACT ACTUAL POWER (try target device first, then power device)
            active_power_w = None
            for r in [limit_r, power_r]:
                if "importActivePower" in r and isinstance(r["importActivePower"], dict):
                    active_power_w = r["importActivePower"].get("value")
                    if active_power_w is not None: break
                        
            # EXTRACT IRRADIANCE
            irradiance_wm2 = None
            irradiance_source = "None (Needs SolarGIS)"
            
            # Step 1: Try true local weather station
            if weather_device and ts in weather_readings:
                for key in ["poaIrradiance", "horizontalIrradiance", "WEATHER_STATION.poaIrradiance", "WEATHER_STATION.horizontalIrradiance"]:
                    val = weather_r.get(key)
                    if isinstance(val, dict): val = val.get("value")
                    if val is not None:
                        irradiance_wm2 = val
                        irradiance_source = f"Local EMIG sensor ({key})"
                        break
                        
            # Step 2: Fallback to Smeed Dean Proxy for dry run
            if irradiance_wm2 is None and ts in smeed_weather_readings:
                sr = smeed_weather_readings[ts]
                for key in ["poaIrradiance", "horizontalIrradiance", "WEATHER_STATION.poaIrradiance", "WEATHER_STATION.horizontalIrradiance"]:
                    val = sr.get(key)
                    if isinstance(val, dict): val = val.get("value")
                    if val is not None:
                        irradiance_wm2 = val
                        irradiance_source = f"Smeed Dean Proxy ({key})"
                        break
            
            # ESTIMATE LOSS
            # The EMIG API sometimes returns negative numbers for export/generation. We only care about absolute magnitude.
            actual_power_kw = abs(active_power_w / 1000.0) if active_power_w is not None else 0.0
            theoretical_power_kw = 0.0
            loss_kwh = 0.0
            est_method = "N/A"
            prorata_loss_kwh = 0.0
            prorata_method = "N/A"

            if export_limit is not None and float(export_limit) < 100.0:
                limit_pct = float(export_limit)

                # Method 1: Irradiance-based (PR=0.8)
                if irradiance_wm2 is not None:
                    # Model: Irradiance / 1000 * DC_Capacity * 0.8 PR
                    theoretical_power_kw = (float(irradiance_wm2) / 1000.0) * dc_capacity * 0.80
                    theoretical_power_kw = max(0.0, theoretical_power_kw)

                    lost_power_kw = max(0.0, theoretical_power_kw - actual_power_kw)
                    loss_kwh = lost_power_kw * 0.25  # 15 min interval
                    est_method = f"PR=0.8 with {irradiance_source.split(' ')[0]}"
                else:
                    est_method = "Needs SolarGIS Data (Proxy missed)"
                    loss_kwh = 0.0

                # Method 2: Pro-rata based on export limit percentage
                # Assumes actual generation = limit_pct% of uncurtailed output.
                # Uncurtailed = actual / (limit_pct / 100), so loss = actual * (100 - limit_pct) / limit_pct
                if actual_power_kw > 0 and limit_pct > 0:
                    prorata_loss_kwh = actual_power_kw * (100.0 - limit_pct) / limit_pct * 0.25
                    prorata_method = f"Pro-rata @ {limit_pct:.1f}% limit"
                else:
                    prorata_method = "No actual power reading"

            all_records.append({
                "site_name": site_name,
                "plant_uid": uid,
                "timestamp": ts,
                "export_limit_pct": export_limit,
                "dc_capacity_kw": dc_capacity,
                "actual_power_kw": round(actual_power_kw, 2),
                "irradiance_wm2": irradiance_wm2,
                "irradiance_source": irradiance_source,
                "theoretical_capacity_kw": round(theoretical_power_kw, 2) if theoretical_power_kw else None,
                "estimated_curtailment_loss_kwh": round(loss_kwh, 3),
                "estimation_method": est_method,
                "prorata_curtailment_loss_kwh": round(prorata_loss_kwh, 3),
                "prorata_method": prorata_method,
            })
                
    if not all_records:
        print("\nNo data retrieved.")
        return
        
    # Sort
    all_records.sort(key=lambda x: (x["site_name"], x["timestamp"]))
    
    # Save to CSV
    output_path = os.path.expanduser("~/Documents/export_limitation_with_losses.csv")
    keys = all_records[0].keys()
    
    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(all_records)
        
    print(f"\nDone! Saved {len(all_records)} rows to {output_path}")
    
    # Summary Printout
    print(f"\n{'='*70}")
    print(f"{'CURTAILMENT LOSS SUMMARY':^70}")
    print(f"{'='*70}")
    print(f"{'Site':<35} {'Events':>6}  {'Irradiance (kWh)':>17}  {'Pro-rata (kWh)':>14}")
    print(f"{'-'*70}")

    site_losses_irr = collections.defaultdict(float)
    site_losses_pro = collections.defaultdict(float)
    site_events = collections.defaultdict(int)

    for r in all_records:
        limit = r["export_limit_pct"]
        if limit is not None and float(limit) < 100.0:
            site_events[r["site_name"]] += 1
            site_losses_irr[r["site_name"]] += float(r["estimated_curtailment_loss_kwh"] or 0)
            site_losses_pro[r["site_name"]] += float(r["prorata_curtailment_loss_kwh"] or 0)

    if not site_events:
        print("No curtailment events found.")
    else:
        for site in sorted(site_events.keys()):
            events = site_events[site]
            irr = site_losses_irr[site]
            pro = site_losses_pro[site]
            irr_str = f"{irr:.2f}" if irr > 0 else "no irradiance data"
            print(f"{site:<35} {events:>6}  {irr_str:>17}  {pro:>14.2f}")

if __name__ == "__main__":
    pull_curtailment_data(days_back=7)
