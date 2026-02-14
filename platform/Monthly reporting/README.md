# Monthly Data Reporting

## Overview
A set of Python scripts to automate monthly data processing, analysis and report generation. The project produces cleaned, aggregated datasets and formatted outputs that can be consumed directly or integrated with BI tools such as Power BI.

## Key features
- Parameterised monthly processing (month/year).
- ETL: load, clean, and join multiple input files.
- Aggregate and compute business KPIs and time-intelligence metrics.
- Export reports to Excel/CSV and prepare datasets for Power BI or paginated reports.
- Configurable via YAML/JSON parameters or CLI arguments.
- Logging and unit tests for maintainability.

## Quick start
1. Clone the repository:
	 ```powershell
	 git clone <repository-url>
	 cd "Monthly reporting"
	 ```
2. Create and activate a virtual environment:
	 ```powershell
	 python -m venv .venv
	 .\.venv\Scripts\Activate
	 ```
3. Install dependencies:
	 ```powershell
	 pip install -r requirements.txt
	 ```

## Usage
Run the main script with optional arguments (example):
```powershell
python main.py --config config.yaml --month November --year 2025
```

If your repo uses a different entrypoint (for example `app.py` or `analysis.py`), replace `main.py` accordingly.

## Configuration
Create or edit `config.yaml` (or `config.json`) to set:
- input file paths
- output folder
- reporting month/year
- email/notification settings
- Power BI export options

Example `config.yaml` keys:
```yaml
input:
	sales_csv: "data/sales_2025.csv"
output:
	folder: "out/"
report:
	month: "November"
	year: 2025
```

## Power BI integration
- Export cleaned datasets (CSV/Parquet/SQL) from the scripts and use them as Power BI data sources.
- Where possible, translate transforms to Power Query (M) and calculations to DAX for better performance and maintainability.
- Use Power Automate and Power BI Service for scheduled refreshes, export and emailing of reports. For paginated reports or automated formatted exports, Power BI Premium or Premium Per User (PPU) may be required.

## Development & testing
- Follow formatting and linting rules configured in `.flake8` and `pyproject.toml`.
- Run unit tests:
```powershell
pytest
```
- Use an editor (e.g., VS Code) for debugging and iterative development.

## Contributing
- Fork the repo and create feature branches: `feature/<name>`.
- Write tests for new functionality and update `requirements.txt` when adding packages.
- Open a pull request with a clear description and changelog.

## License
This project is released under the MIT License. See `LICENSE` for details.

## Contact
For questions or support, open an issue or contact the project owner.