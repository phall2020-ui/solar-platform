"""
Juggle Energy API Client
========================

Fetches plant, meter, and inverter data from the Juggle Energy REST API.
Documentation: Juggle-JSON-API-1.4.pdf
Base URL: https://www.emig.co.uk/p/api
"""

import os
import requests
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

BASE_URL = "https://www.emig.co.uk/p/api"
DEFAULT_TIMEOUT = 30

def _get_headers(api_key: str) -> Dict[str, str]:
    return {"Authorization": f"token {api_key}"}

def get_plant_list(api_key: str) -> List[Dict[str, Any]]:
    """List all plants accessible by the API key."""
    url = f"{BASE_URL}/plant-list"
    try:
        resp = requests.get(url, headers=_get_headers(api_key), timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        print(f"Error fetching plant list: {e}")
        return []

def get_plant_details(plant_uid: str, api_key: str) -> Dict[str, Any]:
    """Get detailed plant information including devices/meters."""
    url = f"{BASE_URL}/plant/{plant_uid}"
    try:
        resp = requests.get(url, headers=_get_headers(api_key), timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        print(f"Error fetching plant details for {plant_uid}: {e}")
        return {}

def get_meter_details(emig_id: str, api_key: str) -> Dict[str, Any]:
    """Get detailed meter information including last reading."""
    url = f"{BASE_URL}/meter/{emig_id}"
    try:
        resp = requests.get(url, headers=_get_headers(api_key), timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        print(f"Error fetching meter details for {emig_id}: {e}")
        return {}

def get_readings(emig_id: str, api_key: str, start_date: str, end_date: str, min_interval_s: int = 1800) -> List[Dict[str, Any]]:
    """
    Get historical readings for a device.
    start_date: YYYYMMDD
    end_date: YYYYMMDD
    """
    url = f"{BASE_URL}/meter/{emig_id}/readings"
    params = {
        "startDate": start_date,
        "endDate": end_date,
        "minIntervalS": min_interval_s
    }
    try:
        resp = requests.get(url, headers=_get_headers(api_key), params=params, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        return resp.json().get("readings", [])
    except requests.RequestException as e:
        print(f"Error fetching readings for {emig_id}: {e}")
        return []

def get_site_status_summary(plant_uid: str, api_key: str) -> Dict[str, Any]:
    """
    Helper to get a summary of all devices in a plant and their latest state.
    """
    plant = get_plant_details(plant_uid, api_key)
    if not plant:
        return {}
    
    summary = {
        "name": plant.get("name"),
        "uid": plant_uid,
        "inverters": [],
        "meters": [],
        "status": "OK"
    }
    
    for device in plant.get("meters", []):
        emig_id = device.get("emigId")
        dtype = device.get("type")
        
        details = get_meter_details(emig_id, api_key)
        if not details:
            continue
            
        status = {
            "id": emig_id,
            "type": dtype,
            "description": device.get("description"),
            "last_reading": None,
            "power_w": 0,
        }
        
        # Extract last reading timestamp
        for field in ['importEnergy', 'exportEnergy', 'importActivePower']:
            if field in details and 'ts' in details[field]:
                status["last_reading"] = details[field]['ts']
                break
        
        # Extract power
        if 'importActivePower' in details:
            status["power_w"] = details['importActivePower'].get('value', 0)
            
        if dtype == "INVERTER":
            summary["inverters"].append(status)
        else:
            summary["meters"].append(status)
            
    return summary

if __name__ == "__main__":
    # Test discovery
    key = os.environ.get("JUGGLE_API_KEY")
    if key:
        print("Plants:")
        for p in get_plant_list(key):
            print(f"- {p.get('plantUID')}: {p.get('name')}")
    else:
        print("JUGGLE_API_KEY not set")
