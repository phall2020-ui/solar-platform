#!/usr/bin/env python3
"""
Export Limit Historical Data Pull.

Fetches historical export limit data for all sites with LIMITATION devices
and stores it in parquet format for analysis.
"""

import os
import sys
from datetime import datetime
from pathlib import Path

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "Solar Toolkit"))

import pandas as pd
from export_limit_crawler import ExportLimitClient


# Configuration
DATA_DIR = Path(__file__).parent.parent / "data" / "export_limits"


def fetch_export_limit_history(
    plant_uid: str,
    start_date: datetime,
    end_date: datetime,
    client: ExportLimitClient = None
) -> pd.DataFrame:
    """Fetch export limit history for a single plant."""
    if client is None:
        client = ExportLimitClient()
    
    print(f"[HistoricPull] Fetching {plant_uid}: {start_date.date()} to {end_date.date()}...")
    df = client.get_export_limit_history(plant_uid, start_date, end_date)
    
    if not df.empty:
        df['plant_uid'] = plant_uid
        print(f"[HistoricPull] Got {len(df)} readings for {plant_uid}")
    else:
        print(f"[HistoricPull] No data for {plant_uid}")
    
    return df


def fetch_all_sites_with_limitation(
    start_date: datetime,
    end_date: datetime,
    save_to_file: bool = True
) -> pd.DataFrame:
    """
    Fetch export limit history for all sites that have LIMITATION devices.
    
    Returns combined DataFrame and optionally saves to parquet.
    """
    client = ExportLimitClient()
    
    # Get all plants
    plants = client.get_plant_list()
    print(f"[HistoricPull] Found {len(plants)} plants total")
    
    all_data = []
    sites_with_limitation = []
    
    for p in plants:
        uid = p.get('uid') or p.get('id') or p.get('plantUID')
        name = p.get('name') or p.get('plantName') or uid
        
        if not uid:
            continue
        
        # Check if this plant has LIMITATION devices
        limitation_devices = client.get_limitation_devices(uid)
        
        if limitation_devices:
            sites_with_limitation.append({
                'uid': uid,
                'name': name,
                'limitation_device': limitation_devices[0].get('emigId')
            })
            
            df = fetch_export_limit_history(uid, start_date, end_date, client)
            if not df.empty:
                df['plant_name'] = name
                all_data.append(df)
    
    print(f"\n[HistoricPull] Found {len(sites_with_limitation)} sites with LIMITATION devices:")
    for site in sites_with_limitation:
        print(f"   - {site['name']} ({site['uid']}): {site['limitation_device']}")
    
    if not all_data:
        print("[HistoricPull] No export limit data found for any site")
        return pd.DataFrame()
    
    combined = pd.concat(all_data, ignore_index=True)
    
    # Ensure proper column order
    cols = ['plant_uid', 'plant_name', 'timestamp', 'export_limit_pct', 'is_curtailed']
    combined = combined[[c for c in cols if c in combined.columns]]
    
    if save_to_file:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        
        # Save as parquet
        filename = f"export_limits_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.parquet"
        filepath = DATA_DIR / filename
        combined.to_parquet(filepath, index=False)
        print(f"\n[HistoricPull] Saved {len(combined)} records to {filepath}")
        
        # Also save as CSV for easy viewing
        csv_path = DATA_DIR / filename.replace('.parquet', '.csv')
        combined.to_csv(csv_path, index=False)
        print(f"[HistoricPull] Also saved to {csv_path}")
    
    return combined


def compute_curtailment_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Compute curtailment statistics per site."""
    if df.empty:
        return pd.DataFrame()
    
    stats = df.groupby(['plant_uid', 'plant_name']).agg({
        'export_limit_pct': ['mean', 'min', 'count'],
        'is_curtailed': ['sum', 'mean']
    }).round(2)
    
    stats.columns = [
        'avg_limit_pct', 'min_limit_pct', 'reading_count',
        'curtailed_readings', 'curtailed_pct'
    ]
    stats['curtailed_pct'] = (stats['curtailed_pct'] * 100).round(2)
    
    return stats.reset_index()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Export Limit Historical Data Pull")
    parser.add_argument("--start", type=str, default="2025-01-01", 
                        help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default=None,
                        help="End date (YYYY-MM-DD), defaults to today")
    parser.add_argument("--no-save", action="store_true",
                        help="Don't save to file, just print stats")
    args = parser.parse_args()
    
    start_date = datetime.strptime(args.start, "%Y-%m-%d")
    end_date = datetime.strptime(args.end, "%Y-%m-%d") if args.end else datetime.now()
    
    print(f"📊 Export Limit Historical Pull")
    print(f"   Period: {start_date.date()} to {end_date.date()}")
    print(f"   Days: {(end_date - start_date).days}")
    print()
    
    combined_df = fetch_all_sites_with_limitation(
        start_date, 
        end_date, 
        save_to_file=not args.no_save
    )
    
    if not combined_df.empty:
        print("\n📈 Curtailment Statistics:")
        stats = compute_curtailment_stats(combined_df)
        print(stats.to_string(index=False))
        
        # Overall summary
        total_readings = len(combined_df)
        total_curtailed = combined_df['is_curtailed'].sum()
        overall_pct = (total_curtailed / total_readings * 100) if total_readings > 0 else 0
        
        print(f"\n📋 Overall Summary:")
        print(f"   Total readings: {total_readings:,}")
        print(f"   Curtailed readings: {total_curtailed:,}")
        print(f"   Overall curtailment rate: {overall_pct:.2f}%")
        
        if combined_df['is_curtailed'].any():
            curtailed_df = combined_df[combined_df['is_curtailed']]
            print(f"\n⚠️  Curtailment Events:")
            print(f"   Average limit during curtailment: {curtailed_df['export_limit_pct'].mean():.1f}%")
            print(f"   Min limit observed: {curtailed_df['export_limit_pct'].min():.1f}%")
