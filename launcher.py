# launcher.py - 改进版
# 新增：更好的错误处理、状态监控、自动重启

import pystray
from PIL import Image, ImageDraw, ImageFont
import subprocess
import sys
import os
import threading
import time
import webbrowser
import ctypes

# 配置
WEBUI_PORT = 8502
AUTO_RESTART = True  # 是否自动重启崩溃的服务
RESTART_DELAY = 5    # 重启延迟（秒）


def hide_console():
    """隐藏控制台窗口 (Windows)"""
    if sys.platform == "win32":
        try:
            ctypes.windll.user32.ShowWindow(
                ctypes.windll.kernel32.GetConsoleWindow(), 0
            )
        except:
            pass


class SystemTrayApp:
    def __init__(self):
        self.tracker_process = None
        self.webui_process = None
        self.icon = None
        self.running = True
        self.monitor_thread = None
        self.status = "启动中..."

    def create_icon(self, status="normal"):
        """创建系统托盘图标"""
        width, height = 64, 64
        
        # 根据状态选择颜色
        colors = {
            "normal": ("#4B8BBE", "#FFD43B"),    # 蓝黄 - Python风格
            "warning": ("#FFA500", "#FFD43B"),   # 橙黄 - 警告
            "error": ("#FF4444", "#FFD43B"),     # 红黄 - 错误
        }
        color1, color2 = colors.get(status, colors["normal"])
        
        image = Image.new('RGB', (width, height), color1)
        dc = ImageDraw.Draw(image)
        
        # 时钟外圈
        dc.ellipse((8, 8, 56, 56), fill=color2, outline=color1, width=2)
        
        # 时针
        dc.rectangle((30, 16, 34, 32), fill=color1)
        # 分针
        dc.rectangle((30, 30, 46, 34), fill=color1)
        
        # 中心点
        dc.ellipse((28, 28, 36, 36), fill=color1)
        
        return image

    def start_tracker(self):
        """启动 Tracker 进程"""
        kwargs = {}
        if sys.platform == "win32":
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW

        try:
            self.tracker_process = subprocess.Popen(
                [sys.executable, "tracker.py"],
                cwd=os.getcwd(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                **kwargs
            )
            print(f"✅ Tracker 已启动 (PID: {self.tracker_process.pid})")
            return True
        except Exception as e:
            print(f"❌ Tracker 启动失败: {e}")
            return False

    def start_webui(self):
        """启动 WebUI 进程"""
        kwargs = {}
        if sys.platform == "win32":
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW

        cmd = [
            sys.executable, "-m", "streamlit", "run", "webui.py",
            f"--server.port={WEBUI_PORT}",
            "--server.headless=true",
            "--browser.gatherUsageStats=false"
        ]

        try:
            self.webui_process = subprocess.Popen(
                cmd,
                cwd=os.getcwd(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                **kwargs
            )
            print(f"✅ WebUI 已启动 (Port: {WEBUI_PORT})")
            return True
        except Exception as e:
            print(f"❌ WebUI 启动失败: {e}")
            return False

    def start_services(self):
        """启动所有服务"""
        print("🚀 正在启动 AI 时间追踪系统...")
        self.status = "正在启动..."
        
        tracker_ok = self.start_tracker()
        webui_ok = self.start_webui()
        
        if tracker_ok and webui_ok:
            self.status = "运行中"
            self.update_icon("normal")
        elif tracker_ok or webui_ok:
            self.status = "部分运行"
            self.update_icon("warning")
        else:
            self.status = "启动失败"
            self.update_icon("error")

    def stop_services(self):
        """停止所有服务"""
        print("🛑 正在停止服务...")
        
        if self.tracker_process:
            try:
                self.tracker_process.terminate()
                self.tracker_process.wait(timeout=5)
            except:
                self.tracker_process.kill()
            self.tracker_process = None
        
        if self.webui_process:
            try:
                self.webui_process.terminate()
                self.webui_process.wait(timeout=5)
            except:
                self.webui_process.kill()
            self.webui_process = None
        
        self.status = "已停止"
        print("✅ 服务已停止")

    def check_process_alive(self, process):
        """检查进程是否存活"""
        if process is None:
            return False
        return process.poll() is None

    def monitor_services(self):
        """监控服务状态，自动重启"""
        while self.running:
            time.sleep(10)  # 每10秒检查一次
            
            if not self.running:
                break
            
            tracker_alive = self.check_process_alive(self.tracker_process)
            webui_alive = self.check_process_alive(self.webui_process)
            
            # 更新状态
            if tracker_alive and webui_alive:
                if self.status != "运行中":
                    self.status = "运行中"
                    self.update_icon("normal")
            elif tracker_alive or webui_alive:
                self.status = "部分运行"
                self.update_icon("warning")
            else:
                self.status = "已停止"
                self.update_icon("error")
            
            # 自动重启
            if AUTO_RESTART:
                if not tracker_alive and self.running:
                    print(f"⚠️ Tracker 已停止，{RESTART_DELAY}秒后重启...")
                    time.sleep(RESTART_DELAY)
                    if self.running:
                        self.start_tracker()
                
                if not webui_alive and self.running:
                    print(f"⚠️ WebUI 已停止，{RESTART_DELAY}秒后重启...")
                    time.sleep(RESTART_DELAY)
                    if self.running:
                        self.start_webui()

    def update_icon(self, status):
        """更新图标状态"""
        if self.icon:
            try:
                self.icon.icon = self.create_icon(status)
            except:
                pass

    def restart_services(self, icon=None, item=None):
        """重启服务"""
        print("🔄 正在重启服务...")
        self.stop_services()
        time.sleep(2)
        self.start_services()
        if icon:
            icon.notify(f"服务已重启 (端口 {WEBUI_PORT})", "AI Tracker")

    def open_webui(self, icon=None, item=None):
        """打开 WebUI"""
        url = f"http://localhost:{WEBUI_PORT}"
        print(f"🌐 打开浏览器: {url}")
        webbrowser.open(url)

    def show_status(self, icon=None, item=None):
        """显示状态通知"""
        tracker_status = "运行中" if self.check_process_alive(self.tracker_process) else "已停止"
        webui_status = "运行中" if self.check_process_alive(self.webui_process) else "已停止"
        
        msg = f"Tracker: {tracker_status}\nWebUI: {webui_status}\n端口: {WEBUI_PORT}"
        if icon:
            icon.notify(msg, "系统状态")

    def on_quit(self, icon=None, item=None):
        """退出程序"""
        print("👋 正在退出...")
        self.running = False
        self.stop_services()
        if icon:
            icon.stop()
        sys.exit(0)

    def run(self):
        """主运行函数"""
        # 启动服务
        self.start_services()
        
        # 启动监控线程
        self.monitor_thread = threading.Thread(target=self.monitor_services, daemon=True)
        self.monitor_thread.start()
        
        # 创建托盘菜单
        menu = pystray.Menu(
            pystray.MenuItem("📊 打开面板", self.open_webui, default=True),
            pystray.MenuItem("ℹ️ 查看状态", self.show_status),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("🔄 重启服务", self.restart_services),
            pystray.MenuItem("❌ 退出系统", self.on_quit)
        )
        
        # 创建图标
        self.icon = pystray.Icon(
            "AI_Tracker",
            self.create_icon(),
            "AI 时间追踪助手",
            menu
        )
        
        # 隐藏控制台
        hide_console()
        
        # 运行（阻塞）
        print("✅ 系统托盘已启动，双击图标打开面板")
        self.icon.run()


if __name__ == "__main__":
    app = SystemTrayApp()
    app.run()
