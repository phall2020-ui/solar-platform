import os
import requests
import json
from fetch_inverter_data import discover_plants

# Hardcode key for script
JUGGLE_API_KEY = "714f3647f0b54070a248c8b82531da47"

if __name__ == "__main__":
    print("Searching for plants using discover_plants()...")
    plants = discover_plants(JUGGLE_API_KEY)
    
    print("\n--- Discovered Plants ---")
    for p in plants:
        print(f"UID: {p['uid']} - Name: {p['name']}")
    
    # Also try brute force beyond AMP:00100 just in case
    # The discover_plants function already does some brute force (1-100)
    # Let's try expanding it if needed, but start with this.
