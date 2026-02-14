from solar_toolkit.plant_registry_store import PlantStore
from solar_toolkit.config import settings

store = PlantStore(settings.DB_PATH)

# Load plant info
plant = store.load("ERS:00001")
if not plant:
    print("Plant ERS:00001 not found.")
    exit(1)

plant_uid = plant["plant_uid"]
inverter_ids = plant["inverter_ids"]
poa_id = f"POA:{'ERS_00001'.replace(' ', '_').upper()}"

# Get first 10 inverter readings
print("\n--- First 10 Inverter Readings ---")
for emig_id in inverter_ids:
    readings = store.query_readings(plant_uid, emig_id, "2000-01-01T00:00:00Z", "2100-01-01T00:00:00Z")
    for r in readings[:10]:
        print(r)
    print(f"(Total for {emig_id}: {len(readings)})\n")

# Get first 10 POA readings
print("\n--- First 10 POA Readings ---")
poa_readings = store.query_readings(plant_uid, poa_id, "2000-01-01T00:00:00Z", "2100-01-01T00:00:00Z")
for r in poa_readings[:10]:
    print(r)
print(f"(Total POA readings: {len(poa_readings)})\n")
