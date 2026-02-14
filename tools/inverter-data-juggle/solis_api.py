"""
Solis Cloud API Client
======================

Fetches inverter generation data from the Solis Cloud API for comparison
with Juggle/EMIG data.

Authentication: HMAC-SHA1 signed requests per Solis Cloud API v2 spec.
"""

import io
import hashlib
import hmac
import base64
import json
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import requests

# Force UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Solis API Configuration
# ---------------------------------------------------------------------------

SOLIS_API_URL = os.environ.get("SOLIS_API_URL") or "https://www.soliscloud.com:13333"
SOLIS_KEY_ID = os.environ.get("SOLIS_KEY_ID") or "1300386381677701029"
SOLIS_KEY_SECRET = os.environ.get("SOLIS_KEY_SECRET") or "dae233aa6c484de59fff0aa73c126cbf"

# ---------------------------------------------------------------------------
# HMAC Authentication
# ---------------------------------------------------------------------------

def _make_auth_headers(body: str, resource: str) -> Dict[str, str]:
    """
    Build the required Solis Cloud API v2 authentication headers.
    
    Signature = Base64(HMAC-SHA1(KeySecret,
        VERB + "\n" +
        Content-MD5 + "\n" +
        Content-Type + "\n" +
        Date + "\n" +
        CanonicalizedResource
    ))
    """
    content_type = "application/json"
    
    # Content-MD5
    md5_hash = hashlib.md5(body.encode("utf-8")).digest()
    content_md5 = base64.b64encode(md5_hash).decode("utf-8")
    
    # Date in GMT format
    date_str = datetime.now(tz=__import__('datetime').timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
    
    # String to sign
    sign_str = f"POST\n{content_md5}\n{content_type}\n{date_str}\n{resource}"
    
    # HMAC-SHA1
    hmac_obj = hmac.new(
        SOLIS_KEY_SECRET.encode("utf-8"),
        sign_str.encode("utf-8"),
        hashlib.sha1,
    )
    signature = base64.b64encode(hmac_obj.digest()).decode("utf-8")
    
    return {
        "Content-Type": content_type,
        "Content-MD5": content_md5,
        "Date": date_str,
        "Authorization": f"API {SOLIS_KEY_ID}:{signature}",
    }


def solis_post(resource: str, body: dict) -> dict:
    """Make an authenticated POST to the Solis Cloud API."""
    body_str = json.dumps(body)
    headers = _make_auth_headers(body_str, resource)
    url = f"{SOLIS_API_URL}{resource}"
    
    resp = requests.post(url, headers=headers, data=body_str, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    
    if data.get("success") is False:
        raise RuntimeError(f"Solis API error: {data.get('msg', data)}")
    
    return data


# ---------------------------------------------------------------------------
# Station (Plant) Discovery
# ---------------------------------------------------------------------------

def list_stations(page: int = 1, page_size: int = 100) -> dict:
    """List all stations (plants) visible to this API key."""
    return solis_post("/v1/api/userStationList", {
        "pageNo": page,
        "pageSize": page_size,
    })


def get_station_detail(station_id: str) -> dict:
    """Get detail for a single station."""
    return solis_post("/v1/api/stationDetail", {
        "id": station_id,
    })


# ---------------------------------------------------------------------------
# Inverter Discovery & Data
# ---------------------------------------------------------------------------

def list_inverters(station_id: str, page: int = 1, page_size: int = 100) -> dict:
    """List all inverters for a station."""
    return solis_post("/v1/api/inverterList", {
        "stationId": station_id,
        "pageNo": page,
        "pageSize": page_size,
    })


def get_inverter_detail(inverter_id: str) -> dict:
    """Get detail for a single inverter."""
    return solis_post("/v1/api/inverterDetail", {
        "id": inverter_id,
    })


def get_inverter_day(inverter_id: str, date_str: str) -> dict:
    """
    Get daily generation data for an inverter.
    date_str: YYYY-MM-DD format
    """
    return solis_post("/v1/api/inverterDay", {
        "id": inverter_id,
        "money": "GBP",
        "time": date_str,
        "timeZone": 0,
    })


def get_station_day(station_id: str, date_str: str) -> dict:
    """
    Get daily generation data for a station.
    date_str: YYYY-MM-DD format
    """
    return solis_post("/v1/api/stationDay", {
        "id": station_id,
        "money": "GBP",
        "time": date_str,
        "timeZone": 0,
    })


def get_station_month(station_id: str, month_str: str) -> dict:
    """
    Get monthly generation data for a station (returns daily list).
    month_str: YYYY-MM format
    """
    return solis_post("/v1/api/stationMonth", {
        "id": station_id,
        "money": "GBP",
        "month": month_str,
    })


# ---------------------------------------------------------------------------
# Main Discovery Script
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 80)
    print("  SOLIS CLOUD API — Station & Inverter Discovery")
    print("=" * 80)
    print(f"  API URL: {SOLIS_API_URL}")
    print(f"  Key ID:  {SOLIS_KEY_ID[:10]}...")
    print()
    
    # 1. List all stations
    print("Fetching station list...")
    try:
        result = list_stations()
        stations = result.get("data", {}).get("page", {}).get("records", [])
        total = result.get("data", {}).get("page", {}).get("total", 0)
        print(f"  Found {len(stations)} stations (total: {total})\n")
    except Exception as e:
        print(f"  ERROR: {e}")
        # Try alternate response format
        try:
            result = list_stations()
            print(f"  Raw response: {json.dumps(result, indent=2)[:2000]}")
        except:
            pass
        sys.exit(1)
    
    # 2. For each station, list inverters and get yesterday's generation
    yesterday = (datetime.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    for station in stations:
        sid = station.get("id") or station.get("stationId")
        sname = station.get("sno") or station.get("stationName") or station.get("name") or str(sid)
        capacity = station.get("capacity") or station.get("installedCapacity") or "?"
        
        print(f"\n{'─'*80}")
        print(f"  Station: {sname} (ID: {sid})")
        print(f"  Capacity: {capacity} kW")
        
        # Get station daily generation
        try:
            day_data = get_station_day(str(sid), yesterday)
            station_gen = day_data.get("data", {})
            energy_today = station_gen.get("energy") or station_gen.get("eToday") or "?"
            print(f"  Generation ({yesterday}): {energy_today} kWh")
        except Exception as e:
            print(f"  Station day data: {e}")
        
        # List inverters
        try:
            inv_result = list_inverters(str(sid))
            inverters = inv_result.get("data", {}).get("page", {}).get("records", [])
            print(f"  Inverters: {len(inverters)}")
            
            for inv in inverters:
                iid = inv.get("id") or inv.get("inverterId")
                isno = inv.get("sn") or inv.get("inverterSn") or str(iid)
                ipower = inv.get("pac") or inv.get("power") or "?"
                ienergy = inv.get("eToday") or inv.get("energyToday") or "?"
                print(f"    Inverter {isno}: {ienergy} kWh today, {ipower} W current")
        except Exception as e:
            print(f"  Inverter list: {e}")
        
        time.sleep(0.3)  # Rate limit
    
    print(f"\n{'='*80}")
    print("  Discovery complete.")
