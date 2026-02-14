"""
CLI: Command Line Interface for Solar Toolkit.
Uses argparse to expose all Orchestrator functions.
"""
import argparse
import sys
import os
from typing import Sequence, Optional
from solar_toolkit.orchestrator import AnalysisOrchestrator
from solar_toolkit.utils import setup_logging, logger
from solar_toolkit.config import settings

# Try to import tkinter, but make it optional
try:
    import tkinter as tk
    from tkinter import filedialog
    TKINTER_AVAILABLE = True
except ImportError:
    TKINTER_AVAILABLE = False
    # Don't log here as logger may not be initialized yet

def _file_dialog(title="Select File", filetypes=[("CSV", "*.csv")]):
    """Opens a file selection dialog (requires tkinter)."""
    if not TKINTER_AVAILABLE:
        logger.error("File dialog requires tkinter. Please provide path as command-line argument.")
        return None
    try:
        root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
        f = filedialog.askopenfilename(title=title, filetypes=filetypes)
        root.destroy()
        return f
    except Exception as e:
        logger.error(f"Could not open file dialog: {e}")
        return None

def _folder_dialog(title="Select Folder"):
    """Opens a folder selection dialog (requires tkinter)."""
    if not TKINTER_AVAILABLE:
        logger.error("Folder dialog requires tkinter. Please provide path as command-line argument.")
        return None
    try:
        root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
        f = filedialog.askdirectory(title=title)
        root.destroy()
        return f
    except Exception as e:
        logger.error(f"Could not open folder dialog: {e}")
        return None
        
def build_parser():
    """Builds the main argument parser with subcommands."""
    parser = argparse.ArgumentParser(description="Solar Toolkit CLI for PV analysis and data management.")
    parser.add_argument("--db-path", default=settings.DB_PATH, help=f"Path to plant registry SQLite file (default: {settings.DB_PATH})")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging (DEBUG level).")
    
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- fetch ---
    p_fetch = subparsers.add_parser("fetch", help="Fetch operational data from Juggle API.")
    p_fetch.add_argument("--plant-uid", required=True, help="Plant unique ID (e.g., ERS:00001).")
    p_fetch.add_argument("--start", required=True, help="Start date (YYYYMMDD).")
    p_fetch.add_argument("--end", required=True, help="End date (YYYYMMDD).")
    p_fetch.add_argument("--output", help="Optional path to save combined data as CSV.")
    p_fetch.set_defaults(func=run_fetch)

    # --- fouling-auto ---
    p_fouling = subparsers.add_parser("fouling-auto", help="Run fouling analysis using auto-selected clean period from a single CSV.")
    p_fouling.add_argument("data_csv", nargs='?', help="Path to the full operational CSV file.")
    p_fouling.add_argument("--dc-size-kw", type=float, required=True, help="DC nameplate capacity in kW.")
    p_fouling.add_argument("--auto-days", type=int, default=3, help="Number of days for auto-clean period selection (default: 3).")
    p_fouling.set_defaults(func=run_fouling_auto)

    # --- shading ---
    p_shading = subparsers.add_parser("shading", help="Run shading analysis comparing two seasonal datasets.")
    p_shading.add_argument("summer_csv", nargs='?', help="Path to the Summer (Baseline) CSV file.")
    p_shading.add_argument("winter_csv", nargs='?', help="Path to the Winter (Shaded) CSV file.")
    p_shading.add_argument("--output", default="shading_report", help="Base filename for output CSV and PDF.")
    p_shading.set_defaults(func=run_shading)
    
    # --- poa-import ---
    p_poa = subparsers.add_parser("poa-import", help="Import SolarGIS POA data into the plant registry.")
    p_poa.add_argument("--plant-alias", required=True, help="Plant alias (must be registered via store).")
    p_poa.add_argument("--folder", nargs='?', help="Path to the folder containing SolarGIS CSVs.")
    p_poa.add_argument("--start", required=True, help="Start date (YYYYMMDD).")
    p_poa.add_argument("--end", required=True, help="End date (YYYYMMDD).")
    p_poa.set_defaults(func=run_poa_import)
    
    # --- poa-bulk-import ---
    p_poa_bulk = subparsers.add_parser("poa-bulk-import", help="Bulk import SolarGIS POA data with manual matching.")
    p_poa_bulk.add_argument("--folder", nargs='?', help="Path to the folder containing SolarGIS CSVs.")
    p_poa_bulk.add_argument("--start", required=True, help="Start date (YYYYMMDD).")
    p_poa_bulk.add_argument("--end", required=True, help="End date (YYYYMMDD).")
    p_poa_bulk.add_argument("--auto-confirm", action="store_true", help="Auto-confirm matches without manual review.")
    p_poa_bulk.set_defaults(func=run_poa_bulk_import)
    
    # --- store-list ---
    p_store = subparsers.add_parser("store-list", help="List all plants registered in the local database.")
    p_store.set_defaults(func=run_store_list)

    return parser

def run_fetch(args):
    orch = AnalysisOrchestrator(args.db_path)
    count = orch.fetch_data(args.plant_uid, args.start, args.end, args.output)
    logger.info(f"Successfully fetched and stored {count} readings.")

def run_fouling_auto(args):
    data_csv = args.data_csv or _file_dialog("Select Full Operational Data CSV")
    if not data_csv: return
    
    # Ensure file exists before proceeding
    if not os.path.exists(data_csv):
        logger.error(f"File not found: {data_csv}")
        return
        
    orch = AnalysisOrchestrator(args.db_path)
    result = orch.run_fouling_auto(data_csv, args.dc_size_kw, args.auto_days)
    
    logger.info("--- Fouling Analysis Results ---")
    logger.info(f"Fouling Index: {result['fouling_index']:.4f}")
    logger.info(f"Fouling Level: {result['fouling_level']}")

def run_shading(args):
    summer_csv = args.summer_csv or _file_dialog("Select Summer (Baseline) CSV")
    if not summer_csv: return
    winter_csv = args.winter_csv or _file_dialog("Select Winter (Shaded) CSV")
    if not winter_csv: return
    
    # Ensure files exist before proceeding
    if not os.path.exists(summer_csv):
        logger.error(f"Summer file not found: {summer_csv}")
        return
    if not os.path.exists(winter_csv):
        logger.error(f"Winter file not found: {winter_csv}")
        return
    
    orch = AnalysisOrchestrator(args.db_path)
    orch.run_shading_analysis(summer_csv, winter_csv, args.output)
    logger.info(f"Shading analysis complete. Results saved to {args.output}.pdf and {args.output}_detail.csv.")

def run_poa_import(args):
    folder = args.folder or _folder_dialog("Select SolarGIS Data Folder")
    if not folder: return
    
    # Ensure folder exists before proceeding
    if not os.path.isdir(folder):
        logger.error(f"Folder not found: {folder}")
        return

    orch = AnalysisOrchestrator(args.db_path)
    count = orch.import_poa(args.plant_alias, folder, args.start, args.end)
    logger.info(f"Successfully imported {count} POA readings for {args.plant_alias}.")

def run_poa_bulk_import(args):
    """Handle bulk POA import with manual matching."""
    folder = args.folder or _folder_dialog("Select SolarGIS Data Folder")
    if not folder: return
    
    # Ensure folder exists before proceeding
    if not os.path.isdir(folder):
        logger.error(f"Folder not found: {folder}")
        return

    orch = AnalysisOrchestrator(args.db_path)
    results = orch.bulk_import_poa(folder, args.start, args.end, auto_confirm=args.auto_confirm)
    
    # Display results
    total_imported = sum(results.values())
    logger.info(f"\n{'='*60}")
    logger.info(f"BULK IMPORT COMPLETE")
    logger.info(f"{'='*60}")
    for filename, count in results.items():
        logger.info(f"  {filename}: {count} readings")
    logger.info(f"Total: {total_imported} readings imported across {len(results)} files.")
    logger.info(f"{'='*60}\n")

def run_store_list(args):
    orch = AnalysisOrchestrator(args.db_path)
    plants = orch.get_plants()
    if not plants:
        logger.info("No plants registered.")
        return
        
    logger.info("\n--- Registered Plants ---")
    for p in plants:
        dc_size = f"{p['dc_size_kw']:.1f}kW" if p.get('dc_size_kw') else "N/A"
        logger.info(f"Alias: {p['alias']} | UID: {p['plant_uid']} | DC Size: {dc_size}")

def run(argv: Optional[Sequence[str]] = None) -> None:
    """Main entry point for the CLI."""
    parser = build_parser()
    
    if argv is None and len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)
        
    args = parser.parse_args(argv)
    
    # Setup logging early
    setup_logging(verbose=args.verbose)
    
    try:
        # Check if the required 'func' attribute is set (meaning a subcommand was provided)
        if hasattr(args, 'func'):
            args.func(args)
        else:
            parser.print_help()
             
    except FileNotFoundError as e:
        logger.error(f"File Error: {e}")
        sys.exit(1)
    except ValueError as e:
        logger.error(f"Input Error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"An unexpected error occurred: {type(e).__name__}: {e}")
        sys.exit(1)
        
if __name__ == "__main__":
    run()
