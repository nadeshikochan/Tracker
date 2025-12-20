@echo off
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo Creating venv...
    python -m venv venv
    call venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate.bat
)

echo Starting AI Time Tracker...
echo WebUI: http://localhost:8502
echo.

start "" venv\Scripts\pythonw.exe launcher.py

timeout /t 2 /nobreak >nul
