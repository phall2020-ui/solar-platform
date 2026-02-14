import os
import requests
import json
from fetch_inverter_data import BASE_URL, Config, fetch_all_readings

JUGGLE_API_KEY = os.environ.get('JUGGLE_API_KEY')

SITES = {
    "Sofina": "AMP:00043",
    "Smithys": "AMP:00036"
}

def check_site(name, uid):
    print(f"Checking {name} ({uid})...")
    headers = {'Authorization': f'token {JUGGLE_API_KEY}'}
    
    # 1. Check Plant Details
    url = f"{BASE_URL}/plant/{uid}"
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        print(f"  Plant API Error: {resp.status_code} {resp.text}")
        return

    data = resp.json()
    print(f"  Plant Found: {data.get('name')}")
    meters = data.get('meters', [])
    print(f"  Meters: {len(meters)}")
    
    # 2. Try to fetch some data (last 3 days)
    if not meters: return

    emig_id = meters[0]['emigId']
    cfg = Config(api_key=JUGGLE_API_KEY, plant_uid=uid, start_date="20260201", end_date="20260205", min_interval_s=1800)
    try:
        readings = fetch_all_readings(cfg, emig_id)
        print(f"  Readings (Feb 1-5): {len(readings)}")
    except Exception as e:
        print(f"  Readings Error: {e}")

if __name__ == "__main__":
    for name, uid in SITES.items():
        check_site(name, uid)
