import requests
import json
import os

NOTION_TOKEN = "ntn_T62952956806aoQrHpKS8stIuHcWDsxx7zUY0yF7QHZ41d"
# The script output log didn't print the DB ID explicitly, so we must find it again.
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

def find_db():
    url = "https://api.notion.com/v1/search"
    payload = {"query": "Energy Comparison Portfolio (Daily)", "filter": {"value": "database", "property": "object"}}
    resp = requests.post(url, headers=HEADERS, json=payload)
    results = resp.json().get("results", [])
    if results:
        return results[0]["id"]
    return None

def list_rows(db_id):
    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    payload = {
        "sorts": [
            {"property": "Date", "direction": "descending"}
        ]
    }
    resp = requests.post(url, headers=HEADERS, json=payload)
    results = resp.json().get("results", [])
    
    print(f"Found {len(results)} rows.")
    for row in results:
        props = row["properties"]
        try:
            site = props["Site"]["title"][0]["text"]["content"]
            date = props["Date"]["date"]["start"]
            juggle_d = props.get("Juggle Inv (Daily)", {}).get("number")
            print(f"{date} - {site}: Juggle={juggle_d}")
        except Exception as e:
            print(f"Error parsing row: {e}")

if __name__ == "__main__":
    db_id = find_db()
    if db_id:
        print(f"Database ID: {db_id}")
        list_rows(db_id)
    else:
        print("Database not found.")
