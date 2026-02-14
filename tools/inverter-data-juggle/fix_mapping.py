import json
import requests
from fetch_inverter_data import discover_plants

# Current Mapping (Load locally to safe keep)
with open('sites_mapping.json', 'r') as f:
    mapping = json.load(f)

# API Key (verified working for list)
JUGGLE_API_KEY = "380fe299-a626-48f1-8456-e701c7383a23"

# 1. Discover actual sites
print("Discovering sites...")
discovered = discover_plants(JUGGLE_API_KEY)
print(f"Found {len(discovered)} sites via API.")

# Create lookup by Name (normalized)
api_sites = {}
for d in discovered:
    # Normalize name: lower, strip
    norm_name = d['name'].lower().strip()
    api_sites[norm_name] = d['uid']
    # Also handle some known variations if needed
    if "hibernian stadium" in norm_name:
        api_sites["hibernian stadium"] = d['uid']
    if "training ground" in norm_name:
        api_sites["hibernian training ground"] = d['uid']
        api_sites["hibernian fc training centre"] = d['uid']

# 2. Update Mapping
updated_mapping = mapping.copy()
updates_log = []

for map_name, info in mapping.items():
    current_uid = info.get('juggle_uid')
    norm_map_name = map_name.lower().strip()
    
    # Try to find in API list
    found_uid = api_sites.get(norm_map_name)
    
    # Specific manual overrides purely based on string similarity observed
    if not found_uid:
        if "parfetts" in norm_map_name and "birmingham" in norm_map_name:
             # Look for api site with parfetts and birmingham
             for aname, auid in api_sites.items():
                 if "parfetts" in aname and "birmingham" in aname:
                     found_uid = auid
                     break
        elif "smithy's mushrooms ph1" == map_name: # Exact match attempt failed?
             found_uid = api_sites.get("smithy's mushrooms ph1") # Should match if name is exact
        elif "sofina" in norm_map_name:
             for aname, auid in api_sites.items():
                 if "sofina" in aname:
                     found_uid = auid
                     break

    if found_uid:
        if current_uid != found_uid:
            info['juggle_uid'] = found_uid
            updates_log.append(f"Updated {map_name}: {current_uid} -> {found_uid}")
    else:
        # Not found in API list
        if current_uid and current_uid != "?":
            # Check if it was one of the "known" good ones? 
            # If it's not in discovery, we assume it's NOT on Juggle (per user instruction)
            # BUT: Park Hall was missing. User might mean "Some sites are not on juggle" = "Don't expect them all to be there"
            # So we set to "?" to avoid errors
            info['juggle_uid'] = "?"
            updates_log.append(f"Disabled {map_name}: {current_uid} -> ? (Not found in API)")

# 3. Save
with open('sites_mapping.json', 'w') as f:
    json.dump(updated_mapping, f, indent=4)

print("\nUpdates Applied:")
for log in updates_log:
    print(log)
