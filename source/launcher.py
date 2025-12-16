
import pystray
from PIL import Image, ImageDraw
import subprocess
import sys
import os
import threading
import time
import webbrowser
import ctypes

# 配置端口号
WEBUI_PORT = 8502


# 隐藏控制台窗口 (Windows)
def hide_console():
    if sys.platform == "win32":
        try:
            ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
        except Exception:
            pass


class SystemTrayApp:
    def __init__(self):
        self.tracker_process = None
        self.webui_process = None
        self.icon = None
        self.running = True

    def create_icon(self):
        """创建一个简单的图标"""
        width = 64
        height = 64
        color1 = "#4B8BBE"  # Python Blue
        color2 = "#FFD43B"  # Python Yellow

        image = Image.new('RGB', (width, height), color1)
        dc = ImageDraw.Draw(image)

        # 画一个简单的时间样式（圆圈）
        dc.ellipse((10, 10, 54, 54), fill=color2)

        # 时针 (修正坐标顺序)
        dc.rectangle((28, 15, 36, 32), fill=color1)

        # 分针 (横向)
        dc.rectangle((28, 28, 48, 36), fill=color1)

        return image

    def start_services(self):
        """启动后台服务"""
        print("🚀 正在启动 AI 时间追踪系统...")

        # 1. 启动 Tracker
        kwargs = {}
        if sys.platform == "win32":
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW

        self.tracker_process = subprocess.Popen(
            [sys.executable, "tracker.py"],
            cwd=os.getcwd(),
            **kwargs
        )
        print(f"✅ Tracker 已启动 (PID: {self.tracker_process.pid})")

        # 2. 启动 WebUI (强制指定端口)
        cmd = [
            sys.executable, "-m", "streamlit", "run", "webui.py",
            f"--server.port={WEBUI_PORT}",  # <--- 强制端口
            "--server.headless=true"
        ]

        self.webui_process = subprocess.Popen(
            cmd,
            cwd=os.getcwd(),
            **kwargs
        )
        print(f"✅ WebUI 已启动 (Port: {WEBUI_PORT})")

    def stop_services(self):
        """停止所有服务"""
        if self.tracker_process:
            self.tracker_process.terminate()
            self.tracker_process = None
        if self.webui_process:
            self.webui_process.terminate()
            self.webui_process = None
        print("🛑 服务已停止")

    def restart_services(self, icon, item):
        self.stop_services()
        time.sleep(1)
        self.start_services()
        icon.notify(f"服务已重启 (端口 {WEBUI_PORT})", "AI Tracker")

    def open_webui(self, icon, item):
        """打开浏览器"""
        # <--- 打开对应的端口
        webbrowser.open(f"http://localhost:{WEBUI_PORT}")

    def on_quit(self, icon, item):
        """退出程序"""
        self.running = False
        self.stop_services()
        icon.stop()
        sys.exit(0)

    def run(self):
        # 1. 启动服务
        self.start_services()

        # 2. 创建托盘菜单
        menu = pystray.Menu(
            pystray.MenuItem("打开面板 (WebUI)", self.open_webui, default=True),
            pystray.MenuItem("重启服务", self.restart_services),
            pystray.MenuItem("退出系统", self.on_quit)
        )

        # 3. 设置图标并运行
        self.icon = pystray.Icon("AI_Tracker", self.create_icon(), "AI 时间追踪助手", menu)

        # 4. 隐藏控制台
        hide_console()

        # 阻塞运行托盘
        self.icon.run()


if __name__ == "__main__":
    app = SystemTrayApp()
    app.run()
