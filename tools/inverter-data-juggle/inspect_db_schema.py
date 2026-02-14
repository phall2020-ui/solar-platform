
import requests
import json
import os

NOTION_TOKEN = os.environ.get('NOTION_TOKEN')
DB_ID = "3041773a-96c0-8150-b90e-d65a266ee6a7"

headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28"
}

resp = requests.get(f"https://api.notion.com/v1/databases/{DB_ID}", headers=headers)
if resp.status_code == 200:
    data = resp.json()
    props = data.get("properties", {})
    print(json.dumps(list(props.keys()), indent=2))
else:
    print(resp.text)
