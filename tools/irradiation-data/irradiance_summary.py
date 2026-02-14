"""
Interactive script to summarize irradiance data at hourly, daily, or monthly intervals.
Users can select one or multiple sites from the available data.
"""
import pandas as pd
import os
from pathlib import Path
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')


class IrradianceSummarizer:
    """Class to handle irradiance data summarization with flexible options"""

    def __init__(self, base_dir):
        self.base_dir = Path(base_dir)
        self.available_sites = self._discover_sites()

    def _discover_sites(self):
        """Discover all available sites from monthly folders"""
        sites = set()
        exclude_patterns = ['pvgis', 'compare', 'test', 'summary']

        monthly_folders = [f for f in self.base_dir.iterdir()
                          if f.is_dir() and f.name.startswith("202")]

        for folder in monthly_folders:
            csv_files = list(folder.glob("*.csv"))
            for csv_file in csv_files:
                site_name = csv_file.stem
                if not any(pattern in site_name.lower() for pattern in exclude_patterns):
                    sites.add(site_name)

        return sorted(list(sites))

    def _load_site_data(self, site_names):
        """Load data for specified sites from all available monthly folders"""
        all_data = []

        monthly_folders = [f for f in self.base_dir.iterdir()
                          if f.is_dir() and f.name.startswith("202")]

        for folder in sorted(monthly_folders):
            for site_name in site_names:
                csv_file = folder / f"{site_name}.csv"
                if csv_file.exists():
                    try:
                        df = pd.read_csv(csv_file)
                        all_data.append(df)
                    except Exception as e:
                        print(f"Warning: Error reading {csv_file}: {e}")

        if not all_data:
            return None

        # Combine all data
        combined_df = pd.concat(all_data, ignore_index=True)

        # Convert time column to datetime
        combined_df['time'] = pd.to_datetime(combined_df['time'])

        # Sort by time
        combined_df = combined_df.sort_values('time').reset_index(drop=True)

        return combined_df

    def summarize_hourly(self, df):
        """Summarize data to hourly intervals, combining arrays by capacity-weighted average"""
        df = df.copy()
        df['hour'] = df['time'].dt.floor('H')

        # First, average readings within each hour for each array
        hourly_per_array = df.groupby(['name', 'azimuth', 'slope', 'array_capacity', 'hour']).agg({
            'gti': 'mean',
            'gti_low': 'mean',
            'gti_high': 'mean',
            'ghi': 'mean'
        }).reset_index()

        # Calculate capacity-weighted irradiance for each site and hour
        hourly_per_array['gti_weighted'] = hourly_per_array['gti'] * hourly_per_array['array_capacity']
        hourly_per_array['gti_low_weighted'] = hourly_per_array['gti_low'] * hourly_per_array['array_capacity']
        hourly_per_array['gti_high_weighted'] = hourly_per_array['gti_high'] * hourly_per_array['array_capacity']
        hourly_per_array['ghi_weighted'] = hourly_per_array['ghi'] * hourly_per_array['array_capacity']

        # Group by site and hour, combining arrays
        summary = hourly_per_array.groupby(['name', 'hour']).agg({
            'array_capacity': 'sum',
            'gti_weighted': 'sum',
            'gti_low_weighted': 'sum',
            'gti_high_weighted': 'sum',
            'ghi_weighted': 'sum'
        }).reset_index()

        # Calculate weighted average irradiance
        summary['gti'] = summary['gti_weighted'] / summary['array_capacity']
        summary['gti_low'] = summary['gti_low_weighted'] / summary['array_capacity']
        summary['gti_high'] = summary['gti_high_weighted'] / summary['array_capacity']
        summary['ghi'] = summary['ghi_weighted'] / summary['array_capacity']

        # Clean up temporary columns
        summary = summary[['name', 'hour', 'array_capacity', 'gti', 'gti_low', 'gti_high', 'ghi']]
        summary.rename(columns={'hour': 'time', 'array_capacity': 'total_capacity_kwp'}, inplace=True)

        return summary

    def summarize_daily(self, df):
        """Summarize data to daily intervals, combining arrays by capacity-weighted average"""
        df = df.copy()
        df['date'] = df['time'].dt.date

        # First, sum readings within each day for each array
        daily_per_array = df.groupby(['name', 'azimuth', 'slope', 'array_capacity', 'date']).agg({
            'gti': 'sum',
            'gti_low': 'sum',
            'gti_high': 'sum',
            'ghi': 'sum'
        }).reset_index()

        # Calculate capacity-weighted irradiance for each site and day
        daily_per_array['gti_weighted'] = daily_per_array['gti'] * daily_per_array['array_capacity']
        daily_per_array['gti_low_weighted'] = daily_per_array['gti_low'] * daily_per_array['array_capacity']
        daily_per_array['gti_high_weighted'] = daily_per_array['gti_high'] * daily_per_array['array_capacity']
        daily_per_array['ghi_weighted'] = daily_per_array['ghi'] * daily_per_array['array_capacity']

        # Group by site and date, combining arrays
        summary = daily_per_array.groupby(['name', 'date']).agg({
            'array_capacity': 'sum',
            'gti_weighted': 'sum',
            'gti_low_weighted': 'sum',
            'gti_high_weighted': 'sum',
            'ghi_weighted': 'sum'
        }).reset_index()

        # Calculate weighted average irradiance
        summary['gti'] = summary['gti_weighted'] / summary['array_capacity']
        summary['gti_low'] = summary['gti_low_weighted'] / summary['array_capacity']
        summary['gti_high'] = summary['gti_high_weighted'] / summary['array_capacity']
        summary['ghi'] = summary['ghi_weighted'] / summary['array_capacity']

        # Clean up temporary columns
        summary = summary[['name', 'date', 'array_capacity', 'gti', 'gti_low', 'gti_high', 'ghi']]
        summary.rename(columns={'date': 'time', 'array_capacity': 'total_capacity_kwp'}, inplace=True)

        return summary

    def summarize_monthly(self, df):
        """Summarize data to monthly intervals, combining arrays by capacity-weighted average"""
        df = df.copy()
        df['month'] = df['time'].dt.to_period('M')

        # First, sum readings within each month for each array
        monthly_per_array = df.groupby(['name', 'azimuth', 'slope', 'array_capacity', 'month']).agg({
            'gti': 'sum',
            'gti_low': 'sum',
            'gti_high': 'sum',
            'ghi': 'sum'
        }).reset_index()

        # Calculate capacity-weighted irradiance for each site and month
        monthly_per_array['gti_weighted'] = monthly_per_array['gti'] * monthly_per_array['array_capacity']
        monthly_per_array['gti_low_weighted'] = monthly_per_array['gti_low'] * monthly_per_array['array_capacity']
        monthly_per_array['gti_high_weighted'] = monthly_per_array['gti_high'] * monthly_per_array['array_capacity']
        monthly_per_array['ghi_weighted'] = monthly_per_array['ghi'] * monthly_per_array['array_capacity']

        # Group by site and month, combining arrays
        summary = monthly_per_array.groupby(['name', 'month']).agg({
            'array_capacity': 'sum',
            'gti_weighted': 'sum',
            'gti_low_weighted': 'sum',
            'gti_high_weighted': 'sum',
            'ghi_weighted': 'sum'
        }).reset_index()

        # Calculate weighted average irradiance
        summary['gti'] = summary['gti_weighted'] / summary['array_capacity']
        summary['gti_low'] = summary['gti_low_weighted'] / summary['array_capacity']
        summary['gti_high'] = summary['gti_high_weighted'] / summary['array_capacity']
        summary['ghi'] = summary['ghi_weighted'] / summary['array_capacity']

        # Convert period back to timestamp for consistency
        summary['time'] = summary['month'].dt.to_timestamp()
        summary = summary[['name', 'time', 'array_capacity', 'gti', 'gti_low', 'gti_high', 'ghi']]
        summary.rename(columns={'array_capacity': 'total_capacity_kwp'}, inplace=True)

        return summary

    def calculate_weighted_total(self, df):
        """Calculate weighted total irradiance by array capacity"""
        df = df.copy()

        # Calculate energy (kWh) = irradiance (kW/m²) * capacity (kWp)
        # Note: This assumes performance ratio = 1.0 for simplification
        df['gti_energy_kwh'] = df['gti'] * df['total_capacity_kwp']
        df['gti_low_energy_kwh'] = df['gti_low'] * df['total_capacity_kwp']
        df['gti_high_energy_kwh'] = df['gti_high'] * df['total_capacity_kwp']
        df['ghi_energy_kwh'] = df['ghi'] * df['total_capacity_kwp']

        return df

    def summarize(self, site_names, interval='daily', weighted=False, output_file=None):
        """
        Main summarization method

        Parameters:
        -----------
        site_names : list
            List of site names to include
        interval : str
            'hourly', 'daily', or 'monthly'
        weighted : bool
            If True, calculate weighted totals by array capacity
        output_file : str, optional
            Output CSV file path. If None, auto-generate filename

        Returns:
        --------
        pd.DataFrame : Summarized data
        """
        print(f"\nLoading data for {len(site_names)} site(s)...")
        df = self._load_site_data(site_names)

        if df is None or len(df) == 0:
            print("Error: No data found for the selected sites.")
            return None

        print(f"Loaded {len(df):,} records")
        print(f"Date range: {df['time'].min()} to {df['time'].max()}")

        # Apply summarization
        if interval == 'hourly':
            print("\nSummarizing to hourly intervals...")
            summary = self.summarize_hourly(df)
        elif interval == 'daily':
            print("\nSummarizing to daily intervals...")
            summary = self.summarize_daily(df)
        elif interval == 'monthly':
            print("\nSummarizing to monthly intervals...")
            summary = self.summarize_monthly(df)
        else:
            raise ValueError("interval must be 'hourly', 'daily', or 'monthly'")

        # Calculate weighted totals if requested
        if weighted:
            print("Calculating weighted energy totals...")
            summary = self.calculate_weighted_total(summary)

        # Generate output filename if not provided
        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            sites_str = "_".join(site_names) if len(site_names) <= 3 else f"{len(site_names)}_sites"
            output_file = self.base_dir / f"summary_{interval}_{sites_str}_{timestamp}.csv"
        else:
            output_file = Path(output_file)

        # Save to CSV
        summary.to_csv(output_file, index=False)
        print(f"\nSummary saved to: {output_file}")
        print(f"Total records in summary: {len(summary):,}")

        # Display preview
        print("\nPreview of summary data:")
        print(summary.head(10).to_string())

        # Display statistics
        self._print_statistics(summary, interval, weighted)

        return summary

    def _print_statistics(self, df, interval, weighted):
        """Print summary statistics"""
        print(f"\n{'='*80}")
        print("SUMMARY STATISTICS")
        print(f"{'='*80}")

        for site in df['name'].unique():
            site_data = df[df['name'] == site]
            print(f"\nSite: {site}")
            print(f"  Total capacity: {site_data['total_capacity_kwp'].iloc[0]:.1f} kWp")
            print(f"  Number of periods: {len(site_data)}")
            print(f"  GTI mean: {site_data['gti'].mean():.4f} kW/m²")
            print(f"  GTI total: {site_data['gti'].sum():.2f} kWh/m²")

            if weighted:
                print(f"  Total energy (GTI): {site_data['gti_energy_kwh'].sum():.2f} kWh")


def display_site_list(sites):
    """Display available sites in a formatted list"""
    print(f"\n{'='*80}")
    print("AVAILABLE SITES")
    print(f"{'='*80}")
    for i, site in enumerate(sites, 1):
        print(f"{i:3d}. {site}")
    print(f"{'='*80}")
    print(f"Total: {len(sites)} sites\n")


def get_site_selection(available_sites):
    """Interactive site selection"""
    display_site_list(available_sites)

    print("Site Selection Options:")
    print("  - Enter site numbers (comma-separated): e.g., '1,3,5'")
    print("  - Enter range: e.g., '1-5'")
    print("  - Enter 'all' for all sites")
    print("  - Enter site names directly (comma-separated)")

    selection = input("\nYour selection: ").strip()

    if selection.lower() == 'all':
        return available_sites

    selected_sites = []

    # Try to parse as numbers or ranges
    try:
        for part in selection.split(','):
            part = part.strip()
            if '-' in part and part.replace('-', '').isdigit():
                # Range
                start, end = map(int, part.split('-'))
                for i in range(start, end + 1):
                    if 1 <= i <= len(available_sites):
                        selected_sites.append(available_sites[i - 1])
            elif part.isdigit():
                # Single number
                idx = int(part)
                if 1 <= idx <= len(available_sites):
                    selected_sites.append(available_sites[idx - 1])
            else:
                # Try as site name
                if part in available_sites:
                    selected_sites.append(part)
    except:
        # If parsing fails, try as site names
        selected_sites = [s.strip() for s in selection.split(',') if s.strip() in available_sites]

    return list(set(selected_sites))  # Remove duplicates


def get_interval_selection():
    """Interactive interval selection"""
    print("\nInterval Selection:")
    print("  1. Hourly")
    print("  2. Daily")
    print("  3. Monthly")

    choice = input("\nSelect interval (1-3): ").strip()

    interval_map = {'1': 'hourly', '2': 'daily', '3': 'monthly'}
    return interval_map.get(choice, 'daily')


def get_weighted_selection():
    """Ask if user wants weighted calculation"""
    choice = input("\nCalculate weighted energy totals by array capacity? (y/n): ").strip().lower()
    return choice == 'y'


def main():
    """Main interactive function"""
    # Use script's directory as base_dir for portability
    base_dir = Path(__file__).parent.resolve()

    print("="*80)
    print("IRRADIANCE DATA SUMMARIZER")
    print("="*80)

    # Initialize summarizer
    summarizer = IrradianceSummarizer(base_dir)

    if not summarizer.available_sites:
        print("Error: No sites found in the data directory.")
        return

    # Get user selections
    selected_sites = get_site_selection(summarizer.available_sites)

    if not selected_sites:
        print("Error: No valid sites selected.")
        return

    print(f"\nSelected {len(selected_sites)} site(s):")
    for site in selected_sites:
        print(f"  - {site}")

    interval = get_interval_selection()
    weighted = get_weighted_selection()

    # Perform summarization
    summary = summarizer.summarize(
        site_names=selected_sites,
        interval=interval,
        weighted=weighted
    )

    print(f"\n{'='*80}")
    print("COMPLETE!")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()
