# tracker.py - 修复版 v2.2
# 修复：休眠误判、工作目录、重复日志问题

import time
import os
import sys
import psutil
import threading
import common
from datetime import datetime, timedelta
import re
import csv

# ==========================================
# 【修复】确保工作目录正确
# ==========================================
# 获取脚本所在目录（不是当前工作目录）
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)  # 切换到脚本目录

# Windows 特定导入
import win32gui
import win32process

# ==========================================
# 1. 环境初始化
# ==========================================
common.ensure_dirs()
logger = common.setup_logging()

try:
    from openai import OpenAI
    import uiautomation as auto
    from pynput import mouse, keyboard
except ImportError as e:
    logger.error(f"缺少依赖库: {e}")
    logger.error("请运行: pip install openai psutil pywin32 uiautomation pynput pystray Pillow")
    sys.exit(1)

CONFIG = common.load_config()

# ==========================================
# 2. AI 提示词
# ==========================================
SYSTEM_PROMPT=CONFIG.get("SYSTEM_PROMPT")


# ==========================================
# 3. 活跃度监听器
# ==========================================
class InputMonitor:
    """后台监听鼠标点击和键盘敲击"""

    def __init__(self):
        self.click_count = 0
        self.key_count = 0
        self.lock = threading.Lock()
        self.last_activity_time = time.time()

        try:
            self.mouse_listener = mouse.Listener(on_click=self._on_click, on_move=self._on_move)
            self.key_listener = keyboard.Listener(on_release=self._on_key)
            self.mouse_listener.start()
            self.key_listener.start()
        except Exception as e:
            logger.error(f"输入监听启动失败: {e}")

    def _on_click(self, x, y, button, pressed):
        if pressed:
            with self.lock:
                self.click_count += 1
                self.last_activity_time = time.time()

    def _on_move(self, x, y):
        with self.lock:
            self.last_activity_time = time.time()

    def _on_key(self, key):
        with self.lock:
            self.key_count += 1
            self.last_activity_time = time.time()

    def get_and_reset(self):
        with self.lock:
            total = self.click_count + self.key_count
            self.click_count = 0
            self.key_count = 0

        if total < 5:
            return "低"
        if total < 50:
            return "中"
        return "高"

    def reset_counters(self):
        with self.lock:
            self.click_count = 0
            self.key_count = 0

    def get_idle_duration(self):
        with self.lock:
            return time.time() - self.last_activity_time


# ==========================================
# 4. 数据采集器
# ==========================================
class DataCollector:
    """获取当前前台窗口信息"""

    def __init__(self):
        self.process_cache = {}
        self.browser_processes = [p.lower() for p in CONFIG.get("browser_processes", 
            ['chrome.exe', 'msedge.exe', 'firefox.exe', 'opera.exe', 'brave.exe'])]
        # 【优化】缓存上次URL获取时间，避免频繁调用
        self.last_url_fetch_time = 0
        self.last_url_cache = ""
        self.url_cache_duration = 2  # URL缓存2秒

    def get_process_name(self, pid):
        if pid in self.process_cache:
            return self.process_cache[pid]
        try:
            p = psutil.Process(pid)
            name = p.name().lower()
            self.process_cache[pid] = name
            return name
        except:
            return "unknown"

    def get_browser_url(self, hwnd, process_name):
        """获取浏览器地址栏URL（带缓存）"""
        # 【优化】URL获取很耗时，添加缓存
        now = time.time()
        if now - self.last_url_fetch_time < self.url_cache_duration:
            return self.last_url_cache
        
        try:
            window = auto.ControlFromHandle(hwnd)
            
            if 'firefox' in process_name:
                edit = window.EditControl(searchDepth=10, AutomationId="urlbar-input")
                if not edit.Exists():
                    edit = window.EditControl(searchDepth=8)
            elif 'edge' in process_name:
                edit = window.EditControl(Name="Address and search bar", searchDepth=8)
                if not edit.Exists():
                    edit = window.EditControl(searchDepth=8, foundIndex=1)
            else:
                edit = window.EditControl(searchDepth=8, foundIndex=1)

            if edit.Exists():
                try:
                    url = edit.GetValuePattern().Value
                    self.last_url_cache = url
                    self.last_url_fetch_time = now
                    return url
                except:
                    pass
        except:
            pass
        
        self.last_url_fetch_time = now
        return ""

    def get_active_window_info(self):
        """获取当前前台窗口信息"""
        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return None, None, None

            title = win32gui.GetWindowText(hwnd)
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            process = self.get_process_name(pid)

            url = ""
            if process in self.browser_processes and title:
                url = self.get_browser_url(hwnd, process)

            return title, process, url
        except:
            return None, None, None


# ==========================================
# 5. AI 总结器
# ==========================================
class AsyncAISummarizer:
    """AI日志分析器"""

    def __init__(self):
        self.client = None
        if CONFIG.get("api_key"):
            try:
                self.client = OpenAI(
                    api_key=CONFIG["api_key"],
                    base_url=CONFIG.get("base_url", "https://api.openai.com/v1")
                )
            except Exception as e:
                logger.error(f"OpenAI客户端初始化失败: {e}")
        
        self.lock = threading.Lock()
        self.retry_times = CONFIG.get("ai_retry_times", 3)
        self.retry_delay = CONFIG.get("ai_retry_delay", 5)

    def _save_raw(self, log_lines, date_str=None):
        if date_str is None:
            date_str = common.get_today_str()
        raw_path = os.path.join(common.RAW_LOG_DIR, f"{date_str}_raw.txt")
        try:
            with open(raw_path, "a", encoding="utf-8") as f:
                f.write("\n".join(log_lines) + "\n")
        except Exception as e:
            logger.error(f"Raw日志保存失败: {e}")

    def _save_failed(self, log_lines, error_msg):
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        failed_path = os.path.join(common.FAILED_LOG_DIR, f"failed_{timestamp}.txt")
        try:
            with open(failed_path, "w", encoding="utf-8") as f:
                f.write(f"# 失败时间: {datetime.now()}\n")
                f.write(f"# 错误信息: {error_msg}\n")
                f.write("# 原始日志:\n")
                f.write("\n".join(log_lines))
            logger.warning(f"⚠️ 失败日志已保存到: {failed_path}")
        except:
            pass

    def _extract_date_from_log(self, log_line):
        match = re.search(r'\[(\d{4}-\d{2}-\d{2})', log_line)
        if match:
            return match.group(1)
        return common.get_today_str()

    def _parse_csv_line(self, line):
        try:
            reader = csv.reader([line])
            for row in reader:
                if len(row) >= 4:
                    return row[:4]
                elif len(row) == 3:
                    return row + ['']
            return None
        except:
            parts = line.split(',')
            if len(parts) >= 4:
                return [parts[0], parts[1], parts[2], ','.join(parts[3:])]
            elif len(parts) == 3:
                return parts + ['']
            return None

    def _save_csv(self, csv_content, log_lines):
        clean_text = csv_content.replace("```csv", "").replace("```", "").strip()
        lines = [line for line in clean_text.split('\n') if line.strip() and ',' in line]
        if not lines:
            logger.warning("AI返回内容为空或格式错误")
            return

        dates_in_logs = set()
        for log in log_lines:
            date_str = self._extract_date_from_log(log)
            dates_in_logs.add(date_str)

        if len(dates_in_logs) == 1:
            date_str = dates_in_logs.pop()
            self._write_to_csv(date_str, lines)
        else:
            date_str = self._extract_date_from_log(log_lines[0]) if log_lines else common.get_today_str()
            self._write_to_csv(date_str, lines)

    def _write_to_csv(self, date_str, lines):
        file_path = os.path.join(common.LOG_DIR, f"{date_str}.csv")
        
        with self.lock:
            new_file = not os.path.exists(file_path)
            try:
                with open(file_path, "a", encoding="utf-8-sig", newline="") as f:
                    writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
                    
                    if new_file:
                        writer.writerow(['开始时间', '结束时间', '任务分类', '任务详情'])
                    
                    for line in lines:
                        parsed = self._parse_csv_line(line)
                        if parsed:
                            writer.writerow(parsed)
                
                logger.info(f"✅ AI分析完成: 写入 {len(lines)} 条记录到 {date_str}.csv")
            except Exception as e:
                logger.error(f"❌ CSV写入失败: {e}")

    def process_logs_async(self, log_lines):
        if not log_lines:
            return

        date_str = self._extract_date_from_log(log_lines[0]) if log_lines else None
        self._save_raw(log_lines, date_str)

        if not self.client:
            logger.warning("⚠️ 未配置API Key，跳过AI分析")
            return

        def run_ai_task(lines):
            logger.info(f"🔄 请求AI分析 {len(lines)} 条日志...")
            user_content = "请分析以下日志并输出CSV格式结果:\n" + "\n".join(lines)
            
            last_error = None
            for attempt in range(self.retry_times):
                try:
                    response = self.client.chat.completions.create(
                        model=CONFIG["model"],
                        messages=[
                            {'role': 'system', 'content': SYSTEM_PROMPT},
                            {'role': 'user', 'content': user_content}
                        ],
                        temperature=0.3,
                        stream=False
                    )
                    self._save_csv(response.choices[0].message.content, lines)
                    return
                except Exception as e:
                    last_error = str(e)
                    if attempt < self.retry_times - 1:
                        logger.warning(f"⚠️ AI请求失败(尝试 {attempt+1}/{self.retry_times}): {e}")
                        time.sleep(self.retry_delay)
                    else:
                        logger.error(f"❌ AI请求最终失败: {e}")
                        self._save_failed(lines, last_error)

        thread = threading.Thread(target=run_ai_task, args=(log_lines,))
        thread.daemon = True
        thread.start()


# ==========================================
# 6. 智能追踪器
# ==========================================
class SmartTracker:
    """主追踪器"""

    def __init__(self):
        self.collector = DataCollector()
        self.input_monitor = InputMonitor()
        self.ai = AsyncAISummarizer()
        self.log_buffer = []

        self.batch_size = CONFIG.get("batch_size", 5)
        self.check_interval = CONFIG.get("check_interval", 30)
        self.idle_timeout = CONFIG.get("idle_timeout", 300)
        
        # 【关键修复】休眠检测阈值
        # 原来是5秒太短了，改为120秒（2分钟）
        # 只有真正的系统休眠/睡眠才会超过这个时间
        self.sleep_threshold = CONFIG.get("sleep_threshold", 120)

        # 稳定态
        self.stable_process = ""
        self.stable_title = ""
        self.stable_url = ""
        self.stable_start_time = time.time()

        # 待定态
        self.pending_process = None
        self.pending_title = None
        self.pending_url = None
        self.pending_start_time = 0

        # 空闲状态
        self.is_idle = False
        self.idle_start_time = 0

        # 【修复】使用单调时钟而不是wall clock
        # time.monotonic() 不受系统时间调整影响，更适合测量时间间隔
        self.last_loop_monotonic = time.monotonic()

    def flush_buffer(self):
        if not self.log_buffer:
            return
        logs = self.log_buffer[:]
        self.log_buffer = []
        self.ai.process_logs_async(logs)

    def _is_same_task(self, proc1, url1, proc2, url2):
        if proc1 != proc2:
            return False
        if proc1 in self.collector.browser_processes:
            if url1 and url2 and url1 != url2:
                return False
        return True

    def _commit_log(self, process, title, url, start_ts, end_ts, force_idle=False):
        duration = end_ts - start_ts
        if duration < 2:
            return

        dt_start = datetime.fromtimestamp(start_ts)
        dt_end = datetime.fromtimestamp(end_ts)

        # 跨天检测
        if dt_start.date() != dt_end.date():
            next_day = datetime.combine(dt_start.date() + timedelta(days=1), datetime.min.time())
            midnight_ts = next_day.timestamp()
            print(f"✂️ 跨天切割: {dt_start.date()} -> {dt_end.date()}")
            self._commit_log(process, title, url, start_ts, midnight_ts, force_idle)
            self._commit_log(process, title, url, midnight_ts, end_ts, force_idle)
            return

        activity_level = "低" if force_idle else self.input_monitor.get_and_reset()
        
        url_part = f"[URL: {url}]" if url else ""
        log_content = f"<{process}> [活跃度:{activity_level}] {url_part} {title}"
        log_line = f"[{dt_start.strftime('%Y-%m-%d %H:%M:%S')} - {dt_end.strftime('%Y-%m-%d %H:%M:%S')}] {log_content}"

        self.log_buffer.append(log_line)
        print(f"📝 记录: {process} ({int(duration)}s) [{activity_level}]")

        if len(self.log_buffer) >= self.batch_size:
            self.flush_buffer()

    def _handle_idle(self):
        idle_duration = self.input_monitor.get_idle_duration()
        
        if not self.is_idle and idle_duration > self.idle_timeout:
            self.is_idle = True
            self.idle_start_time = time.time() - idle_duration
            print(f"💤 进入空闲状态 (无操作 {int(idle_duration)}s)")
            
            if self.stable_process:
                self._commit_log(
                    self.stable_process, self.stable_title, self.stable_url,
                    self.stable_start_time, self.idle_start_time
                )
            return True

        elif self.is_idle and idle_duration < 5:
            print(f"⏰ 退出空闲状态")
            self._commit_log(
                "idle", "系统空闲", "",
                self.idle_start_time, time.time(), force_idle=True
            )
            self.is_idle = False
            self.stable_start_time = time.time()
            return False

        return self.is_idle

    def run(self):
        """主运行循环"""
        logger.info(f"🚀 Tracker 启动 (PID: {os.getpid()})")
        logger.info(f"📂 工作目录: {os.getcwd()}")
        logger.info(f"⚙️ 配置: 防抖={self.check_interval}s, 批量={self.batch_size}, 休眠阈值={self.sleep_threshold}s")

        # 初始化
        while not self.stable_title:
            t, p, u = self.collector.get_active_window_info()
            if t:
                self.stable_title = t
                self.stable_process = p
                self.stable_url = u
                self.stable_start_time = time.time()
                print(f"✅ 初始任务: {self.stable_process}")
            time.sleep(1)

        self.last_loop_monotonic = time.monotonic()

        try:
            while True:
                time.sleep(1)
                
                # 【关键修复】使用 monotonic 时钟计算间隔
                now_monotonic = time.monotonic()
                loop_gap = now_monotonic - self.last_loop_monotonic
                
                # 【修复】只有真正长时间中断才认为是休眠
                # 正常循环即使慢也不会超过120秒
                if loop_gap > self.sleep_threshold:
                    print(f"💤 检测到系统休眠 (中断 {int(loop_gap)}s)")
                    self._commit_log(
                        self.stable_process, self.stable_title, self.stable_url,
                        self.stable_start_time, time.time() - loop_gap
                    )
                    self.input_monitor.reset_counters()
                    t, p, u = self.collector.get_active_window_info()
                    if t:
                        self.stable_title = t
                        self.stable_process = p
                        self.stable_url = u
                    self.stable_start_time = time.time()
                    self.pending_process = None
                    self.is_idle = False
                    self.last_loop_monotonic = now_monotonic
                    continue

                self.last_loop_monotonic = now_monotonic

                # 空闲检测
                if self._handle_idle():
                    continue

                # 获取当前窗口
                raw_title, raw_process, raw_url = self.collector.get_active_window_info()
                if not raw_title:
                    continue

                raw_title = raw_title.strip()

                # URL容错
                if raw_process in self.collector.browser_processes and not raw_url:
                    if raw_process == self.stable_process:
                        raw_url = self.stable_url
                    elif raw_process == self.pending_process:
                        raw_url = self.pending_url

                # 状态机逻辑
                is_stable = self._is_same_task(self.stable_process, self.stable_url, raw_process, raw_url)

                if is_stable:
                    if self.pending_process:
                        duration = time.time() - self.pending_start_time
                        print(f"↩️ 忽略短暂切换: {self.pending_process} ({int(duration)}s)")
                        self.pending_process = None
                    self.stable_title = raw_title
                    if raw_url:
                        self.stable_url = raw_url
                else:
                    if not self.pending_process:
                        self.pending_process = raw_process
                        self.pending_title = raw_title
                        self.pending_url = raw_url
                        self.pending_start_time = time.time()
                    else:
                        if self._is_same_task(self.pending_process, self.pending_url, raw_process, raw_url):
                            pending_duration = time.time() - self.pending_start_time
                            if pending_duration > self.check_interval:
                                self._commit_log(
                                    self.stable_process, self.stable_title, self.stable_url,
                                    self.stable_start_time, self.pending_start_time
                                )
                                print(f"👉 确认切换: {self.stable_process} -> {self.pending_process}")
                                self.stable_process = self.pending_process
                                self.stable_title = self.pending_title
                                self.stable_url = self.pending_url
                                self.stable_start_time = self.pending_start_time
                                self.pending_process = None
                        else:
                            self.pending_process = raw_process
                            self.pending_title = raw_title
                            self.pending_url = raw_url
                            self.pending_start_time = time.time()

        except KeyboardInterrupt:
            print("\n🛑 收到退出信号...")
            if self.stable_process:
                self._commit_log(
                    self.stable_process, self.stable_title, self.stable_url,
                    self.stable_start_time, time.time()
                )
            self.flush_buffer()
            logger.info("Tracker 已安全退出")


# ==========================================
# 7. 入口
# ==========================================
if __name__ == "__main__":
    # 【修复】防止重复启动
    import socket
    lock_socket = None
    try:
        lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        lock_socket.bind(('127.0.0.1', 47832))  # 用一个固定端口作为锁
    except socket.error:
        print("⚠️ Tracker 已在运行中，退出...")
        sys.exit(1)
    
    tracker = SmartTracker()
    tracker.run()
