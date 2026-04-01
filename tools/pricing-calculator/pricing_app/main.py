"""
AMPYR Distributed Energy - Solar PPA Pricing Calculator
=======================================================
Entry point for the desktop application.
"""

import sys
import os


def main():
    # Ensure we can find the package when running from PyInstaller bundle
    if hasattr(sys, "_MEIPASS"):
        os.chdir(sys._MEIPASS)

    from pricing_app.gui import run_app
    run_app()


if __name__ == "__main__":
    main()
