@echo off
REM RoomCurve - Start Script (Windows)

cd /d "%~dp0"
set PYTHONPATH=%CD%;%PYTHONPATH%

echo.
echo  RoomCurve - Raumsimulator nach DIN EN ISO 52016-1
echo  ================================
echo.
echo  Starte Streamlit Server...
echo  Browser oeffnet automatisch auf http://localhost:8501
echo.

streamlit run gui/app.py
pause
