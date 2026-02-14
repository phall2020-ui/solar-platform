# Solar Toolkit ⚡

A comprehensive Python toolkit for solar PV plant analysis, data management, and performance monitoring.

## Features

- **Data Fetching**: Download operational data from Juggle Energy API
- **Web Crawler**: Scrape data for devices with incomplete API coverage
- **Fouling Analysis**: Detect and quantify solar panel soiling
- **Shading Analysis**: Compare seasonal performance to identify shading losses
- **POA Import**: Import SolarGIS plane-of-array irradiance data
  - Single plant import with manual file selection
  - **Bulk upload** with automatic fuzzy matching of files to plants
  - Preview linkage showing how POA data connects to inverters and sites
  - Manual confirmation before import for unmatched files
- **Plant Registry**: SQLite database for managing plant configurations
- **Web UI**: Interactive Streamlit interface for all analysis functions
- **CLI**: Command-line interface for automation and scripting

## Installation

### Prerequisites

- Python 3.12 or later
- SQLite3
- System packages: `python3-tk` (for GUI dialogs)

### Install Dependencies

```bash
# Install system packages
sudo apt-get update
sudo apt-get install -y python3-tk

# Install Python packages
pip install python-dotenv pandas streamlit altair playwright
```

### Configuration

Copy the example environment file and configure your credentials:

```bash
cp .env.example .env
# Edit .env with your API keys and credentials
```

Environment variables:
- `JUGGLE_API_KEY`: API key for Juggle Energy standard API
- `JUGGLE_USERNAME`: Email for web crawler authentication
- `JUGGLE_PASSWORD`: Password for web crawler authentication
- `EMIG_API_KEY`: API key for EMIG data endpoint
- `CRAWLER_HEADLESS`: Set to `true` for headless browser mode

## Usage

### Command Line Interface (CLI)

Run the CLI with:

```bash
python3 entry_point.py [command] [options]
```

#### Available Commands

**List registered plants:**
```bash
python3 entry_point.py store-list
```

**Fetch operational data:**
```bash
python3 entry_point.py fetch --plant-uid ERS:00001 --start 20250101 --end 20250131
```

**Run fouling analysis:**
```bash
python3 entry_point.py fouling-auto data.csv --dc-size-kw 250.5 --auto-days 3
```

**Run shading analysis:**
```bash
python3 entry_point.py shading summer.csv winter.csv --output shading_report
```

**Import POA data (single plant):**
```bash
python3 entry_point.py poa-import --plant-alias MyPlant --folder /path/to/solargis --start 20250101 --end 20250131
```

**Bulk import POA data (multiple plants with auto-matching):**
```bash
python3 entry_point.py poa-bulk-import --folder /path/to/solargis --start 20250101 --end 20250131
```

The bulk import feature will:
- Scan the folder for all CSV files
- Auto-match files to registered plants using fuzzy matching
- Show a preview of how data will be linked to inverters and sites
- Request confirmation before importing
- Only import data that has been successfully matched to a registered plant

Add `--auto-confirm` to skip the confirmation prompt:
```bash
python3 entry_point.py poa-bulk-import --folder /path/to/solargis --start 20250101 --end 20250131 --auto-confirm
```

**Get help:**
```bash
python3 entry_point.py --help
python3 entry_point.py [command] --help
```

### Streamlit Web UI

Launch the web interface:

```bash
streamlit run streamlit_app.py
```

The app will open in your default browser at `http://localhost:8501`.

Features:
- **Data Fetch**: Download data via API or web crawler
- **POA Import**: Import SolarGIS irradiance data
  - **Single Plant Mode**: Import data for one plant at a time
  - **Bulk Upload Mode**: Import multiple files with auto-matching and preview
- **Fouling Analysis**: Analyze panel soiling with auto-detection
- **Shading Analysis**: Compare seasonal performance
- **Register Plant**: Add new plants to the registry
- **Database Viewer**: View, filter, edit, and delete database contents
  - **Plants Registry**: View and manage registered plants
  - **Operational Readings**: View readings with flexible filtering by plant, device, and date range
  - Download data as CSV
  - Delete readings with confirmation

#### POA Bulk Upload Workflow

The bulk upload feature streamlines importing POA data for multiple plants:

1. **File Discovery**: Scans the selected folder for all CSV files
2. **Auto-Matching**: Uses fuzzy string matching to pair files with registered plants
3. **Linkage Preview**: Shows exactly how POA data will connect to existing site data:
   - Plant details (UID, DC size)
   - POA device ID that will be created
   - Existing inverters at the site
   - Weather station ID
   - Data statistics (date range, POA values)
4. **Confirmation**: Displays matched and unmatched files for review
5. **Import**: Only imports data for successfully matched files

Files that don't match any registered plant are skipped automatically.

#### Database Viewer

The Database Viewer provides comprehensive access to view and manage all data stored in the local SQLite database.

**Plants Registry View:**
- View all registered plants in a tabular format
- See plant UID, inverter IDs, weather station ID, and DC capacity
- Download plants data as CSV
- Delete plants from the registry

**Operational Readings View:**
- View operational data with real-time statistics
  - Total readings count
  - Number of unique plants and devices
  - Date range of available data
- **Flexible Filtering Options:**
  - Filter by plant UID (select specific plant or view all)
  - Filter by device EMIG ID (inverters, weather stations, etc.)
  - Filter by date range (start and end dates)
  - Control display limit (10 to 10,000 rows)
- **Data Management:**
  - Load and preview filtered data in an interactive table
  - Download filtered data as CSV for external analysis
  - Delete readings with confirmation and safety checks
  - Expanded payload columns for easy data inspection

The viewer automatically expands nested JSON data structures (like `apparentPower: {value: 100, unit: "kW"}`) into separate columns for easier analysis.

## Database

The toolkit uses an SQLite database to store plant configurations and operational data.

**Default location:** `~/.solar_toolkit/plant_registry.sqlite`

See [database_contents.txt](database_contents.txt) for schema details and sample data.

## Project Structure

```
Solar-Toolkit/
├── entry_point.py              # CLI entry point
├── streamlit_app.py            # Web UI application
├── solar_toolkit/              # Main package
│   ├── __init__.py
│   ├── cli.py                 # CLI implementation
│   ├── orchestrator.py        # Main orchestration logic
│   ├── config.py              # Configuration management
│   ├── utils.py               # Utility functions
│   ├── data_fetcher.py        # API data fetching
│   ├── poa_importer.py        # SolarGIS data import
│   ├── fouling_analysis.py   # Fouling analysis algorithms
│   ├── shading_analysis.py   # Shading analysis algorithms
│   ├── plant_registry_store.py # Database operations
│   └── crawlers/              # Web crawler modules
│       └── juggle_adapter.py  # Juggle web interface scraper
├── .env.example               # Environment template
├── .gitignore                 # Git ignore rules
├── database_contents.txt      # Database documentation
└── README.md                  # This file
```

## Development

### Notebook Files

The project includes Jupyter notebook files with detailed documentation:
- `Command Line Interface` - CLI implementation details
- `Configuration Settings` - Configuration management
- `Data Fetcher` - API fetching logic
- `Fouling Analysis` - Soiling detection algorithms
- `Shading Analysis` - Seasonal comparison methods
- `POA Importer` - SolarGIS data import
- `Plant Registry Store` - Database schema
- `Orchestrator` - Main orchestration layer

### Testing

Test the CLI:
```bash
python3 entry_point.py store-list
```

Test the web UI:
```bash
streamlit run streamlit_app.py
```

### Logging

Enable verbose logging with the `-v` flag:
```bash
python3 entry_point.py -v store-list
```

## Screenshots

### Streamlit Web UI
![Solar Analytics Workbench](https://github.com/user-attachments/assets/aba19f6f-7b4d-4b7e-8e78-907236d9ebb0)

The web interface provides an intuitive way to:
- Fetch operational data from multiple sources
- Import POA irradiance data
- Run fouling and shading analysis
- Manage plant registry

## Troubleshooting

**Module not found errors:**
- Ensure you've installed all dependencies with pip
- Verify you're running from the repository root directory

**Database errors:**
- Check that the database directory exists: `~/.solar_toolkit/`
- Verify database permissions

**Web crawler issues:**
- Ensure credentials are configured in `.env`
- Try running with `CRAWLER_HEADLESS=false` to see browser window
- Install playwright browsers: `playwright install`

**Streamlit not loading:**
- Check port 8501 is not in use
- Try specifying a different port: `streamlit run streamlit_app.py --server.port 8502`

## License

This project is provided as-is for solar PV analysis and monitoring purposes.

## Contributing

Contributions are welcome! Please ensure:
- Code follows existing style conventions
- Functions include docstrings
- New features are tested
- Documentation is updated

## Support

For issues, questions, or feature requests, please open an issue on GitHub.
