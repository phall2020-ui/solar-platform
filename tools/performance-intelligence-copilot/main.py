import asyncio
import argparse
import json
import os
import sys
import pandas as pd
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add src to python path for solar_platform package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'src')))

from solar_platform.services.performance_copilot_asset_audit import (
    AssetRegisterAuditService,
    run_asset_register_daily_publish,
    run_asset_register_yesterday_audit,
    run_asset_register_triage_publish,
)

# Configuration
NEWFOLD_FARM_UID = "ERS:00001" # Correct UID from EMIG data
INSTALLED_DC_KWP = 459.0 # Approximate from previous data
PR_BASELINE = 0.85
INTERVAL_HOURS = 0.25 # 15 mins
DEFAULT_PPA_RATE_GBP_MWH = 100.0

async def fetch_emig_data() -> pd.DataFrame:
    """Fetch the last 24 hours of data from EMIG for Newfold Farm."""
    from solar_platform.ingestion.emig_adapter import EMIGAdapter

    api_key = os.getenv("JUGGLE_API_KEY") # reusing token variable
    if not api_key:
        raise ValueError("JUGGLE_API_KEY environment variable is required")

    adapter = EMIGAdapter(api_key=api_key)
    
    # Authenticate
    if not await adapter.authenticate():
        raise RuntimeError("Failed to authenticate with EMIG API")

    # Time range: yesterday to now (approx 24h)
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=1)
    
    print(f"Fetching data for Newfold Farm ({NEWFOLD_FARM_UID}) from {start_time} to {end_time}")
    
    batch = await adapter.fetch_readings(
        plant_uid=NEWFOLD_FARM_UID,
        start=start_time,
        end=end_time
    )
    
    print(f"Fetched {len(batch.readings)} readings. Errors: {len(batch.errors)}, Warnings: {len(batch.warnings)}")
    if batch.errors:
        print(f"Errors: {batch.errors}")
    if batch.warnings:
        print(f"Warnings: {batch.warnings}")

    if not batch.readings:
        return pd.DataFrame()

    # Convert to pandas DataFrame
    data = []
    for r in batch.readings:
        power = getattr(r, "power_kw", 0.0) or 0.0
        poa = getattr(r, "poa_wm2", 0.0) or 0.0
        
        # Pull energy accumulator to backfill missing Power data
        energy_kwh = getattr(r, "energy_kwh", None)
        energy_wh = None
        if energy_kwh is None:
            # Maybe the raw payload has it directly
            raw = getattr(r, "raw_payload", {})
            export_energy = raw.get("exportEnergy")
            if export_energy and isinstance(export_energy, dict):
                val = export_energy.get("value")
                if val is not None:
                    try:
                        energy_wh = float(val)
                    except ValueError:
                        pass
        
        data.append({
            "timestamp": r.timestamp,
            "device_id": r.device_id,
            "poa_wm2": poa,
            "power_kw": power,
            "energy_wh": energy_wh,
            # Mocking controller_active; Juggle might not provide this directly without mapping
            "controller_active": True if power >= 300.0 else False,
        })
        
    df = pd.DataFrame(data)
    if df.empty:
        return df

    # Ensure timestamp is datetime type
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # 2. Time Series Reconstruction (Gap Filling)
    # The Juggle API often drops 15-minute intervals, but the energy accumulator continues
    # We reconstruct the full series to ensure 100% availability metrics where evidence exists.
    
    # Define the reference timeline for the entire site
    # Use 15-minute floor/ceil to align exactly with SCADA intervals
    full_range = pd.date_range(
        start=df['timestamp'].min().floor('15min'),
        end=df['timestamp'].max().ceil('15min'),
        freq='15min'
    )
    
    reconstructed_frames = []
    for dev_id, group in df.groupby("device_id"):
        # Set timestamp as index for reindexing
        group = group.sort_values("timestamp").set_index("timestamp")
        
        # Remove duplicates if any (Juggle sometimes returns overlapping chunks)
        group = group[~group.index.duplicated(keep='first')]
        
        # Reindex to the full range
        # Note: We only reindex between the device's own min/max to avoid "hallucinating" 
        # data before the inverter woke up or after it went to sleep for the session.
        dev_range = pd.date_range(start=group.index.min(), end=group.index.max(), freq='15min')
        group_full = group.reindex(dev_range)
        
        # Fill device_id
        group_full['device_id'] = dev_id
        
        # Interpolate energy accumulator (Wh)
        if 'energy_wh' in group_full.columns:
            group_full['energy_wh'] = group_full['energy_wh'].interpolate(method='linear')
            
            # Calculate power from energy delta
            # Wh delta * 4 (intervals per hour) / 1000 = kW
            # Or simpler: Wh / 250
            group_full['power_kw'] = group_full['energy_wh'].diff() / 250.0
            
            # Handle edge case: if we have power_kw readings from API, prefer those
            # But the user noted missing intervals, so derived is safer for the gaps.
            # We enforce a floor of 0.
            group_full['power_kw'] = group_full['power_kw'].fillna(0.0).clip(lower=0.0)
            
            # Cap realistic power (max 500kW for Newfold inverters)
            group_full.loc[group_full['power_kw'] > 500.0, 'power_kw'] = 0.0

        # Forward fill POA so it's available for during the gap period
        if 'poa_wm2' in group_full.columns:
            group_full['poa_wm2'] = group_full['poa_wm2'].ffill().bfill()
            
        group_full['controller_active'] = group_full['power_kw'] >= 2.0 # simplified
        
        reconstructed_frames.append(group_full.reset_index().rename(columns={'index': 'timestamp'}))

    if reconstructed_frames:
        df = pd.concat(reconstructed_frames, ignore_index=True)
    
    return df.sort_values("timestamp")

def generate_ai_diagnosis(evidence_pack: dict) -> str:
    """Send evidence pack to OpenAI LLM for diagnosis."""
    from openai import OpenAI

    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        raise ValueError("OPENAI_API_KEY environment variable is required")
        
    client = OpenAI(
        api_key=openai_api_key,
    )
    
    prompt = f"""
You are an expert Solar Asset Management AI. Analyze the following operational evidence for a solar site and provide a concise diagnosis and recommended actions for the Operations & Maintenance (O&M) team.

Evidence Data:
{evidence_pack}

Please structure your response with:
1. Summary of the event
2. Likely Root Cause
3. Recommended O&M Action
4. Urgency
"""
    
    print("Calling OpenAI LLM...")
    response = client.chat.completions.create(
        model="gpt-5.4-2026-03-05", # Exact model requested by user
        messages=[{"role": "user", "content": prompt}],
    )
    
    return response.choices[0].message.content

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Performance intelligence copilot."
    )
    parser.add_argument(
        "--mode",
        choices=(
            "asset-register-yesterday",
            "asset-register-backfill",
            "asset-register-publish-triage",
            "asset-register-publish-daily",
            "single-site",
        ),
        default="asset-register-yesterday",
        help="Run the asset-register audit, the Data Source Match backfill, publish triage or daily output, or the legacy single-site copilot.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(Path(__file__).resolve().parent / "output"),
        help="Directory for generated dataset files in asset-register mode.",
    )
    parser.add_argument(
        "--reference-date",
        help="Reference date in YYYY-MM-DD format. Yesterday is derived from this date.",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Force-refresh the Notion asset register before building the dataset.",
    )
    parser.add_argument(
        "--asset-filter",
        help="Optional case-insensitive asset-name filter for asset-register audit mode.",
    )
    parser.add_argument(
        "--include-healthy",
        action="store_true",
        help="Include healthy records when publishing triage output.",
    )
    parser.add_argument(
        "--daily-json-database-id",
        default=os.getenv("NOTION_DAILY_JSON_DATABASE_ID", ""),
        help="Optional Notion database ID for daily output publishing.",
    )
    parser.add_argument(
        "--daily-json-parent-page-id",
        default=os.getenv("NOTION_DAILY_JSON_PARENT_PAGE_ID", ""),
        help="Optional Notion page ID used to create the Daily JSON database if it does not exist.",
    )
    return parser.parse_args()


def _parse_reference_date(value: str | None):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


async def run_single_site_copilot():
    try:
        from solar_platform.analytics.performance_intelligence.copilot_pipeline import analyze_telemetry_dataframe
        from solar_platform.analytics.performance_intelligence.diagnosis import build_evidence_pack

        # 1. Fetch Data
        df = await fetch_emig_data()
        
        if df.empty:
            print("No data fetched. Exiting.")
            return

        print(f"\nData sample:\n{df.head()}")

        # 1.5 Calculate Availability
        availability_metrics = {}
        if "device_id" in df.columns and not df.empty:
            counts = df["device_id"].value_counts()
            
            # The cleanest way to find true "100%" availability in Juggle is to find the maximum 
            # number of reading intervals any single device achieved that day. 
            # This implicitly accounts for when the inverters wake up / go to sleep due to low irradiance.
            # We enforce a realistic upper bound of 96 intervals.
            max_intervals_today = min(96, counts.max())
            
            print(f"\nSunlight/Active Hours Detected: Maximum active intervals for the best inverter was {max_intervals_today}")
            
            all_inverters = df["device_id"].unique()
            for dev in all_inverters:
                c = counts.get(dev, 0)
                availability_metrics[dev] = round(min(1.0, c / float(max_intervals_today)), 3)

        print(f"Calculated Performance Availability Metrics for {len(availability_metrics)} devices.")

        # 2. Analyze Telemetry
        print("\nAnalyzing Telemetry for Curtailment/Losses...")
        ppa_rate_gbp_mwh = float(os.getenv("PPA_RATE_GBP_MWH", str(DEFAULT_PPA_RATE_GBP_MWH)))
        analyzed_df, events = analyze_telemetry_dataframe(
            df=df,
            installed_dc_kwp=INSTALLED_DC_KWP,
            pr_baseline=PR_BASELINE,
            interval_hours=INTERVAL_HOURS,
            ppa_rate_gbp_mwh=ppa_rate_gbp_mwh,
        )
        
        print(f"Total Curtailment Events Detected: {len(events)}")
        
        if events:
            # Aggregate all energy lost
            total_lost_energy = sum(
                float(e.get("estimated_generation_loss_kwh", e.get("lost_energy_kwh", 0.0)) or 0.0)
                for e in events
            )
            total_revenue_loss = sum(
                float(e.get("estimated_revenue_loss_gbp", 0.0) or 0.0)
                for e in events
            )
            event_type = "aggregated_export_limit_curtailment"
        else:
            total_lost_energy = 0.0
            total_revenue_loss = 0.0
            event_type = "normal_operation_no_curtailment"

        # 3. Build Real Evidence
        evidence = build_evidence_pack(
            site_name="Newfold Farm",
            event_type=event_type,
            lost_energy_kwh=total_lost_energy,
            revenue_loss_gbp=total_revenue_loss,
            availability_metrics=availability_metrics
        )
        
        print(f"\nRAW EVIDENCE DATA PAYLOAD BUILT FOR LLM:\n")
        print("-" * 50)
        import json
        print(json.dumps(evidence, indent=2))
        print("-" * 50)
        
        # Ask AI with Real payload
        diagnosis = generate_ai_diagnosis(evidence)
        print(f"\n{'='*40}\nAI Diagnosis Report\n{'='*40}\n")
        print(diagnosis)

    except Exception as e:
        print(f"Error during execution: {e}")


async def run_asset_register_audit(args: argparse.Namespace):
    result = await run_asset_register_yesterday_audit(
        output_dir=Path(args.output_dir),
        reference_date=_parse_reference_date(args.reference_date),
        force_refresh=args.force_refresh,
        asset_filter=args.asset_filter,
    )

    print(f"Asset-register yesterday audit complete for {result['target_date']}")
    print(f"Rows written: {result['rows']}")
    print(f"CSV: {result['paths']['csv']}")
    print(f"JSON: {result['paths']['json']}")

    dataset = result["dataset"]
    if not dataset:
        print(
            "No asset rows were returned. "
            "This usually means Notion access is not configured or the asset register query failed."
        )
        return

    assets_with_data = sum(1 for row in dataset if row.get("has_any_data"))
    post_pac_assets = sum(1 for row in dataset if row.get("pac_phase") == "post_pac")
    pre_pac_assets = sum(1 for row in dataset if row.get("pac_phase") == "pre_pac")
    unknown_pac_assets = sum(1 for row in dataset if row.get("pac_phase") == "unknown")
    print(f"Assets with data in at least one source: {assets_with_data}")
    print(f"PAC split: post_pac={post_pac_assets} pre_pac={pre_pac_assets} unknown={unknown_pac_assets}")


def run_asset_register_backfill(args: argparse.Namespace):
    service = AssetRegisterAuditService()
    result = service.backfill_confirmed_data_source_matches(force_refresh=args.force_refresh)
    print(json.dumps(result, indent=2))


async def run_asset_register_triage(args: argparse.Namespace):
    result = await run_asset_register_triage_publish(
        output_dir=Path(args.output_dir),
        reference_date=_parse_reference_date(args.reference_date),
        force_refresh=args.force_refresh,
        asset_filter=args.asset_filter,
        include_healthy=args.include_healthy,
    )

    print(f"Asset-register triage publish complete for {result['target_date']}")
    print(f"Triage rows written: {result['rows']}")
    print(f"Triage JSON: {result['triage_json']}")
    publish_result = result["publish_result"]
    print(f"Notion database: {publish_result['database_id']}")
    print(f"Published rows: {publish_result['published']}")
    print(f"Failed rows: {publish_result['failed']}")


async def run_asset_register_daily_publish_cmd(args: argparse.Namespace):
    result = await run_asset_register_daily_publish(
        output_dir=Path(args.output_dir),
        reference_date=_parse_reference_date(args.reference_date),
        force_refresh=args.force_refresh,
        asset_filter=args.asset_filter,
        database_id=args.daily_json_database_id or None,
        parent_page_id=args.daily_json_parent_page_id or None,
    )

    print(f"Asset-register daily publish complete for {result['target_date']}")
    print(f"Daily rows written: {result['rows']}")
    print(f"Daily JSON: {result['daily_json']}")
    publish_result = result["publish_result"]
    print(f"Notion database: {publish_result['database_id']}")
    print(f"Rows eligible for Notion publish: {publish_result.get('eligible_rows', result['rows'])}")
    print(f"Published rows: {publish_result['published']}")
    print(f"Failed rows: {publish_result['failed']}")


async def main():
    args = parse_args()
    if args.mode == "single-site":
        await run_single_site_copilot()
        return
    if args.mode == "asset-register-backfill":
        run_asset_register_backfill(args)
        return
    if args.mode == "asset-register-publish-triage":
        await run_asset_register_triage(args)
        return
    if args.mode == "asset-register-publish-daily":
        await run_asset_register_daily_publish_cmd(args)
        return
    await run_asset_register_audit(args)


if __name__ == "__main__":
    asyncio.run(main())
