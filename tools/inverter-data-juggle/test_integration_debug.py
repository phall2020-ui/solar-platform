import os
import json
import time
import requests
import solaredge_api

# Load SolarEdge Keys
keys_json = os.environ.get('SOLAREDGE_KEYS_JSON', '{}')
try:
    SOLAREDGE_KEYS = json.loads(keys_json)
except:
    SOLAREDGE_KEYS = {}

def test_solaredge():
    print("Testing SolarEdge Fetch...")
    if not SOLAREDGE_KEYS:
        print("No SolarEdge keys found!")
        return

    site_id = list(SOLAREDGE_KEYS.keys())[0]
    api_key = SOLAREDGE_KEYS[site_id]
    print(f"  Using Site {site_id}")
    
    start = "2024-02-01"
    end = "2024-02-05"
    try:
        data = solaredge_api.get_energy(site_id, api_key, start, end)
        print(f"  Result: {data}")
    except Exception as e:
        print(f"  Error: {e}")

def test_notion_query():
    print("\nTesting Notion Query Speed...")
    token = os.environ.get('NOTION_TOKEN')
    if not token:
        print("No Notion Token!")
        return
        
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    
    # helper to find db
    url = "https://api.notion.com/v1/search"
    payload = {"query": "Meter / inverter comparison", "filter": {"value": "database", "property": "object"}}
    resp = requests.post(url, headers=headers, json=payload)
    results = resp.json().get("results", [])
    if not results:
        print("DB not found")
        return
    db_id = results[0]["id"]
    print(f"  DB ID: {db_id}")
    
    # Query for a date
    date_str = "2026-02-01"
    print(f"  Querying for {date_str}...")
    start_time = time.time()
    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    payload = {
        "filter": {"property": "Date", "date": {"equals": date_str}}
    }
    resp = requests.post(url, headers=headers, json=payload)
    end_time = time.time()
    print(f"  Query took {end_time - start_time:.2f}s")
    data = resp.json()
    print(f"  Results: {len(data.get('results', []))}")

if __name__ == "__main__":
    test_solaredge()
    test_notion_query()
