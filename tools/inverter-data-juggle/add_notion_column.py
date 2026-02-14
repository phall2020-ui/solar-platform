import os
import requests
import json

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
    for db in results:
        title = db.get("title", [])
        name = title[0].get("plain_text", "") if title else ""
        if name == "Meter / inverter comparison":
            return db["id"], db["properties"]
    return None, None

def add_platform_column(db_id):
    url = f"https://api.notion.com/v1/databases/{db_id}"
    payload = {
        "properties": {
            "Platform": {"select": {}}
        }
    }
    resp = requests.patch(url, headers=HEADERS, json=payload)
    if resp.status_code == 200:
        print("Successfully added 'Platform' column.")
    else:
        print(f"Failed to add 'Platform' column: {resp.status_code} {resp.text}")

def main():
    if not NOTION_TOKEN:
        print("Missing NOTION_TOKEN env var")
        return

    db_id, props = find_db()
    if not db_id:
        print("Database not found")
        return

    print(f"Found DB: {db_id}")
    
    if "Platform" not in props:
        print("Adding 'Platform' column...")
        add_platform_column(db_id)
    else:
        print("'Platform' column already exists.")

if __name__ == "__main__":
    main()
