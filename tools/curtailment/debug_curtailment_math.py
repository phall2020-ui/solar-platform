import csv
import os

def check():
    path = os.path.expanduser("~/Documents/export_limitation_with_losses.csv")
    
    newfold_events = []
    mancity_events = []
    
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row['export_limit_pct']:
                continue
                
            try:
                limit = float(row['export_limit_pct'])
                if limit < 100.0:
                    if row['site_name'] == 'Newfold Farm':
                        newfold_events.append(row)
                    elif row['site_name'] == 'Man City FC Training Ground':
                        mancity_events.append(row)
            except ValueError:
                pass
                
    print("NEWFOLD FARM CURTAILMENT EVENTS:")
    if newfold_events:
        for row in newfold_events:
            print(f"Time: {row['timestamp']}")
            print(f"  Export Limit: {row['export_limit_pct']}%")
            print(f"  DC Capacity: {row['dc_capacity_kw']} kW")
            print(f"  Actual Power: {row['actual_power_kw']} kW")
            print(f"  Proxy Irradiance: {row['irradiance_wm2']} W/m2")
            print(f"  Theoretical Power: {row['theoretical_capacity_kw']} kW")
            print(f"  Calculated Loss: {row['estimated_curtailment_loss_kwh']} kWh")
    else:
        print("None found")
        
    print("\nMAN CITY FC CURTAILMENT EVENTS (First 5):")
    if mancity_events:
        for row in mancity_events[:5]:
            print(f"Time: {row['timestamp']}")
            print(f"  Export Limit: {row['export_limit_pct']}%")
            print(f"  DC Capacity: {row['dc_capacity_kw']} kW")
            print(f"  Actual Power: {row['actual_power_kw']} kW")
            print(f"  Proxy Irradiance: {row['irradiance_wm2']} W/m2")
            print(f"  Theoretical Power: {row['theoretical_capacity_kw']} kW")
            print(f"  Calculated Loss: {row['estimated_curtailment_loss_kwh']} kWh")
            
        total_loss = sum(float(r['estimated_curtailment_loss_kwh']) for r in mancity_events if r['estimated_curtailment_loss_kwh'])
        print(f"\nTotal Man City Events: {len(mancity_events)}")
        print(f"Total Man City Loss: {total_loss} kWh")
    else:
        print("None found")

if __name__ == "__main__":
    check()
