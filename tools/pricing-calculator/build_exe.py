"""
Build script for creating the AMPYR Pricing Calculator .exe
============================================================

Usage (on Windows):
    pip install -r requirements.txt
    python build_exe.py

This will create:
    dist/AMPYR_Pricing_Calculator.exe
"""

import PyInstaller.__main__
import os
import sys

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAIN_SCRIPT = os.path.join(BASE_DIR, "pricing_app", "main.py")
ICON_PATH = os.path.join(BASE_DIR, "pricing_app", "assets", "icon.ico")
ASSETS_DIR = os.path.join(BASE_DIR, "pricing_app", "assets")

args = [
    MAIN_SCRIPT,
    "--name=AMPYR_Pricing_Calculator",
    "--onefile",
    "--windowed",
    "--noconfirm",
    "--clean",
    # Include the assets directory
    f"--add-data={ASSETS_DIR}{os.pathsep}pricing_app/assets",
    # Hidden imports that PyInstaller may miss
    "--hidden-import=numpy",
    "--hidden-import=numpy_financial",
    "--hidden-import=scipy.optimize",
    "--hidden-import=openpyxl",
    "--hidden-import=reportlab",
    "--hidden-import=customtkinter",
    "--hidden-import=PIL",
    # Collect all customtkinter data files (themes, etc.)
    "--collect-all=customtkinter",
]

# Add icon if it exists
if os.path.exists(ICON_PATH):
    args.append(f"--icon={ICON_PATH}")

print("=" * 60)
print("  AMPYR Pricing Calculator — Building .exe")
print("=" * 60)
print(f"  Source: {MAIN_SCRIPT}")
print(f"  Output: dist/AMPYR_Pricing_Calculator.exe")
print("=" * 60)

PyInstaller.__main__.run(args)

print()
print("=" * 60)
print("  Build complete!")
print("  Output: dist/AMPYR_Pricing_Calculator.exe")
print("=" * 60)
