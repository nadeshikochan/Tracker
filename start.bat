@echo off
REM ==========================================
REM   AI Time Tracker - Start Script v2.1
REM   Fixed: Encoding issues, better error handling
REM ==========================================

REM Use UTF-8 codepage
chcp 65001 >nul 2>&1

REM Change to script directory
cd /d "%~dp0"
title AI Time Tracker

REM Enable delayed expansion
setlocal EnableDelayedExpansion

echo.
echo  ========================================
echo       AI Time Tracker - Starting...
echo  ========================================
echo.

REM ========= 1. Check Python =========
echo [1/5] Checking Python...
where python >nul 2>&1
if !errorlevel! neq 0 (
    echo.
    echo [ERROR] Python not found in PATH!
    echo Please install Python 3.8+ and add to PATH
    echo Download: https://www.python.org/downloads/
    echo.
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    goto END
)

python --version 2>&1
if !errorlevel! neq 0 (
    echo [ERROR] Python found but cannot run!
    pause
    goto END
)
echo       OK - Python installed

REM ========= 2. Virtual Environment =========
echo.
echo [2/5] Setting up virtual environment...

if not exist "venv" (
    echo       Creating virtual environment...
    python -m venv venv
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to create virtual environment!
        echo Try running: python -m pip install --upgrade pip
        pause
        goto END
    )
    echo       OK - Virtual environment created
) else (
    echo       OK - Virtual environment exists
)

REM Activate venv
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
    echo       OK - Virtual environment activated
) else (
    echo [ERROR] Cannot find venv\Scripts\activate.bat
    echo Try deleting the venv folder and run again.
    pause
    goto END
)

REM ========= 3. Install Dependencies =========
echo.
echo [3/5] Checking dependencies...

if exist "requirements.txt" (
    REM Check if streamlit is installed
    pip show streamlit >nul 2>&1
    if !errorlevel! neq 0 (
        echo       Installing dependencies...
        echo       This may take a few minutes on first run...
        pip install -r requirements.txt
        if !errorlevel! neq 0 (
            echo.
            echo [ERROR] Failed to install dependencies!
            echo.
            echo Try these solutions:
            echo 1. Check internet connection
            echo 2. Use a mirror: pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
            echo 3. Install manually: pip install streamlit plotly pandas psutil pywin32 uiautomation pynput pystray Pillow openai
            echo.
            pause
            goto END
        )
        echo       OK - Dependencies installed
    ) else (
        echo       OK - Dependencies ready
    )
) else (
    echo [WARNING] requirements.txt not found
    echo Creating minimal requirements...
    (
        echo streamlit
        echo plotly
        echo pandas
        echo psutil
        echo pywin32
        echo uiautomation
        echo pynput
        echo pystray
        echo Pillow
        echo openai
    ) > requirements.txt
    pip install -r requirements.txt
)

REM ========= 4. Check Config =========
echo.
echo [4/5] Checking configuration...

if not exist "config.json" (
    echo       Creating default config file...
    (
        echo {
        echo     "api_key": "",
        echo     "base_url": "https://api-inference.modelscope.cn/v1/",
        echo     "model": "Qwen/Qwen2.5-72B-Instruct",
        echo     "check_interval": 30,
        echo     "batch_size": 5,
        echo     "idle_timeout": 300,
        echo     "ai_retry_times": 3,
        echo     "ai_retry_delay": 5,
        echo     "browser_processes": ["chrome.exe", "msedge.exe", "firefox.exe"]
        echo }
    ) > config.json
    echo.
    echo ==========================================
    echo  [IMPORTANT] Please configure API Key!
    echo ==========================================
    echo.
    echo  1. Open config.json
    echo  2. Fill in your API Key
    echo  3. Save and run this script again
    echo.
    notepad config.json
    pause
    goto END
)

REM Check if API Key is empty
findstr /c:"\"api_key\": \"\"" config.json >nul 2>&1
if !errorlevel! equ 0 (
    echo.
    echo [NOTE] API Key not configured!
    echo Please edit config.json and add your API key.
    echo.
    notepad config.json
    pause
    goto END
)
echo       OK - Config file valid

REM ========= 5. Check for data issues =========
echo.
echo [5/6] Checking data files...

if exist "logs\*.csv" (
    echo       Found existing CSV files.
    echo       If you see errors, run: python fix_csv.py
)

REM ========= 6. Start Program =========
echo.
echo [6/6] Starting system...
echo.
echo ==========================================
echo  System starting...
echo ==========================================
echo.
echo  - System tray icon will appear
echo  - Double-click tray icon to open dashboard
echo  - Right-click tray icon for more options
echo.
echo  WebUI URL: http://localhost:8502
echo.
echo ------------------------------------------
echo.

REM Check if launcher.py exists
if not exist "launcher.py" (
    echo [ERROR] launcher.py not found!
    pause
    goto END
)

REM Start main program
python launcher.py

REM If we get here, program exited
echo.
echo ------------------------------------------
echo Program exited.
echo.

if !errorlevel! neq 0 (
    echo [ERROR] Program exited with error code: !errorlevel!
    echo.
    echo Troubleshooting:
    echo 1. Is port 8502 already in use?
    echo    Run: netstat -ano | findstr 8502
    echo 2. Check logs\runtime.log for details
    echo 3. Try running directly: python tracker.py
    echo.
)

:END
echo.
echo Press any key to exit...
pause >nul
