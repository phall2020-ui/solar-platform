import requests
import os
from datetime import datetime, timedelta

NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

# Find DB ID (same logic as before)
def find_db():
    url = "https://api.notion.com/v1/search"
    payload = {"query": "Energy Comparison Portfolio (Daily)", "filter": {"value": "database", "property": "object"}}
    resp = requests.post(url, headers=HEADERS, json=payload)
    results = resp.json().get("results", [])
    if results: return results[0]["id"]
    return None

def verify_site(db_id, site_name):
    print(f"\nVerifying {site_name}...")
    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    # Query for the specific site and recent dates
    payload = {
        "filter": {
            "property": "Site",
            "title": {"equals": site_name}
        },
        "sorts": [{"property": "Date", "direction": "descending"}],
        "page_size": 5
    }
    resp = requests.post(url, headers=HEADERS, json=payload)
    results = resp.json().get("results", [])
    
    found_data = False
    for row in results:
        props = row["properties"]
        date = props["Date"]["date"]["start"]
        
        # Check Juggle columns
        j_inv = props.get("Juggle Inv (Daily)", {}).get("number")
        j_meter = props.get("Juggle Meter (Daily)", {}).get("number")
        
        # Check Platform columns
        p_day = props.get("Platform (Daily)", {}).get("number")
        
        print(f"  {date}: Juggle Inv={j_inv}, Juggle Meter={j_meter}, Platform={p_day}")
        
        if j_inv is not None and j_inv > 0:
            found_data = True

    if found_data:
        print(f"  [SUCCESS] Juggle data found for {site_name}")
    else:
        print(f"  [WARNING] No Juggle data found for {site_name}")

if __name__ == "__main__":
    db_id = find_db()
    if db_id:
        verify_site(db_id, "Hibernian Training Ground")
        verify_site(db_id, "Man City FC Training Ground")
        verify_site(db_id, "Hibernian Stadium")
    else:
        print("Database not found")
