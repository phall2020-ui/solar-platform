# Utility functions for Solar Toolkit
import logging
from datetime import datetime
from typing import Optional, Tuple

def setup_logging(verbose: bool = False, log_to_file: Optional[str] = None):
    """Configures logging for the application."""
    level = logging.DEBUG if verbose else logging.INFO
    
    handlers = []
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    handlers.append(console_handler)
    
    # File handler (optional)
    if log_to_file:
        file_handler = logging.FileHandler(log_to_file)
        file_handler.setLevel(logging.DEBUG)
        handlers.append(file_handler)

    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers,
        force=True
    )

def date_range_to_ts(start_date: str, end_date: str) -> Tuple[str, str]:
    """Converts YYYYMMDD dates to ISO timestamps for query boundaries."""
    try:
        start_dt = datetime.strptime(start_date, "%Y%m%d")
        end_dt = datetime.strptime(end_date, "%Y%m%d")
        start_ts = start_dt.isoformat() + "Z"
        end_ts = (end_dt.replace(hour=23, minute=59, second=59, microsecond=999999)).isoformat() + "Z"
        return start_ts, end_ts
    except ValueError as e:
        raise ValueError(f"Invalid date format (must be YYYYMMDD): {e}")

logger = logging.getLogger("solar_toolkit")
