import sys
import pandas as pd
import numpy as np
from pathlib import Path
import datetime

# Add unified_app to path
current_dir = Path(__file__).parent
sys.path.append(str(current_dir))

from services.toolkit_bridge import toolkit
from services.reporting_bridge import reporting

def debug_alias_resolution():
    print("\n--- Debugging Alias Resolution ---")
    if not toolkit.is_available():
        print("Toolkit bridge not available.")
        return

    test_aliases = ["Blachford UK", "BAE Fylde", "Sofina Haverhill"]
    
    for alias in test_aliases:
        print(f"\nTesting Alias: '{alias}'")
        
        # Method 1: Get Plant directly
        p1 = toolkit.get_plant(alias)
        uid1 = p1.get('uid') if p1 else None
        print(f"  > toolkit.get_plant('{alias}') -> UID: {uid1}")
        
        # Method 2: Search List
        uid2 = None
        all_plants = toolkit.get_plants()
        for p in all_plants:
            if p.get('alias') == alias:
                uid2 = p.get('uid')
                break
        print(f"  > Search list for '{alias}' -> UID: {uid2}")
        
        # Final UID selection logic simulation
        final_uid = uid1 if uid1 else uid2
        print(f"  > RESOLVED UID: {final_uid}")
        
        if final_uid:
            s, e = toolkit.get_date_range(final_uid)
            print(f"    > Data Range: {s} to {e}")
        else:
            print("    > FAILED TO RESOLVE UID")

def debug_loss_calculation():
    print("\n--- Debugging Technical Loss Calculation ---")
    
    # Create dummy data simulating the issue
    data = {
        'Site': ['Site A', 'Site B', 'Site C'],
        'Calculated Exp (kWh)': [1000, 0, None],
        'Actual Gen (kWh)': [900, 500, 500]
    }
    df = pd.DataFrame(data)
    print("Test Data:")
    print(df)
    
    # Apply logic
    def calc_loss(row, exp_col, act_col):
        exp = row.get(exp_col, 0)
        act = row.get(act_col, 0)
        if pd.isna(exp) or exp == 0:
            return 0.0 # Return 0 if no expectation
        return exp - act

    col_name = 'Loss_Total_Tech_kWh'
    df[col_name] = df.apply(lambda x: calc_loss(x, 'Calculated Exp (kWh)', 'Actual Gen (kWh)'), axis=1)
    
    print("\nCalculated Results:")
    print(df)

if __name__ == "__main__":
    debug_loss_calculation()
    debug_alias_resolution()
