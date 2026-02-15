# Findings & Decisions: Solargis Monthly Aggregator + Away Day Deck

## Requirements (from user)
- Find the “67 sites (3)” file in Google Drive.
- Add/import it into the Solargis / monthly aggregator DB.
- Update the DB for all new irradiance files and sites.
- In parallel: find the Away Day presentation project in Notion; start planning and developing slides in detail.
- Slides must follow “ADE style”.

## Research Findings
- Repo contains Google Drive API code under `jobs/inverter-daily-checks/`:
  - `jobs/inverter-daily-checks/google_drive.py`
  - Config keys referenced include `google_drive.enabled`, `google_drive.folder_id`, `google_drive.credentials_file` (default `credentials.json`). (Found via ripgrep.)
- `platform/services/notion_irradiance_sync.py` reads monthly site data from a DuckDB database (table `solar_data`) and merges SolarGIS monthly aggregates.
- Notion project exists: “Away Day Presentation — Solar Portfolio Performance” (`https://www.notion.so/26931b217bf1455e96fa2ba65800ba3f`) with initial key messages and a detailed proposed slide structure task (`https://www.notion.so/4153c8f2913e4d08b3326aab58d511b0`).
- Local shell does not have `python` on PATH (command not found); likely need to use `python3`.
- DuckDB DB found at `~/.solar_toolkit/plant_registry.duckdb`; in current state it contains `solar_data` but `readings`/`plants` are empty.
- `solar_data` currently has 17 sites across 8 months (`Apr-25`..`Nov-25`).
- Found “67 sites” workbook locally (Jan 2026, 67 rows): `"/Users/peterhall/My Drive/All Sites January.xlsx"` (also duplicated at `"/Users/peterhall/Documents/Python Scripts/67 Sites.xlsx"`).
  - Sheet: `Whole Period Summary`
  - Date range: `01/01/2026` → `31/01/2026` (so target month label should be `Jan-26`)
  - Columns include generation vs budget, weather-adjusted budget, export/self-consumption, PR, availability, and revenues (no irradiance columns).
- Implemented local ingestion scripts:
  - `platform/scripts/import_solar_data_all_sites_xlsx.py` imports the “All Sites” workbook into DuckDB `solar_data` for the inferred month label (e.g. `Jan-26`).
  - `platform/scripts/import_solar_data_excom_xlsx.py` imports ADE Excom “postPAC” sheets into DuckDB `solar_data`, normalizing date labels to `Mon-YY` and mapping `Irr Losses (kWh)` → `Irr Variation (kWh)`.
- Persisted SolarGIS monthly aggregates into DuckDB:
  - `platform/services/solargis_monthly_aggregator.py` supports `--write-db` and writes a `solargis_monthly` table.
  - Current table size: 409 site-months across 69 sites (months include `Jan-26`).
- Notion sync now prefers persisted SolarGIS data:
  - `platform/services/notion_irradiance_sync.py` reads `solargis_monthly` from DuckDB when present; otherwise falls back to on-the-fly CSV aggregation.
  - Filters non-site rollups (`Site` in {`Summary`, `Oasis`}) for Notion output and normalizes site lookup for suffix markers (e.g. `Metro Centre*`).

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Use existing Drive API module if it supports file search/download | Avoid re-implementing OAuth/client plumbing |
| Import sites + irradiance idempotently (upsert) | Safe re-runs; avoids dupes when backfilling |
| Persist SolarGIS monthly irradiance into DuckDB | Fast joins + explicit refresh point for downstream sync/reporting |
| Build Away Day deck by duplicating a content-layout slide from the ADE template | Keeps ADE style without re-creating theme/layout from scratch |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| `tools/irradiation-data/site_summary.csv` missing 4 sites present in `tools/irradiation-data/2026 01/*.csv` | `Carlton Thorpe Primary`, `Casepak Sunningdale`, `Casepak Warren Park Way`, `Wienerberger - Smeed` not present; likely needs re-generation from latest CSVs |
| Some `solar_data` site labels are rollups (`Summary`, `Oasis`) or have suffix markers (`*`) | Excluded rollups from Notion sync output and normalized lookup for suffix markers |

## Resources
- `jobs/inverter-daily-checks/google_drive.py`
- `jobs/inverter-daily-checks/inverter_monitor.py` (references Drive config)
- `platform/services/notion_irradiance_sync.py`
- `platform/services/solargis_monthly_aggregator.py`
- `~/.solar_toolkit/plant_registry.duckdb` (target DB)
- `"/Users/peterhall/My Drive/All Sites January.xlsx"` (Jan 2026 / 67 sites source)
- `platform/reports/away_day_2026/ade_style_template.pptx` (ADE style reference)
- `platform/reports/away_day_2026/away_day_2026_solar_portfolio_performance.pptx` (generated deck)

## Visual/Browser Findings
- (none yet)
