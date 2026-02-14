# Irradiance Data Summary Scripts

Two scripts for summarizing irradiance data at different time intervals (hourly, daily, monthly).

## Scripts

### 1. `irradiance_summary.py` - Interactive Version

Interactive script with prompts for user input.

**Usage:**
```bash
python irradiance_summary.py
```

**Features:**
- Browse and select from available sites
- Choose single or multiple sites
- Select time interval (hourly/daily/monthly)
- Option for weighted energy calculations
- Auto-generated output filenames

**Interactive Prompts:**
1. **Site Selection:**
   - Enter site numbers: `1,3,5`
   - Enter range: `1-5`
   - Type `all` for all sites
   - Enter site names directly: `Blachford,Cromwell_Tools`

2. **Interval Selection:**
   - `1` for Hourly
   - `2` for Daily
   - `3` for Monthly

3. **Weighted Calculation:**
   - `y` to calculate energy (kWh) weighted by array capacity
   - `n` for standard irradiance summary

### 2. `irradiance_summary_cli.py` - Command-Line Version

Non-interactive version for automation and scripting.

**Basic Usage:**
```bash
# List all available sites
python irradiance_summary_cli.py --list-sites

# Summarize specific sites
python irradiance_summary_cli.py --sites Blachford,Cromwell_Tools --interval daily

# Summarize all sites monthly
python irradiance_summary_cli.py --sites all --interval monthly

# With weighted calculation
python irradiance_summary_cli.py --sites Blachford --interval daily --weighted

# Specify output file
python irradiance_summary_cli.py --sites all --interval monthly --output monthly_summary.csv

# Quiet mode (minimal output)
python irradiance_summary_cli.py --sites Blachford --interval daily --quiet
```

**Arguments:**
- `--sites SITES`: Comma-separated site names or "all"
- `--interval {hourly,daily,monthly}`: Time interval (default: daily)
- `--weighted`: Calculate weighted energy totals by array capacity
- `--output FILE`: Specify output CSV file path
- `--list-sites`: List all available sites and exit
- `--quiet`: Suppress non-essential output

## Output

### Columns in Summary CSV

**Basic columns:**
- `name`: Site name
- `time`: Timestamp (start of period)
- `total_capacity_kwp`: Total site capacity combining all arrays (kWp)
- `gti`: Capacity-weighted average Global Tilted Irradiance (kW/m² or kWh/m² depending on interval)
- `gti_low`: Capacity-weighted average lower bound of GTI
- `gti_high`: Capacity-weighted average upper bound of GTI
- `ghi`: Capacity-weighted average Global Horizontal Irradiance

**Additional columns (with --weighted flag):**
- `gti_energy_kwh`: Total energy from GTI (kWh) = gti × total_capacity_kwp
- `gti_low_energy_kwh`: Total energy from lower bound
- `gti_high_energy_kwh`: Total energy from upper bound
- `ghi_energy_kwh`: Total energy from GHI

**Note:** When a site has multiple arrays (different azimuths/tilts), the irradiance values are **capacity-weighted averages** that combine all arrays into a single representative value for the site.

### Interval Aggregation Rules

**Multiple Array Handling:**
All summarizations combine multiple arrays per site using capacity-weighted averaging:
1. Each array's irradiance is weighted by its capacity (kWp)
2. Weighted values are summed
3. Result is divided by total site capacity
4. This produces a single representative irradiance value for the entire site

**Hourly:**
- Within each hour, readings are **averaged** for each array
- Arrays are then combined using capacity-weighted averaging
- Suitable for time-of-day analysis

**Daily:**
- Within each day, readings are **summed** for each array
- Arrays are then combined using capacity-weighted averaging
- Represents total daily irradiance (kWh/m²)

**Monthly:**
- Within each month, readings are **summed** for each array
- Arrays are then combined using capacity-weighted averaging
- Represents total monthly irradiance (kWh/m²)

## Examples

### Example 1: Daily Summary for One Site
```bash
python irradiance_summary_cli.py --sites Blachford --interval daily
```

Output: `summary_daily_Blachford_20251216_143022.csv`

### Example 2: Monthly Summary for Multiple Sites with Energy
```bash
python irradiance_summary_cli.py --sites "Blachford,Cromwell_Tools,Faltec_Europe_Ltd" --interval monthly --weighted
```

Output includes energy calculations in kWh.

### Example 3: Hourly Data for All Sites
```bash
python irradiance_summary_cli.py --sites all --interval hourly --output hourly_all_sites.csv
```

Creates a single CSV with hourly data for all available sites.

## Data Structure

The scripts automatically:
1. Scan all monthly folders (`2025 01`, `2025 02`, etc.)
2. Load matching CSV files for selected sites
3. Combine data across all months
4. Apply time-based aggregation
5. Export to CSV with statistics

## Notes

- **Site names** must match the CSV filenames (without `.csv` extension)
- Scripts automatically exclude test/comparison files (containing 'pvgis', 'compare', 'test', 'summary')
- **Weighted calculations** assume performance ratio = 1.0 (adjust in code if needed)
- Output files are timestamped to avoid overwrites
- All times are preserved in UTC from source data

## Troubleshooting

**"No data found for selected sites"**
- Check site names with `--list-sites`
- Ensure CSV files exist in monthly folders
- Verify file naming matches exactly

**"Invalid site names"**
- Use `--list-sites` to see exact names
- Site names are case-sensitive
- Remove any extra spaces

**Missing data for certain months**
- Scripts process only available monthly folders
- Output will include all found data with gaps where files are missing
