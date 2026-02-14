import sqlite3
import pandas as pd

try:
    conn = sqlite3.connect('c:/Users/PeterHall/OneDrive - AMPYR IDEA UK Ltd/Python scripts/Inverter data - Juggle/plant_registry.sqlite')
    
    print("Searching for plants > 1000 kW...")
    query = """
    SELECT alias, plant_uid, dc_size_kw, inverter_ids
    FROM plants 
    WHERE dc_size_kw > 1000
    ORDER BY dc_size_kw DESC
    """
    df = pd.read_sql_query(query, conn)
    print(df)
    
    print("\nChecking Hibernian specific details again...")
    query_hib = """
    SELECT alias, plant_uid, dc_size_kw, inverter_ids
    FROM plants 
    WHERE alias LIKE '%Hibernian%'
    """
    df_hib = pd.read_sql_query(query_hib, conn)
    print(df_hib)
    
    conn.close()

except Exception as e:
    print(f"Error: {e}")
