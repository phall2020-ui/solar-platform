import os
import requests
import json
from datetime import datetime, timedelta

NOTION_TOKEN = os.environ.get('NOTION_TOKEN')
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

def find_db():
    url = "https://api.notion.com/v1/search"
    payload = {"query": "Meter / inverter comparison", "filter": {"value": "database", "property": "object"}}
    resp = requests.post(url, headers=HEADERS, json=payload)
    results = resp.json().get("results", [])
    if results:
        return results[0]["id"]
    return None

def check_update(db_id, site_name, date_str):
    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    payload = {
        "filter": {
            "and": [
                {"property": "Site", "title": {"equals": site_name}},
                {"property": "Date", "date": {"equals": date_str}}
            ]
        }
    }
    resp = requests.post(url, headers=HEADERS, json=payload)
    results = resp.json().get("results", [])
    
    if not results:
        print(f"No page found for {site_name} on {date_str}")
        return

    page = results[0]
    last_edited = page["last_edited_time"] # e.g. "2026-02-12T12:00:00.000Z"
    
    print(f"Page: {site_name} ({date_str})")
    print(f"Last Edited: {last_edited}")
    
    # Simple check
    # Parse?
    # 2026-02-12T...
    # Compare with now?
    # Just printing it is enough for visual verification.

if __name__ == "__main__":
    db_id = find_db()
    if db_id:
        # Check Park Hall for Feb 10
        check_update(db_id, "PPA Park Hall", "2026-02-10")
