"""
AI Time Tracker - EXE Build Script
Run: python build_exe.py
"""

import subprocess
import sys
import os

def main():
    print("=" * 50)
    print("  Building AI Time Tracker EXE")
    print("=" * 50)
    print()
    
    # Check PyInstaller
    try:
        import PyInstaller
        print("[OK] PyInstaller found")
    except ImportError:
        print("[...] Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
    
    # Build command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",              # Single EXE file
        "--windowed",             # No console window
        "--name=AI_TimeTracker",  # EXE name
        "--icon=NONE",            # Add icon path if you have one
        "--add-data=config.json;.",
        "--add-data=goals.json;.",
        "--hidden-import=pystray._win32",
        "--hidden-import=PIL._tkinter_finder",
        "--hidden-import=comtypes.stream",
        "launcher.py"
    ]
    
    print("[...] Building EXE (this takes 1-2 minutes)...")
    print()
    
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        print()
        print("=" * 50)
        print("  BUILD SUCCESS!")
        print("=" * 50)
        print()
        print("  EXE location: dist/AI_TimeTracker.exe")
        print()
        print("  To use:")
        print("  1. Copy dist/AI_TimeTracker.exe to project folder")
        print("  2. Make sure config.json is in same folder")
        print("  3. Double-click to run!")
        print()
    else:
        print()
        print("[ERROR] Build failed!")

if __name__ == "__main__":
    main()
