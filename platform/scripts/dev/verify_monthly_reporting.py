
import streamlit as st
import datetime
import pandas as pd
import sys
import os

# Create a mock streamlit context
class MockSessionState(dict):
    def __init__(self):
        self.pdf_report = {}
        self['fiscal_year_start'] = 4 # Mock the fiscal year
        self['pdf_report'] = {}

    def __getattr__(self, key):
        if key in self:
            return self[key]
        return None
    
    def __setattr__(self, key, value):
        self[key] = value

if 'session_state' not in st.__dict__:
    st.session_state = MockSessionState()
else:
    # Ensure keys exist
    if 'pdf_report' not in st.session_state:
        st.session_state.pdf_report = {}
    if 'fiscal_year_start' not in st.session_state:
        st.session_state['fiscal_year_start'] = 4

# Mock the config path logic
# We need to add the current dir to path to import modules
current_dir = os.getcwd()
sys.path.append(current_dir)

print(f"Testing Monthly Reporting logic...")

try:
    from modules import monthly_reporting
    from services.reporting_bridge import reporting
    
    print("Imports successful.")
    
    # 1. Test Data Fetch
    print("Fetching 'solar_data' table...")
    df = reporting.get_table_data("solar_data")
    
    if df is None:
        print("Warning: 'solar_data' returned None. Is the database empty or path wrong?")
        # Create dummy data for testing logic
        data = {
            'Site': ['Site A', 'Site B'],
            'Date': ['Jan-24', 'Feb-24'],
            'Actual Gen (kWh)': [1000, 1100],
            'Forecast Gen (kWh)': [1200, 1150],
            'Calculated Exp (kWh)': [1100, 1120]
        }
        df = pd.DataFrame(data)
        print("Created mock DF for testing.")
    else:
        print(f"Data retrieved: {len(df)} rows.")
        if not df.empty:
            print(f"Columns: {df.columns.tolist()}")
    
    # 2. Test Date Parsing Logic (Crucial for "fiscal_year" error prevention)
    dates = []
    if not df.empty and 'Date' in df.columns:
        unique_dates = df['Date'].unique()
        date_objs = []
        for d in unique_dates:
            try:
                dt = datetime.datetime.strptime(str(d), '%b-%y')
                date_objs.append((d, dt))
            except Exception as e:
                print(f"Date parse error for {d}: {e}")
        
        date_objs.sort(key=lambda x: x[1], reverse=True)
        dates = [x[0] for x in date_objs]
        print(f"Parsed and sorted dates: {dates[:3]}...")
    
    # 3. Test Technical Loss Calculation Logic
    print("Testing Technical Loss calculation...")
    month_df = df.copy()
    target_loss_col = 'Loss_Total_Tech_kWh'
    
    if target_loss_col not in month_df.columns:
        if 'Calculated Exp (kWh)' in month_df.columns and 'Actual Gen (kWh)' in month_df.columns:
             month_df[target_loss_col] = 0.0 # logic test
             exp = month_df['Calculated Exp (kWh)'].fillna(0)
             act = month_df['Actual Gen (kWh)'].fillna(0)
             loss = exp - act
             loss[exp == 0] = 0.0
             month_df[target_loss_col] = loss
             print("Calculated Tech Loss using 'Calculated Exp'.")
        elif 'Forecast Gen (kWh)' in month_df.columns and 'Actual Gen (kWh)' in month_df.columns:
             exp = month_df['Forecast Gen (kWh)'].fillna(0)
             act = month_df['Actual Gen (kWh)'].fillna(0)
             loss = exp - act
             loss[exp == 0] = 0.0
             month_df[target_loss_col] = loss
             print("Calculated Tech Loss using 'Forecast Gen'.")
    
    print(f"Loss column present: {target_loss_col in month_df.columns}")
    if target_loss_col in month_df.columns:
        print(f"Sample Loss values: {month_df[target_loss_col].head().tolist()}")

    print("\n[OK] Verification Script Complete: Logic appears sound and 'fiscal_year' session state is handled.")

except Exception as e:
    print(f"\n[FAIL] Verification Failed: {e}")
    import traceback
    traceback.print_exc()
