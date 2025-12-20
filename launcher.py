# launcher.py - v3.0
# Main program runs silently, optional log window

import subprocess
import sys
import os
import threading
import time
import webbrowser
import signal

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)

WEBUI_PORT = 8502

# Globals
tracker_proc = None
webui_proc = None
log_proc = None
running = True


def start_tracker():
    global tracker_proc
    try:
        tracker_proc = subprocess.Popen(
            [sys.executable, "tracker.py"],
            cwd=SCRIPT_DIR,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )
        return True
    except Exception as e:
        print(f"Tracker start failed: {e}")
        return False


def start_webui():
    global webui_proc
    try:
        cmd = [
            sys.executable, "-m", "streamlit", "run", "webui.py",
            f"--server.port={WEBUI_PORT}",
            "--server.headless=true",
            "--browser.gatherUsageStats=false",
        ]
        webui_proc = subprocess.Popen(
            cmd,
            cwd=SCRIPT_DIR,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )
        return True
    except Exception as e:
        print(f"WebUI start failed: {e}")
        return False


def open_log_window():
    """Open a separate terminal to tail the log file (UTF-8 encoding for Chinese)"""
    global log_proc
    log_path = os.path.join(SCRIPT_DIR, "logs", "runtime.log")
    
    if sys.platform == "win32":
        # 使用 PowerShell 并设置 UTF-8 编码以正确显示中文
        cmd = f'start powershell -NoExit -Command "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; Get-Content -Path \'{log_path}\' -Wait -Tail 50 -Encoding UTF8"'
        os.system(cmd)
    else:
        # Linux/Mac
        os.system(f'gnome-terminal -- tail -f "{log_path}" &')


def stop_all():
    global tracker_proc, webui_proc, running
    running = False
    
    for proc in [tracker_proc, webui_proc]:
        if proc:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except:
                try:
                    proc.kill()
                except:
                    pass


def monitor():
    global running
    while running:
        time.sleep(10)
        
        if tracker_proc and tracker_proc.poll() is not None:
            if running:
                start_tracker()
        
        if webui_proc and webui_proc.poll() is not None:
            if running:
                start_webui()


def main_with_tray():
    """Run with system tray icon"""
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        print("pystray/Pillow not installed, running without tray")
        main_simple()
        return
    
    def create_icon():
        img = Image.new('RGB', (64, 64), '#4B8BBE')
        d = ImageDraw.Draw(img)
        d.ellipse((8, 8, 56, 56), fill='#FFD43B')
        return img
    
    def on_open(icon, item):
        webbrowser.open(f"http://localhost:{WEBUI_PORT}")
    
    def on_log(icon, item):
        open_log_window()
    
    def on_quit(icon, item):
        stop_all()
        icon.stop()
        os._exit(0)
    
    # Start services
    start_tracker()
    start_webui()
    
    # Start monitor thread
    t = threading.Thread(target=monitor, daemon=True)
    t.start()
    
    # Create tray
    menu = pystray.Menu(
        pystray.MenuItem("Open Dashboard", on_open, default=True),
        pystray.MenuItem("View Log", on_log),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Exit", on_quit)
    )
    
    icon = pystray.Icon("TimeTracker", create_icon(), "AI Time Tracker", menu)
    icon.run()


def main_simple():
    """Run without tray - just start services"""
    start_tracker()
    start_webui()
    
    print(f"Services started!")
    print(f"WebUI: http://localhost:{WEBUI_PORT}")
    print("Press Ctrl+C to stop")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop_all()


if __name__ == "__main__":
    main_with_tray()
