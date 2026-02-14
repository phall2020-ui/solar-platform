import os
import requests
import json
from fetch_inverter_data import BASE_URL

JUGGLE_API_KEY = "714f3647f0b54070a248c8b82531da47"

def list_juggle_sites():
    print("Fetching site list from Juggle...")
    headers = {'Authorization': f'token {JUGGLE_API_KEY}'}
    
    # Just iterate likely IDs? No, there must be a list endpoint.
    # checking fetch_inverter_data.py or similar docs?
    # Usually /plant/ list? 
    # Use brute force check or known endpoint?
    # fetch_inverter_data.py didn't have a list_all function.
    
    # Try iterating AMP:00000 to AMP:00100?
    
    found = []
    for i in range(1, 100):
        uid = f"AMP:{i:05d}"
        url = f"{BASE_URL}/plant/{uid}"
        try:
            resp = requests.get(url, headers=headers, timeout=2)
            if resp.status_code == 200:
                data = resp.json()
                name = data.get('name')
                print(f"  {uid}: {name}")
                found.append((uid, name))
            elif resp.status_code == 421:
                pass # Not found
            elif resp.status_code == 401:
                pass # Auth error?
        except:
             pass
             
    print(f"Found {len(found)} sites.")

if __name__ == "__main__":
    list_juggle_sites()
