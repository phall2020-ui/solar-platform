import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))
from services.toolkit_bridge import toolkit
print('Toolkit available:', toolkit.is_available())
if toolkit.is_available():
    plants = toolkit.get_plants()
    print('Number of plants:', len(plants))
    for p in plants:
        print(p)
