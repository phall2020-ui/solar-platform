import sys
from pathlib import Path

# Add unified_app to sys.path
sys.path.append(str(Path(__file__).parent))

from services.toolkit_bridge import toolkit

if not toolkit.is_available():
    print('Toolkit not available')
else:
    plants = toolkit.get_plants()
    print(f'Number of plants: {len(plants)}')
    for p in plants:
        print(p)
