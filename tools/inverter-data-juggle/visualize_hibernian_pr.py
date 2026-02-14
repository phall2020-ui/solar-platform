import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import os

# Configuration
CSV_FILE = 'c:/Users/PeterHall/OneDrive - AMPYR IDEA UK Ltd/Python scripts/Inverter data - Juggle/Hibernian_Daily_PR.csv'
OUTPUT_FILE = 'c:/Users/PeterHall/OneDrive - AMPYR IDEA UK Ltd/Python scripts/Inverter data - Juggle/Hibernian_PR_Dec_Jan.png'

def plot_pr_generation(csv_path, output_path):
    print(f"Loading data from {csv_path}...")
    try:
        df = pd.read_csv(csv_path)
    except FileNotFoundError:
        print("Error: CSV file not found.")
        return

    # Convert date to datetime
    df['date'] = pd.to_datetime(df['date'])
    
    # Filter for Dec 2025 and Jan 2026
    start_date = '2025-12-01'
    end_date = '2026-01-31'
    df = df[(df['date'] >= start_date) & (df['date'] <= end_date)]
    
    if df.empty:
        print("No data found for the specified period (Dec 2025 - Jan 2026).")
        return

    sites = df['site_name'].unique()
    
    fig, axes = plt.subplots(len(sites), 1, figsize=(12, 10), sharex=True)
    if len(sites) == 1:
        axes = [axes]
        
    for i, site in enumerate(sites):
        site_data = df[df['site_name'] == site].sort_values('date')
        ax1 = axes[i]
        
        # Generation (Bar chart)
        color = 'tab:blue'
        ax1.set_title(f'{site} - Generation vs PR (Dec 2025 - Jan 2026)', fontsize=14)
        ax1.set_ylabel('Generation (kWh)', color=color, fontsize=12)
        bars = ax1.bar(site_data['date'], site_data['energy_kwh'], color=color, alpha=0.6, label='Generation (kWh)')
        ax1.tick_params(axis='y', labelcolor=color)
        ax1.grid(True, axis='y', alpha=0.3)
        
        # Instantiate a second axes that shares the same x-axis
        ax2 = ax1.twinx()  
        
        # PR (Line chart)
        color = 'tab:red'
        ax2.set_ylabel('Performance Ratio (PR)', color=color, fontsize=12)  # we already handled the x-label with ax1
        line = ax2.plot(site_data['date'], site_data['pr'], color=color, marker='o', linewidth=2, label='PR')
        ax2.tick_params(axis='y', labelcolor=color)
        ax2.set_ylim(0, 1.2) # Set PR limit mostly 0-100% (allows for some over)
        
        # Formatting X axis
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax1.xaxis.set_major_locator(mdates.DayLocator(interval=5))
        plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45)
        
    plt.tight_layout()
    plt.savefig(output_path)
    print(f"Chart saved to {output_path}")

if __name__ == "__main__":
    plot_pr_generation(CSV_FILE, OUTPUT_FILE)
