import os
import requests
import json
from fetch_inverter_data import discover_plants, BASE_URL

# Key found in debug_juggle_fetch.py
JUGGLE_API_KEY = "380fe299-a626-48f1-8456-e701c7383a23"

def check_key():
    print(f"Testing Key: {JUGGLE_API_KEY}")
    
    # 1. Try Discover Plants
    try:
        plants = discover_plants(JUGGLE_API_KEY)
        print(f"Discovery Found: {len(plants)} plants")
        for p in plants:
            print(f"  {p['uid']}: {p['name']}")
    except Exception as e:
        print(f"Discovery Error: {e}")

    # 2. Try Fetching Data for a known good site (Park Hall AMP:00045)
    # Check if we can get meter list first
    uid = "AMP:00045"
    url = f"{BASE_URL}/plant/{uid}"
    headers = {"Authorization": f"token {JUGGLE_API_KEY}"}
    try:
        resp = requests.get(url, headers=headers)
        print(f"Plant {uid} Check: {resp.status_code}")
        if resp.status_code == 200:
            print("  Plant Name:", resp.json().get('name'))
    except Exception as e:
        print(f"Plant Check Error: {e}")

if __name__ == "__main__":
    check_key()
