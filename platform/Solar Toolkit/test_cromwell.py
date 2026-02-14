"""Test script to fetch Cromwell Tools data and verify DB storage."""
import sys
sys.stdout.reconfigure(line_buffering=True)

from solar_toolkit.orchestrator import AnalysisOrchestrator
from datetime import datetime, timedelta

print("Starting test...", flush=True)

orch = AnalysisOrchestrator()

# Get all plants
plants = orch.get_plants()
print(f'Found {len(plants)} registered plants:', flush=True)
for p in plants:
    print(f"  - {p['alias']} ({p['plant_uid']})", flush=True)

# Find Cromwell Tools
cromwell = next((p for p in plants if 'cromwell' in p['alias'].lower()), None)

if not cromwell:
    print('Cromwell Tools not found in registered plants', flush=True)
else:
    print(f'\nFound Cromwell: {cromwell}', flush=True)
    plant_uid = cromwell['plant_uid']
    
    # Fetch data for past week
    end_date = datetime.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=7)
    
    start_str = start_date.strftime('%Y%m%d')
    end_str = end_date.strftime('%Y%m%d')
    
    print(f'Fetching data from {start_str} to {end_str}...', flush=True)
    count = orch.fetch_data(plant_uid, start_str, end_str)
    print(f'Fetched {count} readings', flush=True)
    
    # Verify data in DB
    print('\nVerifying data in database...', flush=True)
    inv_ids = cromwell.get('inverter_ids', [])
    if inv_ids:
        for inv_id in inv_ids[:2]:  # Check first 2 inverters
            readings = orch.store.query_readings(
                plant_uid, 
                inv_id, 
                start_date.strftime('%Y-%m-%dT00:00:00Z'), 
                end_date.strftime('%Y-%m-%dT23:59:59Z')
            )
            print(f'  {inv_id}: {len(readings)} readings in DB', flush=True)
            if readings:
                print(f'    Sample: {readings[0]}', flush=True)
    else:
        print('No inverter IDs registered for this plant', flush=True)

print("\nTest complete!", flush=True)
