from services.reporting_bridge import reporting
print(f"Reporting Available: {reporting.is_available()}")
if reporting.is_available():
    df = reporting.get_table_data("solar_data")
    if df is not None:
        print(f"Got DataFrame: {len(df)} rows")
        print("Columns:", df.columns.tolist())
        print("Dates:", df['Date'].unique().tolist())
    else:
        print("DataFrame is None")
else:
    print("Reporting Bridge not available")
    # inspect why
    import sys
    from unified_config import config
    print(f"Sys Path includes reporting path? {str(config.MONTHLY_REPORTING_PATH) in sys.path}")
    
    try:
        from data_access import SolarDataExtractor
        print("Imported SolarDataExtractor successfully manually")
    except ImportError as e:
        print(f"Failed to import SolarDataExtractor: {e}")
