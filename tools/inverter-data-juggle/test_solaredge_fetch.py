import os
import json
import solaredge_api
from datetime import datetime, timedelta

# Load keys
keys_json = os.environ.get('SOLAREDGE_KEYS_JSON', '{}')
keys = json.loads(keys_json)

if not keys:
    print("No keys found in SOLAREDGE_KEYS_JSON")
else:
    site_id = list(keys.keys())[0]
    api_key = keys[site_id]
    print(f"Testing with Site {site_id}...")
    
    details = solaredge_api.get_details(site_id, api_key)
    print("Details:", details)
    
    # Use recent dates
    end_date = datetime.now() - timedelta(days=1)
    start_date = end_date - timedelta(days=5)
    
    start = start_date.strftime("%Y-%m-%d")
    end = end_date.strftime("%Y-%m-%d")
    
    print(f"Fetching Energy from {start} to {end}...")
    energy = solaredge_api.get_energy(site_id, api_key, start, end)
    print(f"Energy:", energy)
