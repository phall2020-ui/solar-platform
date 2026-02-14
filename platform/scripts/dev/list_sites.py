import sys
from pathlib import Path

# Add unified_app path
sys.path.append(str(Path(__file__).parent))

from services.reporting_bridge import reporting

sites = reporting.get_table_data('solar_data')
if sites is not None:
    uniq = sites['Site'].dropna().unique()
    print('Distinct sites in reporting DB:')
    for s in uniq:
        print('-', s)
else:
    print('No data')
