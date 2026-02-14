# Central configuration for the Solar Toolkit
import os
from dotenv import load_dotenv

# Load environment variables from a .env file if it exists
load_dotenv()

class Settings:
    # EMIG API Settings (Primary API for Juggle/EMIG data)
    # Correct base URL: https://www.emig.co.uk/api (without /p/)
    EMIG_API_URL = os.getenv("EMIG_API_URL", "https://www.emig.co.uk/api")
    EMIG_API_KEY = os.getenv("EMIG_API_KEY", os.getenv("JUGGLE_APIKEY"))  # Fallback to JUGGLE_APIKEY
    
    # Legacy Juggle API Settings (deprecated - api.juggle.energy no longer resolves)
    JUGGLE_BASE_URL = os.getenv("JUGGLE_BASE_URL", "https://api.juggle.energy/v1")
    JUGGLE_API_KEY = os.getenv("JUGGLE_API_KEY")
    
    # Crawler Settings (Web scraper fallback)
    JUGGLE_USERNAME = os.getenv("JUGGLE_USERNAME")
    JUGGLE_PASSWORD = os.getenv("JUGGLE_PASSWORD")
    CRAWLER_HEADLESS = os.getenv("CRAWLER_HEADLESS", "true").lower() == "true"
    
    # Database Settings
    DB_PATH = os.path.join(os.path.expanduser("~"), ".solar_toolkit", "plant_registry.sqlite")
    
    # Data Interval Settings
    DEFAULT_MIN_INTERVAL_S = int(os.getenv("DEFAULT_MIN_INTERVAL_S", 900))  # 15 minutes (aligned)
    DATA_INTERVAL_MINUTES = 15  # Standard interval for all data alignment
    MAX_DAYS_PER_REQUEST = 90  # Max days per API request (to avoid 413 errors)
    
    # Analysis Defaults (used by Fouling/Shading if not overridden)
    POA_IRRADIANCE_COL = "poaIrradiance"
    POWER_COL_PREFERENCES = ("apparentPower", "activePower", "dcCurrent", "exportEnergy")

settings = Settings()
