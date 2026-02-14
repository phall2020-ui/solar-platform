import requests
import json

BASE_URL = "https://www.emig.co.uk/p/api"
JUGGLE_API_KEY = "380fe299-a626-48f1-8456-e701c7383a23"

def list_sites():
    print("Listing all sites...")
    headers = {'Authorization': f'token {JUGGLE_API_KEY}'}
    
    # We will just check 1-50 to be safe and find them by name
    for i in range(1, 60):
        uid = f"AMP:{i:05d}"
        try:
            resp = requests.get(f"{BASE_URL}/plant/{uid}", headers=headers, timeout=2)
            if resp.status_code == 200:
                data = resp.json()
                name = data.get('name')
                print(f"{uid}: {name}")
        except:
            pass

if __name__ == "__main__":
    list_sites()
