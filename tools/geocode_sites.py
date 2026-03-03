#!/usr/bin/env python3
"""
Geocode all sites in the solar portfolio using OpenStreetMap Nominatim API.

Usage:
    python tools/geocode_sites.py              # geocode and save to config/site_locations.json
    python tools/geocode_sites.py --dry-run    # print results without saving
    python tools/geocode_sites.py --force      # re-geocode even if file already exists
"""

import argparse
import json
import time
from pathlib import Path

import urllib.request
import urllib.parse

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "solar-platform-geocoder/1.0 (solar portfolio management)"
OUTPUT_PATH = Path(__file__).parent.parent / "config" / "site_locations.json"

# All 45 portfolio sites + Point Lane Solar Farm
# Platform data from sites_mapping.json
SITES_RAW = [
    {"name": "PPA Park Hall",                       "platform": "solaredge", "site_id": "4667531",                    "juggle_uid": "?"},
    {"name": "PPA Uniroyal Global",                 "platform": "solaredge", "site_id": "3933004",                    "juggle_uid": "?"},
    {"name": "PPA Shawton Engineering Ltd",         "platform": "solaredge", "site_id": "2798969",                    "juggle_uid": "?"},
    {"name": "PPA Princes Tuna",                    "platform": "solaredge", "site_id": "4209270",                    "juggle_uid": "?"},
    {"name": "PPA Panorama Kitchens",               "platform": "solaredge", "site_id": "4519032",                    "juggle_uid": "?"},
    {"name": "PPA WALC Adult Learning Centre",      "platform": "solaredge", "site_id": "3829329",                    "juggle_uid": "?"},
    {"name": "PPA Dunham Forest Golf Club",         "platform": "solaredge", "site_id": "3490228",                    "juggle_uid": "?"},
    {"name": "PPA Burnley College",                 "platform": "solaredge", "site_id": "2733539",                    "juggle_uid": "?"},
    {"name": "PPA Bannatynes Wildmoor",             "platform": "solaredge", "site_id": "4338522",                    "juggle_uid": "?"},
    {"name": "Smeed Dean Works Final",              "platform": "solaredge", "site_id": "4724518",                    "juggle_uid": "?"},
    {"name": "PPA WALC Pagefield",                  "platform": "solaredge", "site_id": "3823337",                    "juggle_uid": "?"},
    {"name": "PPA WALC Leigh College",              "platform": "solaredge", "site_id": "3888537",                    "juggle_uid": "?"},
    {"name": "PPA Valley Hydraulics",               "platform": "solaredge", "site_id": "2626861",                    "juggle_uid": "?"},
    {"name": "PPA Swift Dental Group",              "platform": "solaredge", "site_id": "3656221",                    "juggle_uid": "?"},
    {"name": "PPA Ink Tech",                        "platform": "solaredge", "site_id": "4625192",                    "juggle_uid": "?"},
    {"name": "PPA I&N Fabrications Ltd",            "platform": "solaredge", "site_id": "2688590",                    "juggle_uid": "?"},
    {"name": "PPA Bannatynes Weybridge",            "platform": "solaredge", "site_id": "4283465",                    "juggle_uid": "?"},
    {"name": "PPA Bannatynes Norwich",              "platform": "solaredge", "site_id": "4319038",                    "juggle_uid": "?"},
    {"name": "PPA Bannatynes Darlington Head Office", "platform": "solaredge", "site_id": "4307544",                  "juggle_uid": "?"},
    {"name": "PPA Bannatynes Cookridge Hall",       "platform": "solaredge", "site_id": "4361798",                    "juggle_uid": "?"},
    {"name": "PPA Bannatynes Colchester Kingsford Park", "platform": "solaredge", "site_id": "4320553",               "juggle_uid": "?"},
    {"name": "PPA Bannatynes Bury St Edmunds",      "platform": "solaredge", "site_id": "4309872",                    "juggle_uid": "?"},
    {"name": "PPA Bannatynes Braintree",            "platform": "solaredge", "site_id": "4284090",                    "juggle_uid": "?"},
    {"name": "CASEPAK SUNNINGDALE",                 "platform": "solaredge", "site_id": "4756575",                    "juggle_uid": "?"},
    {"name": "Blachford UK",                        "platform": "solaredge", "site_id": "4466155",                    "juggle_uid": "AMP:00024"},
    {"name": "Newfold Farm",                        "platform": "juggle",    "site_id": "",                           "juggle_uid": "ERS:00001"},
    {"name": "Cromwell Tools",                      "platform": "juggle",    "site_id": "",                           "juggle_uid": "AMP:00001"},
    {"name": "Man City FC Training Ground",         "platform": "juggle",    "site_id": "",                           "juggle_uid": "AMP:00019"},
    {"name": "Sheldons Bakery",                     "platform": "juggle",    "site_id": "",                           "juggle_uid": "AMP:00020"},
    {"name": "Merry Hill Shopping Centre",          "platform": "juggle",    "site_id": "",                           "juggle_uid": "AMP:00025"},
    {"name": "Metrocentre",                         "platform": "juggle",    "site_id": "",                           "juggle_uid": "AMP:00027"},
    {"name": "FloPlast",                            "platform": "juggle",    "site_id": "",                           "juggle_uid": "AMP:00032"},
    {"name": "Smeed Dean Works",                    "platform": "juggle",    "site_id": "",                           "juggle_uid": "AMP:00034"},
    {"name": "NIC Barking",                         "platform": "juggle",    "site_id": "",                           "juggle_uid": "AMP:00035"},
    {"name": "Finlay Beverages",                    "platform": "solis",     "site_id": "1298491919450070492",        "juggle_uid": "AMP:00031"},
    {"name": "Haverhill",                           "platform": "solis",     "site_id": "1298491919449993293",        "juggle_uid": "?"},
    {"name": "Sofina Foods",                        "platform": "solis",     "site_id": "1298491919449993293",        "juggle_uid": "AMP:00029"},
    {"name": "Smithy's Mushrooms PH1",              "platform": "solis",     "site_id": "1298491919449898612",        "juggle_uid": "AMP:00028"},
    {"name": "Smithy's Mushrooms PH2",              "platform": "solis",     "site_id": "1298491919449898612",        "juggle_uid": "AMP:00033"},
    {"name": "Smithy's Mushrooms PH1+2",            "platform": "solis",     "site_id": "1298491919449898612",        "juggle_uid": "AMP:00036"},
    {"name": "Parfetts Birmingham",                 "platform": "solis",     "site_id": "1298491919449855581",        "juggle_uid": "AMP:00026"},
    {"name": "FALTEC Europe Ltd",                   "platform": "solis",     "site_id": "1298491919449813631",        "juggle_uid": "?"},
    {"name": "Hibernian Training Ground",           "platform": "solis",     "site_id": "1298491919449006183",        "juggle_uid": "AMP:00003"},
    {"name": "Hibernian Stadium",                   "platform": "solis",     "site_id": "1298491919449005781",        "juggle_uid": "AMP:00002"},
    {"name": "Besblock",                            "platform": "solis",     "site_id": "1298491919448677612",        "juggle_uid": "?"},
    # FusionSolar ground-mount farm
    {"name": "Point Lane Solar Farm",              "platform": "fusionsolar", "site_id": "NE=YOUR_CODE",              "juggle_uid": "?", "capacity_kwp": 8601},
]

# Custom Nominatim search queries — override the default "{name}, UK" search
CUSTOM_QUERIES: dict[str, str] = {
    "PPA Park Hall":                         "Park Hall, Staffordshire, UK",
    "PPA Uniroyal Global":                   "Uniroyal Global, UK",
    "PPA Shawton Engineering Ltd":           "Shawton Engineering, UK",
    "PPA Princes Tuna":                      "Princes Tuna, Lincolnshire, UK",
    "PPA Panorama Kitchens":                 "Panorama Kitchens, UK",
    "PPA WALC Adult Learning Centre":        "Wigan Adult Learning Centre, UK",
    "PPA Dunham Forest Golf Club":           "Dunham Forest Golf Club, Altrincham, UK",
    "PPA Burnley College":                   "Burnley College, Burnley, UK",
    "PPA Bannatynes Wildmoor":               "Bannatyne Health Club Wildmoor, Bromsgrove, UK",
    "Smeed Dean Works Final":                "Smeed Dean, Sittingbourne, UK",
    "PPA WALC Pagefield":                    "Pagefield, Wigan, UK",
    "PPA WALC Leigh College":                "Leigh College, Leigh, Wigan, UK",
    "PPA Valley Hydraulics":                 "Valley Hydraulics, UK",
    "PPA Swift Dental Group":                "Swift Dental Group, UK",
    "PPA Ink Tech":                          "Ink Tech, UK",
    "PPA I&N Fabrications Ltd":              "I&N Fabrications, UK",
    "PPA Bannatynes Weybridge":              "Bannatyne Health Club, Weybridge, UK",
    "PPA Bannatynes Norwich":                "Bannatyne Health Club, Norwich, UK",
    "PPA Bannatynes Darlington Head Office": "Bannatyne Group, Darlington, UK",
    "PPA Bannatynes Cookridge Hall":         "Cookridge Hall Golf Club, Leeds, UK",
    "PPA Bannatynes Colchester Kingsford Park": "Bannatyne Health Club, Colchester, UK",
    "PPA Bannatynes Bury St Edmunds":        "Bannatyne Health Club, Bury St Edmunds, UK",
    "PPA Bannatynes Braintree":              "Bannatyne Health Club, Braintree, UK",
    "CASEPAK SUNNINGDALE":                   "Sunningdale, Berkshire, UK",
    "Blachford UK":                          "Blachford, UK",
    "Newfold Farm":                          "Newfold Farm, UK",
    "Cromwell Tools":                        "Cromwell Tools, Leicester, UK",
    "Man City FC Training Ground":           "Manchester City Football Club Training Ground, Manchester, UK",
    "Sheldons Bakery":                       "Sheldons Bakery, UK",
    "Merry Hill Shopping Centre":            "Merry Hill Shopping Centre, Dudley, UK",
    "Metrocentre":                           "Metro Centre, Gateshead, UK",
    "FloPlast":                              "FloPlast, Rochester, Kent, UK",
    "Smeed Dean Works":                      "Smeed Dean, Sittingbourne, UK",
    "NIC Barking":                           "NIC, Barking, London, UK",
    "Finlay Beverages":                      "Finlay Beverages, UK",
    "Haverhill":                             "Haverhill, Suffolk, UK",
    "Sofina Foods":                          "Sofina Foods, UK",
    "Smithy's Mushrooms PH1":               "Smithys Mushrooms, UK",
    "Smithy's Mushrooms PH2":               "Smithys Mushrooms, UK",
    "Smithy's Mushrooms PH1+2":             "Smithys Mushrooms, UK",
    "Parfetts Birmingham":                   "Parfetts, Birmingham, UK",
    "FALTEC Europe Ltd":                     "FALTEC Europe, UK",
    "Hibernian Training Ground":             "Hibernian FC Training Ground, Edinburgh, UK",
    "Hibernian Stadium":                     "Easter Road Stadium, Edinburgh, UK",
    "Besblock":                              "Besblock, UK",
    "Point Lane Solar Farm":                 "Burnley, Lancashire, UK",
}

# Manual coordinate overrides — used when geocoder fails or for accuracy
MANUAL_COORDS: dict[str, tuple[float, float]] = {
    "Man City FC Training Ground":           (53.4814, -2.2000),
    "Merry Hill Shopping Centre":            (52.4800, -2.1100),
    "Metrocentre":                           (54.9600, -1.6630),
    "Newfold Farm":                          (51.5000, -0.1000),  # placeholder — update when known
    "Point Lane Solar Farm":                 (53.7500, -2.6500),
    "Hibernian Stadium":                     (55.9614, -3.1653),
    "Hibernian Training Ground":             (55.9000, -3.1500),
    "PPA Burnley College":                   (53.7900, -2.2400),
    "PPA Bannatynes Darlington Head Office": (54.5236, -1.5572),
    "PPA Bannatynes Norwich":                (52.6300,  1.2900),
    "PPA Bannatynes Weybridge":              (51.3700, -0.4700),
    "PPA Bannatynes Colchester Kingsford Park": (51.8900, 0.9000),
    "PPA Bannatynes Bury St Edmunds":        (52.2436,  0.7148),
    "PPA Bannatynes Braintree":              (51.8800,  0.5500),
    "CASEPAK SUNNINGDALE":                   (51.4000, -0.6300),
    "Haverhill":                             (52.0800,  0.4400),
    "Parfetts Birmingham":                   (52.4862, -1.8904),
    "FloPlast":                              (51.3600,  0.6800),
    "Smeed Dean Works":                      (51.3700,  0.6600),
    "Smeed Dean Works Final":                (51.3700,  0.6600),
    "NIC Barking":                           (51.5400,  0.0800),
}

# Default tilt/azimuth/timezone for UK commercial rooftop; ground-mount sites override below
GROUND_MOUNT_SITES = {"Newfold Farm", "Point Lane Solar Farm"}


def geocode(query: str) -> tuple[float, float] | None:
    """Query Nominatim for the first result matching *query*. Returns (lat, lon) or None."""
    params = urllib.parse.urlencode({
        "q": query,
        "format": "jsonv2",
        "limit": 1,
        "countrycodes": "gb",
    })
    url = f"{NOMINATIM_URL}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        if data:
            return round(float(data[0]["lat"]), 6), round(float(data[0]["lon"]), 6)
    except Exception as exc:
        print(f"    [WARN] Nominatim error for '{query}': {exc}")
    return None


def _region(lat: float | None, lon: float | None) -> str:
    """Classify UK region. Heuristic based on lat/lon — correct for this portfolio."""
    if lat is None:
        return "Unknown"
    if lat > 55.0:
        return "Scotland"
    # Welsh sites: west of -2.7°, latitude 51.3–53.5°
    if lon is not None and lon < -2.7 and 51.3 < lat < 53.5:
        return "Wales"
    return "England"


def build_site_entry(raw: dict, lat: float | None, lon: float | None, source: str) -> dict:
    name = raw["name"]
    is_ground_mount = name in GROUND_MOUNT_SITES
    entry = {
        "name": name,
        "platform": raw["platform"],
        "site_id": raw.get("site_id", ""),
        "juggle_uid": raw.get("juggle_uid", "?"),
        "latitude": lat,
        "longitude": lon,
        "capacity_kwp": raw.get("capacity_kwp", None),
        "tilt_deg": 25.0 if is_ground_mount else 10.0,
        "azimuth_deg": 180.0,
        "timezone": "Europe/London",
        "region": _region(lat, lon),
        "_coord_source": source,
    }
    return entry


def main():
    parser = argparse.ArgumentParser(description="Geocode solar portfolio sites")
    parser.add_argument("--dry-run", action="store_true", help="Print results without saving")
    parser.add_argument("--force", action="store_true", help="Re-geocode even if output exists")
    args = parser.parse_args()

    if OUTPUT_PATH.exists() and not args.force and not args.dry_run:
        print(f"[INFO] Output already exists: {OUTPUT_PATH}")
        print("[INFO] Use --force to re-geocode, or --dry-run to preview without saving.")
        return

    results = []
    stats = {"geocoded": 0, "manual": 0, "null": 0}

    for i, raw in enumerate(SITES_RAW):
        name = raw["name"]
        print(f"[{i+1:2d}/{len(SITES_RAW)}] {name}")

        # 1. Check manual override first (skips network call)
        if name in MANUAL_COORDS:
            lat, lon = MANUAL_COORDS[name]
            print(f"         -> manual override: ({lat}, {lon})")
            entry = build_site_entry(raw, lat, lon, "manual")
            stats["manual"] += 1
        else:
            # 2. Try Nominatim
            query = CUSTOM_QUERIES.get(name, f"{name}, UK")
            print(f"         -> geocoding: '{query}'")
            coords = geocode(query)
            if coords:
                lat, lon = coords
                print(f"         -> found: ({lat}, {lon})")
                entry = build_site_entry(raw, lat, lon, "nominatim")
                stats["geocoded"] += 1
            else:
                print(f"         -> NOT FOUND — storing null")
                entry = build_site_entry(raw, None, None, "null")
                stats["null"] += 1
            # Rate-limit: 1 req/sec for Nominatim
            time.sleep(1)

        results.append(entry)

    output = {"sites": results}

    print("\n" + "="*60)
    print(f"Results: {stats['geocoded']} geocoded | {stats['manual']} manual | {stats['null']} null")
    print("="*60)

    if args.dry_run:
        print("\nDRY RUN — output (first 3 sites):")
        for s in results[:3]:
            print(json.dumps(s, indent=2))
        print(f"\n[dry-run] Would save to: {OUTPUT_PATH}")
    else:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_PATH, "w") as f:
            json.dump(output, f, indent=2)
        print(f"\nSaved to: {OUTPUT_PATH}")
        # Quick validate
        with open(OUTPUT_PATH) as f:
            loaded = json.load(f)
        print(f"Validated: {len(loaded['sites'])} sites in JSON")


if __name__ == "__main__":
    main()
