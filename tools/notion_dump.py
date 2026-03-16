import os
import sys

# Add the src folder to path so we can import the module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "GitHub", "solar-platform", "src")))

from solar_platform.services.lookup import NotionSiteLookup # actually wait, the filename is 2026-02-15-Services-File-Data-Pull-v01.py and we don't have an __init__.py that exports it neatly probably.

def main():
    pass

if __name__ == "__main__":
    main()
