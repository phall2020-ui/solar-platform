import sqlite3
import pandas as pd
import numpy as np
import os

# Configuration
DB_PATH = 'c:/Users/PeterHall/OneDrive - AMPYR IDEA UK Ltd/Python scripts/Inverter data - Juggle/plant_registry.sqlite'
GHI_DIR = 'c:/Users/PeterHall/OneDrive - AMPYR IDEA UK Ltd/Python scripts/Irradiation Data'

SITES = [
    {
        'name': 'Hibernian Stadium',
        'uid': 'AMP:00002',
        'dc_kw': 117.0,
        'ghi_files': [
            '2025 11/Hibernian_Stadium.csv',
            '2025 12/Hibernian_Stadium.csv',
            '2026 01/Hibernian_Stadium.csv'
        ]
    },
    {
        'name': 'Hibernian Training Ground',
        'uid': 'AMP:00003',
        'dc_kw': 90.0,
        'ghi_files': [
            '2025 11/Hibernian_Training_Ground.csv',
            '2025 12/Hibernian_Training_Ground.csv',
            '2026 01/Hibernian_Training_Ground.csv'
        ]
    }
]

def get_generation_data(conn, uid):
    """Fetch generation data (active power) from DB"""
    print(f"Fetching generation data for {uid}...")
    query = """
        SELECT ts, 
               json_extract(payload, '$.activePower.value') as power_w
        FROM readings 
        WHERE plant_uid = ? 
          AND emig_id LIKE 'INVERT:%'
          AND json_extract(payload, '$.activePower.value') IS NOT NULL
    """
    df = pd.read_sql_query(query, conn, params=(uid,))
    if df.empty:
        # Try apparent power if active power is missing
        print("  Active power missing, trying apparent power...")
        query = """
            SELECT ts, 
                   json_extract(payload, '$.apparentPower.value') as power_w
            FROM readings 
            WHERE plant_uid = ? 
              AND emig_id LIKE 'INVERT:%'
              AND json_extract(payload, '$.apparentPower.value') IS NOT NULL
        """
        df = pd.read_sql_query(query, conn, params=(uid,))
        
    if df.empty:
        return pd.DataFrame()

    df['ts'] = pd.to_datetime(df['ts'])
    # Convert UTC to simple datetime (assuming GHI is local/aligned)
    if df['ts'].dt.tz is not None:
        df['ts'] = df['ts'].dt.tz_localize(None)
        
    df['power_kw'] = pd.to_numeric(df['power_w']) / 1000.0
    
    # Resample to hourly/daily sum
    # Note: If data is instantaneous power (kW), Energy (kWh) = Power * Time
    # Assuming 30min or 15min intervals, we'll resample to hourly mean then sum?
    # Better: Resample to 15min mean, then sum / 4 to get kWh?
    # Let's check frequency.
    
    df = df.set_index('ts').sort_index()
    
    # Group by timestamp first to sum across multiple inverters
    df_site = df.groupby(level=0)['power_kw'].sum().to_frame()
    
    return df_site

def load_ghi_data(filepath):
    """Load GHI data from CSV"""
    print(f"Loading GHI data from {filepath}...")
    if not os.path.exists(filepath):
        print(f"  File not found: {filepath}")
        return pd.DataFrame()
        
    df = pd.read_csv(filepath)
    # Parse time
    # Format appears to be: 2025-11-01 00:00:30+00:00
    df['time'] = pd.to_datetime(df['time'])
    if df['time'].dt.tz is not None:
        df['time'] = df['time'].dt.tz_localize(None)
        
    df = df.set_index('time').sort_index()
    # Rename ghi column
    df = df[['ghi']].rename(columns={'ghi': 'ghi_w_m2'})
    return df

def calculate_daily_pr(gen_df, ghi_df, dc_kw):
    """Calculate daily PR"""
    # Merge on nearest timestamp
    # Resample both to 15min to align
    
    gen_15min = gen_df.resample('15min').mean() # avg kW over 15 min
    ghi_15min = ghi_df.resample('15min').mean() # avg W/m2 over 15 min
    
    merged = pd.merge(gen_15min, ghi_15min, left_index=True, right_index=True, how='inner')
    
    # Calculate Energy
    # Energy produced (kWh) = Power (kW) * 0.25h
    merged['energy_kwh'] = merged['power_kw'] * 0.25
    
    # Expected Energy
    # Expected (kWh) = DC (kW) * Insolation (kWh/m2)
    # Since ghi_w_m2 is per interval (kWh/m2), we just mult by DC.
    merged['expected_kwh'] = dc_kw * merged['ghi_w_m2']
    
    # Daily aggregation
    merged['date'] = merged.index.date
    
    daily = merged.groupby('date').agg({
        'energy_kwh': 'sum',
        'expected_kwh': 'sum',
        'ghi_w_m2': 'sum' # This is sum of kWh/m2 intervals.
    }).reset_index()
    
    # Daily Irradiation (kWh/m2)
    # Since input is likely kWh/m2 per interval, just sum it.
    daily['daily_irradiation_kwh_m2'] = daily['ghi_w_m2']
    
    daily['pr'] = daily['energy_kwh'] / daily['expected_kwh']
    
    # Handle low/zero expected energy
    daily.loc[daily['expected_kwh'] < 1.0, 'pr'] = np.nan
    
    daily['dc_capacity_kw'] = dc_kw
    
    return daily

def main():
    conn = sqlite3.connect(DB_PATH)
    
    all_results = []
    
    for site in SITES:
        print(f"\nProcessing {site['name']}...")
        
        # Generator Data
        gen_df = get_generation_data(conn, site['uid'])
        if gen_df.empty:
            print("  No generation data found.")
            continue
        print(f"  Gen Data: {len(gen_df)} rows, {gen_df.index.min()} to {gen_df.index.max()}")
            
        # GHI Data - Load multiple months
        ghi_dfs = []
        for ghi_file in site['ghi_files']:
            ghi_path = os.path.join(GHI_DIR, ghi_file)
            df_part = load_ghi_data(ghi_path)
            if not df_part.empty:
                ghi_dfs.append(df_part)
        
        if not ghi_dfs:
            print("  No GHI data found.")
            continue
            
        ghi_df = pd.concat(ghi_dfs).sort_index()
        print(f"  GHI Data (Total): {len(ghi_df)} rows, {ghi_df.index.min()} to {ghi_df.index.max()}")
            
        # Calc PR
        # DEBUG: Check alignment
        gen_15min = gen_df.resample('15min').mean()
        ghi_15min = ghi_df.resample('15min').mean()
        print(f"  Gen 15min Sample: {gen_15min.index[0]}")
        print(f"  GHI 15min Sample: {ghi_15min.index[0]}")
        
        daily_df = calculate_daily_pr(gen_df, ghi_df, site['dc_kw'])
        daily_df['site_name'] = site['name']
        
        all_results.append(daily_df)
        
    conn.close()
    
    if all_results:
        final_df = pd.concat(all_results)
        output_file = 'c:/Users/PeterHall/OneDrive - AMPYR IDEA UK Ltd/Python scripts/Inverter data - Juggle/Hibernian_Daily_PR.csv'
        final_df.to_csv(output_file, index=False)
        print(f"\nSaved results to {output_file}")
        print(final_df[['site_name', 'date', 'daily_irradiation_kwh_m2', 'energy_kwh', 'pr']].to_string())
    else:
        print("\nNo results calculated.")

if __name__ == "__main__":
    main()
