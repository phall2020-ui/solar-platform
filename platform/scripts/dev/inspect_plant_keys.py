
import sys
from unified_config import config
import json

if str(config.SOLAR_TOOLKIT_PATH) not in sys.path:
    sys.path.insert(0, str(config.SOLAR_TOOLKIT_PATH))

try:
    from services.toolkit_bridge import toolkit
    plants = toolkit.get_plants()
    if plants:
        p = plants[0]
        print("Keys of first plant object:", p.keys())
        print("Full object dump:", json.dumps(p, default=str, indent=2))
    else:
        print("No plants found.")

except Exception as e:
    print(e)
