
import os
import requests
import sys

# Flush verify
print("Starting script...", flush=True)

with open("debug_log.txt", "w") as f:
    f.write("Starting script...\n")
    
    NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
    f.write(f"Token length: {len(NOTION_TOKEN)}\n")
    
    HEADERS = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    
    url = "https://api.notion.com/v1/search"
    payload = {"query": "Meter / inverter comparison", "filter": {"value": "database", "property": "object"}}
    
    try:
        f.write(f"Requesting {url}...\n")
        resp = requests.post(url, headers=HEADERS, json=payload, timeout=10)
        f.write(f"Status: {resp.status_code}\n")
        f.write(f"Response: {resp.text[:500]}\n")
        
        results = resp.json().get("results", [])
        f.write(f"Results count: {len(results)}\n")
        
        for db in results:
            title = db.get("title", [])
            name = title[0].get("plain_text", "") if title else ""
            f.write(f"DB: {name} => {db['id']}\n")
            
    except Exception as e:
        f.write(f"Error: {e}\n")

print("Script finished.", flush=True)
