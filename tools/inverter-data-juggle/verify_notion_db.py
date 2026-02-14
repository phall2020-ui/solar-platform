"""
Verify Notion DB contents — paginated query of all rows,
grouped by date, showing counts and sample values.
"""
import requests, json, sys
from collections import defaultdict

NOTION_TOKEN = "ntn_T62952956806aoQrHpKS8stIuHcWDsxx7zUY0yF7QHZ41d"
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

def find_db():
    url = "https://api.notion.com/v1/search"
    payload = {"query": "Meter / inverter comparison", "filter": {"value": "database", "property": "object"}}
    resp = requests.post(url, headers=HEADERS, json=payload)
    for db in resp.json().get("results", []):
        title = db.get("title", [])
        name = title[0].get("plain_text", "") if title else ""
        print(f"  DB: {name!r} => {db['id']}")
    # Return the Daily one
    for db in resp.json().get("results", []):
        title = db.get("title", [])
        name = title[0].get("plain_text", "") if title else ""
        if "Meter / inverter comparison" in name:
            return db["id"], name
    # Fallback to first
    if resp.json().get("results"):
        db = resp.json()["results"][0]
        title = db.get("title", [])
        name = title[0].get("plain_text", "") if title else ""
        return db["id"], name
    return None, None

def query_all_pages(db_id):
    """Paginate through all pages in the database."""
    all_rows = []
    has_more = True
    start_cursor = None
    
    while has_more:
        payload = {"page_size": 100}
        if start_cursor:
            payload["start_cursor"] = start_cursor
        
        url = f"https://api.notion.com/v1/databases/{db_id}/query"
        resp = requests.post(url, headers=HEADERS, json=payload)
        data = resp.json()
        
        results = data.get("results", [])
        all_rows.extend(results)
        
        has_more = data.get("has_more", False)
        start_cursor = data.get("next_cursor")
        print(f"  Fetched {len(results)} rows (total: {len(all_rows)}, has_more: {has_more})", flush=True)
    
    return all_rows

def main():
    print("=" * 60)
    print("NOTION DATABASE VERIFICATION")
    print("=" * 60)
    
    db_id, db_name = find_db()
    if not db_id:
        print("No database found!")
        return
    
    print(f"\nUsing DB: {db_name} ({db_id})")
    print("\nFetching all rows...")
    rows = query_all_pages(db_id)
    print(f"\nTotal rows: {len(rows)}")
    
    # Parse and group
    by_date = defaultdict(list)
    by_site = defaultdict(list)
    
    for row in rows:
        props = row["properties"]
        try:
            site = props["Site"]["title"][0]["text"]["content"]
            date_val = props["Date"]["date"]["start"] if props["Date"]["date"] else "NO_DATE"
        except:
            site = "UNKNOWN"
            date_val = "NO_DATE"
        
        # Get a sample value
        inv_d = None
        for key in ["Juggle Inv (Daily)", "Juggle Inv Day (kWh)"]:
            if key in props and props[key].get("number") is not None:
                inv_d = props[key]["number"]
                break
        
        by_date[date_val].append({"site": site, "inv": inv_d})
        by_site[site].append({"date": date_val, "inv": inv_d})
    
    # Report by date
    print("\n" + "=" * 60)
    print("ROWS BY DATE:")
    print("=" * 60)
    for dt in sorted(by_date.keys()):
        entries = by_date[dt]
        non_zero = sum(1 for e in entries if e["inv"] and e["inv"] > 0)
        print(f"  {dt}: {len(entries)} sites ({non_zero} with data)")
    
    # Report by site (sample)
    print("\n" + "=" * 60)
    print("SAMPLE: Newfold Farm by date:")
    print("=" * 60)
    for entry in sorted(by_site.get("Newfold Farm", []), key=lambda x: x["date"]):
        print(f"  {entry['date']}: Inv={entry['inv']}")
    
    # Also check Cromwell Tools
    print("\nSAMPLE: Cromwell Tools by date:")
    for entry in sorted(by_site.get("Cromwell Tools", []), key=lambda x: x["date"]):
        print(f"  {entry['date']}: Inv={entry['inv']}")

if __name__ == "__main__":
    main()
