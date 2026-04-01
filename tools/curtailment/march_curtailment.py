import requests
import datetime
import os
import csv
from collections import defaultdict

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

# Update these filenames once the March SolarGIS/PVGIS spreadsheets are downloaded.
# Expected naming convention mirrors January: YYYY-MM-DD-YYYY-03-Spreadsheet-<Site>-v01.csv
SITE_TO_IRRADIANCE_FILE = {
    "Blachford UK": "2026-03-Spreadsheet-Blachford-v01.csv",
    "Casepak (Sunningdale Road)": "2026-03-Spreadsheet-Casepak-Sunningdale-v01.csv",
    "Smeed Dean Works": "2026-03-Spreadsheet-Wienerberger---Smeed-v01.csv",
    "Smithy's Mushrooms PH1": "2026-03-Spreadsheet-Smithys-Mushrooms-v01.csv",
    "Smithy's Mushrooms PH1+2": "2026-03-Spreadsheet-Smithys-Mushrooms-v01.csv",
    "Newfold Farm": "2026-03-Spreadsheet-Bae-Fylde-v01.csv",
    "Cromwell Tools": "2026-03-Spreadsheet-Cromwell-Tools-v01.csv",
    "Man City FC Training Ground": "2026-03-Spreadsheet-City-Football-Group-Phase-1-v01.csv",
    "Merry Hill Shopping Centre": "2026-03-Spreadsheet-Merry-Hill-v01.csv",
    "Metrocentre": "2026-03-Spreadsheet-Metro-Centre-v01.csv",
    "Smithy's Mushrooms PH2": "2026-03-Spreadsheet-Smithys-Mushrooms-Phase-2-v01.csv",
    "Sofina Foods": "2026-03-Spreadsheet-Sofina-Haverhill-v01.csv"
}

IRRADIANCE_DATA_DIR = "/Users/peterhall/Documents/Irradiation Data/2026 03"


def load_theoretical_hourly(file_path):
    """Load theoretical 15-min generation from a SolarGIS/PVGIS spreadsheet CSV.

    Returns a dict mapping standardised timestamp strings
    (e.g. "2026-03-01T12:00:00.000000Z") to theoretical kWh for that 15-min slot.
    """
    target_path = os.path.join(IRRADIANCE_DATA_DIR, file_path)
    output = defaultdict(float)
    if not os.path.exists(target_path):
        print(f"  Warning: irradiance file not found: {target_path}")
        return output

    with open(target_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            time_str = row.get("time", "")
            if "2026-03" not in time_str:
                continue
            try:
                gti = float(row["gti"])
                cap = float(row["array_capacity"])

                dt = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S%z")
                # Snap to 15-minute bucket
                minute = (dt.minute // 15) * 15
                dt = dt.replace(minute=minute, second=0, microsecond=0)
                std_time = dt.strftime("%Y-%m-%dT%H:%M:00.000000Z")

                # gti in kWh/m² per 15 min; theoretical energy = gti * array_capacity * PR
                output[std_time] += gti * cap * 0.8
            except Exception:
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
                "minIntervalS": 900,
            },
            timeout=30,
        )
        if resp.status_code == 200:
            readings = resp.json().get("readings", [])
            for r in readings:
                r["deviceId"] = d
            all_readings.extend(readings)
        else:
            print(f"      Failed for device {d}: {resp.status_code}")
    return all_readings


def process_site_march(name, site_data):
    print(f"[{name}] Analyzing March Data...")

    meters = fetch_plant_devices(site_data["uid"])
    target_type = site_data["type"]
    limitation_devices = [m["emigId"] for m in meters if m.get("type", "") == target_type]
    inverter_devices = [m["emigId"] for m in meters if m.get("type", "") in ("INVERTER", "PV")]

    if not limitation_devices:
        print(f"  -> WARNING: No {target_type} device found for {name}, skipping.")
        return []

    file_mapping = SITE_TO_IRRADIANCE_FILE.get(name)
    theoretical_map = load_theoretical_hourly(file_mapping) if file_mapping else {}

    START = "20260301"
    END = "20260401"

    limitation_data = fetch_bulk_data(limitation_devices, START, END)
    inverter_data = fetch_bulk_data(inverter_devices, START, END)

    events_by_time = defaultdict(dict)

    for reading in limitation_data:
        t = reading.get("ts", reading.get("timestamp"))
        limit_val = None
        for f in (
            "activePowerRatio",
            "activePowerRatioL1",
            "activePowerSetLimit",
            "activePowerSetLimitL1",
            "limitProfile",
            "exportLimitKW",
        ):
            if reading.get(f) is not None:
                if "Ratio" in f:
                    limit_val = reading[f]
                elif "Profile" in f:
                    try:
                        limit_val = float(reading[f])
                    except Exception:
                        pass
                break

        if limit_val is not None:
            if "export_limit_pct" not in events_by_time[t] or limit_val < events_by_time[t]["export_limit_pct"]:
                events_by_time[t]["export_limit_pct"] = limit_val

    for reading in inverter_data:
        t = reading.get("ts", reading.get("timestamp"))
        val = reading.get("activePower") or reading.get("activePowerL1")
        if val is not None:
            events_by_time[t]["generation_actual_kw"] = (
                events_by_time[t].get("generation_actual_kw", 0) + abs(val / 1000.0)
            )

    records = []
    total_loss = 0.0

    for t, data in sorted(events_by_time.items()):
        limit = data.get("export_limit_pct")
        if limit is not None and limit < 100.0:
            actual_kw = data.get("generation_actual_kw", 0.0)
            theo_kwh_15m = theoretical_map.get(t, 0.0)
            theo_kw = theo_kwh_15m / 0.25

            if theo_kw > actual_kw:
                lost_kw = theo_kw - actual_kw
                loss_kwh = lost_kw * 0.25
                total_loss += loss_kwh
                records.append(
                    {
                        "site": name,
                        "time": t,
                        "export_limit_pct": limit,
                        "actual_gen_kw": round(actual_kw, 2),
                        "theoretical_gen_kw": round(theo_kw, 2),
                        "curtailment_loss_kwh": round(loss_kwh, 2),
                    }
                )

    print(f"  -> Total March Loss: {total_loss:.2f} kWh across {len(records)} curtailed intervals.")
    return records


def main():
    all_records = []

    print("Starting March 2026 Curtailment Analysis...")
    for name, site_data in SITES.items():
        records = process_site_march(name, site_data)
        all_records.extend(records)

    output_path = "/Users/peterhall/Documents/march_curtailment_report.csv"
    if not all_records:
        print("No curtailed intervals found across all sites.")
        return

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=all_records[0].keys())
        writer.writeheader()
        writer.writerows(all_records)

    total_kwh = sum(r["curtailment_loss_kwh"] for r in all_records)
    print(f"\nAnalysis Complete.")
    print(f"Total curtailment loss: {total_kwh:.2f} kWh across {len(all_records)} intervals.")
    print(f"Detailed output saved to: {output_path}")


if __name__ == "__main__":
    main()
