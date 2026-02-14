"""
Three-way comparison: Solis API vs Juggle Inverters vs Juggle PV Meters

For each Solis station, get:
  1. Station-level dayEnergy (from station list record, today's data)
  2. Sum of per-inverter eToday
  3. Try to match to Juggle site by name or inverter count

Then output a consolidated table.
"""
import io, sys, json, time
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from datetime import datetime, timedelta
from solis_api import list_stations, get_station_detail, list_inverters, solis_post

# Get yesterday's date for comparison
yesterday = (datetime.today() - timedelta(days=1)).strftime("%Y-%m-%d")
print(f"Comparison Date: {yesterday}\n")

# 1. Fetch all Solis stations
result = list_stations()
stations = result.get("data", {}).get("page", {}).get("records", [])
print(f"Solis stations found: {len(stations)}\n")

# Build summary
summary = []
for s in stations:
    sid = str(s.get("id"))
    sno = s.get("sno", "?")
    name = s.get("stationName", sno)
    capacity = s.get("capacity", 0)  # MWp
    capacity_kw = s.get("capacity1", capacity * 1000)  # kWp
    day_energy = s.get("dayEnergy1", s.get("dayEnergy", 0))  # kWh (today)
    month_energy = s.get("monthEnergy1", s.get("monthEnergy", 0))  # kWh
    all_energy = s.get("allEnergy1", s.get("allEnergy", 0))  # kWh
    inv_count = s.get("inverterCount", 0)
    inv_online = s.get("inverterOnlineCount", 0)
    city = s.get("cityStr", "?")
    
    # Get inverter-level detail to sum etotal values
    try:
        inv_result = list_inverters(sid)
        inverters = inv_result.get("data", {}).get("page", {}).get("records", [])
        inv_etoday_total = sum(float(inv.get("etoday", 0) or 0) for inv in inverters)
        inv_etotal_total = sum(float(inv.get("etotal", 0) or 0) for inv in inverters) 
        inv_serials = [inv.get("sn", "?") for inv in inverters]
    except Exception as e:
        inv_etoday_total = 0
        inv_etotal_total = 0
        inv_serials = []
    
    summary.append({
        "solis_id": sid,
        "sno": sno,
        "name": name,
        "city": city,
        "capacity_kw": capacity_kw,
        "inv_count": inv_count,
        "inv_online": inv_online,
        "day_energy_station": day_energy,
        "month_energy": month_energy,
        "all_energy": all_energy,
        "inv_etoday_sum": inv_etoday_total,
        "inv_etotal_sum": inv_etotal_total,
        "inv_serials": inv_serials,
    })
    
    time.sleep(0.2)

# Print summary table
print(f"{'Station Name':<30} {'City':<18} {'Cap(kW)':>8} {'Inv':>4} {'On':>3} "
      f"{'Day(kWh)':>10} {'Month(kWh)':>11} {'Total(MWh)':>11}")
print("-" * 120)

for s in summary:
    print(f"{s['name']:<30} {s['city']:<18} {s['capacity_kw']:>8.0f} {s['inv_count']:>4} {s['inv_online']:>3} "
          f"{s['day_energy_station']:>10.1f} {s['month_energy']:>11.1f} {s['all_energy']:>11.0f}")

# Also save as JSON for further use
with open("solis_stations.json", "w") as f:
    json.dump(summary, f, indent=2, default=str)
print(f"\nSaved to solis_stations.json")

# Now print inverter serials for matching
print(f"\n{'='*80}")
print("Inverter Serial Numbers (for matching to Juggle)")
print(f"{'='*80}")
for s in summary:
    print(f"\n{s['name']} ({s['inv_count']} inverters):")
    for sn in s['inv_serials']:
        print(f"  {sn}")
