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

def rename_property(db_id, old_name, new_name):
    url = f"https://api.notion.com/v1/databases/{db_id}"
    payload = {
        "properties": {
            old_name: {"name": new_name}
        }
    }
    resp = requests.patch(url, headers=HEADERS, json=payload)
    if resp.status_code == 200:
        print(f"Successfully renamed '{old_name}' to '{new_name}'")
    else:
        print(f"Failed to rename '{old_name}': {resp.status_code} {resp.text}")

def main():
    if not NOTION_TOKEN:
        print("Missing NOTION_TOKEN env var")
        return

    db_id, props = find_db()
    if not db_id:
        print("Database not found")
        return

    print(f"Found DB: {db_id}")
    
    # Check for "Solis (Daily)"
    if "Solis (Daily)" in props:
        print("Renaming 'Solis (Daily)' to 'Platform (Daily)'...")
        rename_property(db_id, "Solis (Daily)", "Platform (Daily)")
    elif "Platform (Daily)" in props:
        print("'Platform (Daily)' already exists.")
    else:
        print("'Solis (Daily)' not found (and 'Platform (Daily)' missing).")

    # Check for "Solis (MTD)"
    if "Solis (MTD)" in props:
        print("Renaming 'Solis (MTD)' to 'Platform (MTD)'...")
        rename_property(db_id, "Solis (MTD)", "Platform (MTD)")
    elif "Platform (MTD)" in props:
        print("'Platform (MTD)' already exists.")
    else:
        print("'Solis (MTD)' not found.")

if __name__ == "__main__":
    main()
