
import sys
from unified_config import config

# Ensure Solar Toolkit is in path
if str(config.SOLAR_TOOLKIT_PATH) not in sys.path:
    sys.path.insert(0, str(config.SOLAR_TOOLKIT_PATH))

try:
    from services.toolkit_bridge import toolkit
    print(f"Toolkit Bridge Available: {toolkit.is_available()}")
    
    plants = toolkit.get_plants()
    print(f"\nFound {len(plants)} plants in Toolkit Database:")
    print("-" * 60)
    print(f"{'Alias':<30} | {'UID':<30}")
    print("-" * 60)
    for p in plants:
        alias = p.get('alias', 'N/A')
        uid = p.get('uid', 'N/A')
        print(f"{alias:<30} | {uid:<30}")
    print("-" * 60)

except Exception as e:
    print(f"Error: {e}")
