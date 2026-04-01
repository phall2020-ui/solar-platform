@echo off
echo ============================================================
echo   AMPYR Distributed Energy - Pricing Calculator Builder
echo ============================================================
echo.
echo Installing dependencies...
pip install -r requirements.txt
echo.
echo Building .exe...
python build_exe.py
echo.
echo Done! Check the dist\ folder for AMPYR_Pricing_Calculator.exe
pause
