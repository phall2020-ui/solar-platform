"""
Command-line script to summarize irradiance data at hourly, daily, or monthly intervals.
Non-interactive version for automation and scripting.

Usage:
    python irradiance_summary_cli.py --sites Blachford,Cromwell_Tools --interval daily
    python irradiance_summary_cli.py --sites all --interval monthly --weighted
    python irradiance_summary_cli.py --list-sites
"""
import pandas as pd
import argparse
from pathlib import Path
from datetime import datetime
import sys
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
        exclude_patterns = ['pvgis', 'compare', 'test', 'summary', 'combined']

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
                        # Skip rows where 'time' column contains 'time' (duplicate headers)
                        if 'time' in df.columns:
                            df = df[df['time'] != 'time']
                        all_data.append(df)
                    except Exception as e:
                        print(f"Warning: Error reading {csv_file}: {e}", file=sys.stderr)

        if not all_data:
            return None

        # Combine all data
        combined_df = pd.concat(all_data, ignore_index=True)

        # Convert time column to datetime with flexible parsing
        combined_df['time'] = pd.to_datetime(combined_df['time'], format='mixed', utc=True)

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
        df['gti_energy_kwh'] = df['gti'] * df['total_capacity_kwp']
        df['gti_low_energy_kwh'] = df['gti_low'] * df['total_capacity_kwp']
        df['gti_high_energy_kwh'] = df['gti_high'] * df['total_capacity_kwp']
        df['ghi_energy_kwh'] = df['ghi'] * df['total_capacity_kwp']

        return df

    def summarize(self, site_names, interval='daily', weighted=False, output_file=None, quiet=False):
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
        quiet : bool
            If True, suppress non-essential output

        Returns:
        --------
        pd.DataFrame : Summarized data
        """
        if not quiet:
            print(f"\nLoading data for {len(site_names)} site(s)...")

        df = self._load_site_data(site_names)

        if df is None or len(df) == 0:
            print("Error: No data found for the selected sites.", file=sys.stderr)
            return None

        if not quiet:
            print(f"Loaded {len(df):,} records")
            print(f"Date range: {df['time'].min()} to {df['time'].max()}")

        # Apply summarization
        if interval == 'hourly':
            if not quiet:
                print("\nSummarizing to hourly intervals...")
            summary = self.summarize_hourly(df)
        elif interval == 'daily':
            if not quiet:
                print("\nSummarizing to daily intervals...")
            summary = self.summarize_daily(df)
        elif interval == 'monthly':
            if not quiet:
                print("\nSummarizing to monthly intervals...")
            summary = self.summarize_monthly(df)
        else:
            raise ValueError("interval must be 'hourly', 'daily', or 'monthly'")

        # Calculate weighted totals if requested
        if weighted:
            if not quiet:
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
        print(f"Summary saved to: {output_file}")

        if not quiet:
            print(f"Total records in summary: {len(summary):,}")
            print("\nPreview of summary data:")
            print(summary.head(10).to_string())
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


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Summarize irradiance data at different time intervals',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Summarize two sites daily
  python irradiance_summary_cli.py --sites Blachford,Cromwell_Tools --interval daily

  # Summarize all sites monthly with weighted calculation
  python irradiance_summary_cli.py --sites all --interval monthly --weighted

  # List all available sites
  python irradiance_summary_cli.py --list-sites

  # Specify output file
  python irradiance_summary_cli.py --sites Blachford --interval hourly --output my_summary.csv
        """
    )

    parser.add_argument(
        '--sites',
        type=str,
        help='Comma-separated list of site names, or "all" for all sites'
    )

    parser.add_argument(
        '--interval',
        type=str,
        choices=['hourly', 'daily', 'monthly'],
        default='daily',
        help='Time interval for summarization (default: daily)'
    )

    parser.add_argument(
        '--weighted',
        action='store_true',
        help='Calculate weighted energy totals by array capacity'
    )

    parser.add_argument(
        '--output',
        type=str,
        help='Output CSV file path (auto-generated if not specified)'
    )

    parser.add_argument(
        '--list-sites',
        action='store_true',
        help='List all available sites and exit'
    )

    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Suppress non-essential output'
    )

    return parser.parse_args()


def main():
    """Main function"""
    # Use script's directory as base_dir for portability
    base_dir = Path(__file__).parent.resolve()

    args = parse_arguments()

    # Initialize summarizer
    summarizer = IrradianceSummarizer(base_dir)

    if not summarizer.available_sites:
        print("Error: No sites found in the data directory.", file=sys.stderr)
        sys.exit(1)

    # List sites if requested
    if args.list_sites:
        print(f"\nAvailable sites ({len(summarizer.available_sites)}):")
        for i, site in enumerate(summarizer.available_sites, 1):
            print(f"{i:3d}. {site}")
        sys.exit(0)

    # Validate sites argument
    if not args.sites:
        print("Error: --sites argument is required (or use --list-sites)", file=sys.stderr)
        sys.exit(1)

    # Parse site selection
    if args.sites.lower() == 'all':
        selected_sites = summarizer.available_sites
    else:
        selected_sites = [s.strip() for s in args.sites.split(',')]
        # Validate site names
        invalid_sites = [s for s in selected_sites if s not in summarizer.available_sites]
        if invalid_sites:
            print(f"Error: Invalid site names: {', '.join(invalid_sites)}", file=sys.stderr)
            print("Use --list-sites to see available sites", file=sys.stderr)
            sys.exit(1)

    if not args.quiet:
        print(f"\nSelected {len(selected_sites)} site(s):")
        for site in selected_sites:
            print(f"  - {site}")

    # Perform summarization
    summary = summarizer.summarize(
        site_names=selected_sites,
        interval=args.interval,
        weighted=args.weighted,
        output_file=args.output,
        quiet=args.quiet
    )

    if summary is None:
        sys.exit(1)

    if not args.quiet:
        print(f"\n{'='*80}")
        print("COMPLETE!")
        print(f"{'='*80}")


if __name__ == "__main__":
    main()
