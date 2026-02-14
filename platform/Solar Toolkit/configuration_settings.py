"""
Central configuration for the Solar Toolkit.
"""
import os
from dotenv import load_dotenv

# Load environment variables from a .env file if it exists
load_dotenv()

# --- Core Settings ---
class Settings:
    # API Settings (Juggle Energy)
    JUGGLE_BASE_URL = os.getenv("JUGGLE_BASE_URL", "https://api.juggle.energy/v1")
    JUGGLE_API_KEY = os.getenv("JUGGLE_API_KEY")

    # Database Settings
    DB_PATH = os.path.join(os.path.expanduser("~"), ".solar_toolkit", "plant_registry.sqlite")

    # Fetching Defaults
    DEFAULT_MIN_INTERVAL_S = int(os.getenv("DEFAULT_MIN_INTERVAL_S", 1800)) # 30 minutes

    # Analysis Defaults (used by Fouling/Shading if not overridden)
    POA_IRRADIANCE_COL = "poaIrradiance"
    POWER_COL_PREFERENCES = ("apparentPower", "activePower", "dcCurrent", "exportEnergy")

settings = Settings()
