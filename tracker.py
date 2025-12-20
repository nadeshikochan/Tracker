# tracker.py - v3.0 Simplified
# No logging module, just common.log()

import time
import os
import sys
import psutil
import threading
import common
from datetime import datetime, timedelta
import re
import csv

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)

import win32gui
import win32process

common.ensure_dirs()

try:
    from openai import OpenAI
    import uiautomation as auto
    from pynput import mouse, keyboard
except ImportError as e:
    common.log(f"Missing dependency: {e}")
    sys.exit(1)

CONFIG = common.load_config()

DEFAULT_SYSTEM_PROMPT = """
你是一个专业的时间管理助手。根据电脑操作日志对用户行为进行分类。

【日志字段说明】
格式：[开始时间 - 结束时间] <进程名> [活跃度: 低/中/高] [URL: ...] 窗口标题

【9大分类规则】
1. 【开发】: 编写代码, 调试, 查阅技术文档, 终端操作
2. 【AI】: 使用 ChatGPT, Claude, Gemini 等AI工具
3. 【知识库】: 使用 Obsidian, Notion 等笔记软件
4. 【学习】: 观看教学视频, 阅读PDF/电子书
5. 【办公】: 处理文档, 邮件, 会议软件
6. 【社交】: 即时通讯(微信, QQ等)
7. 【娱乐】: 游戏, 娱乐视频, 音乐
8. 【系统】: 文件管理器, 系统设置, 桌面
9. 【休息】: 长时间无操作

【输出要求】
1. 严格CSV格式，无表头，无多余解释
2. 每行：开始时间,结束时间,任务分类,任务详情
3. 时间格式：HH:MM:SS
4. 如果任务详情包含逗号，用双引号包裹

【示例】
19:30:00,20:15:00,开发,VSCode编写Python代码
20:15:00,20:30:00,社交,微信聊天
"""

SYSTEM_PROMPT = CONFIG.get("SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT)


class InputMonitor:
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
            common.log(f"Input monitor failed: {e}")

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


class DataCollector:
    def __init__(self):
        self.process_cache = {}
        self.browser_processes = [p.lower() for p in CONFIG.get("browser_processes",
            ['chrome.exe', 'msedge.exe', 'firefox.exe'])]
        self.last_url_fetch_time = 0
        self.last_url_cache = ""

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
        now = time.time()
        if now - self.last_url_fetch_time < 2:
            return self.last_url_cache

        try:
            window = auto.ControlFromHandle(hwnd)

            if 'firefox' in process_name:
                edit = window.EditControl(searchDepth=8, AutomationId="urlbar-input")
                if not edit.Exists():
                    edit = window.EditControl(searchDepth=6)
            elif 'edge' in process_name:
                edit = window.EditControl(Name="Address and search bar", searchDepth=6)
                if not edit.Exists():
                    edit = window.EditControl(searchDepth=6, foundIndex=1)
            else:
                edit = window.EditControl(searchDepth=6, foundIndex=1)

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


class AsyncAISummarizer:
    def __init__(self):
        self.client = None
        if CONFIG.get("api_key"):
            try:
                self.client = OpenAI(
                    api_key=CONFIG["api_key"],
                    base_url=CONFIG.get("base_url", "https://api.openai.com/v1")
                )
            except Exception as e:
                common.log(f"OpenAI init failed: {e}")

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
        except:
            pass

    def _save_failed(self, log_lines, error_msg):
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        failed_path = os.path.join(common.FAILED_LOG_DIR, f"failed_{timestamp}.txt")
        try:
            with open(failed_path, "w", encoding="utf-8") as f:
                f.write(f"# Error: {error_msg}\n")
                f.write("\n".join(log_lines))
            common.log(f"Failed log saved: {failed_path}")
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
            return None

    def _save_csv(self, csv_content, log_lines):
        clean_text = csv_content.replace("```csv", "").replace("```", "").strip()
        lines = [line for line in clean_text.split('\n') if line.strip() and ',' in line]
        if not lines:
            common.log("AI response empty or invalid format")
            return

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
                common.log(f"AI done: {len(lines)} records -> {date_str}.csv")
            except Exception as e:
                common.log(f"CSV write failed: {e}")

    def process_logs_async(self, log_lines):
        if not log_lines:
            return

        date_str = self._extract_date_from_log(log_lines[0]) if log_lines else None
        self._save_raw(log_lines, date_str)

        if not self.client:
            common.log("No API key, skipping AI")
            return

        def run_ai_task(lines):
            common.log(f"AI request: {len(lines)} logs...")
            user_content = "请分析以下日志并输出CSV格式结果:\n" + "\n".join(lines)

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
                    if attempt < self.retry_times - 1:
                        common.log(f"AI retry {attempt+1}: {e}")
                        time.sleep(self.retry_delay)
                    else:
                        common.log(f"AI failed: {e}")
                        self._save_failed(lines, str(e))

        thread = threading.Thread(target=run_ai_task, args=(log_lines,))
        thread.daemon = True
        thread.start()


class SmartTracker:
    def __init__(self):
        self.collector = DataCollector()
        self.input_monitor = InputMonitor()
        self.ai = AsyncAISummarizer()
        self.log_buffer = []

        self.batch_size = CONFIG.get("batch_size", 5)
        self.check_interval = CONFIG.get("check_interval", 30)
        self.idle_timeout = CONFIG.get("idle_timeout", 300)
        self.sleep_threshold = CONFIG.get("sleep_threshold", 120)

        self.stable_process = ""
        self.stable_title = ""
        self.stable_url = ""
        self.stable_start_time = time.time()

        self.pending_process = None
        self.pending_title = None
        self.pending_url = None
        self.pending_start_time = 0

        self.is_idle = False
        self.idle_start_time = 0
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

        if dt_start.date() != dt_end.date():
            next_day = datetime.combine(dt_start.date() + timedelta(days=1), datetime.min.time())
            midnight_ts = next_day.timestamp()
            common.log(f"Day split: {dt_start.date()} -> {dt_end.date()}")
            self._commit_log(process, title, url, start_ts, midnight_ts, force_idle)
            self._commit_log(process, title, url, midnight_ts, end_ts, force_idle)
            return

        activity_level = "低" if force_idle else self.input_monitor.get_and_reset()
        url_part = f"[URL: {url}]" if url else ""
        log_content = f"<{process}> [活跃度:{activity_level}] {url_part} {title}"
        log_line = f"[{dt_start.strftime('%Y-%m-%d %H:%M:%S')} - {dt_end.strftime('%Y-%m-%d %H:%M:%S')}] {log_content}"

        self.log_buffer.append(log_line)
        common.log(f"Record: {process} ({int(duration)}s) [{activity_level}]")

        if len(self.log_buffer) >= self.batch_size:
            self.flush_buffer()

    def _handle_idle(self):
        idle_duration = self.input_monitor.get_idle_duration()

        if not self.is_idle and idle_duration > self.idle_timeout:
            self.is_idle = True
            self.idle_start_time = time.time() - idle_duration
            common.log(f"Idle start ({int(idle_duration)}s)")
            if self.stable_process:
                self._commit_log(self.stable_process, self.stable_title, self.stable_url,
                               self.stable_start_time, self.idle_start_time)
            return True

        elif self.is_idle and idle_duration < 5:
            common.log("Idle end")
            self._commit_log("idle", "系统空闲", "", self.idle_start_time, time.time(), force_idle=True)
            self.is_idle = False
            self.stable_start_time = time.time()
            return False

        return self.is_idle

    def run(self):
        common.log(f"Tracker started (PID: {os.getpid()})")
        common.log(f"Config: interval={self.check_interval}s, batch={self.batch_size}")

        while not self.stable_title:
            t, p, u = self.collector.get_active_window_info()
            if t:
                self.stable_title = t
                self.stable_process = p
                self.stable_url = u
                self.stable_start_time = time.time()
                common.log(f"Initial: {self.stable_process}")
            time.sleep(1)

        self.last_loop_monotonic = time.monotonic()

        try:
            while True:
                time.sleep(1)

                now_monotonic = time.monotonic()
                loop_gap = now_monotonic - self.last_loop_monotonic

                if loop_gap > self.sleep_threshold:
                    common.log(f"Sleep detected ({int(loop_gap)}s)")
                    self._commit_log(self.stable_process, self.stable_title, self.stable_url,
                                   self.stable_start_time, time.time() - loop_gap)
                    self.input_monitor.reset_counters()
                    t, p, u = self.collector.get_active_window_info()
                    if t:
                        self.stable_title, self.stable_process, self.stable_url = t, p, u
                    self.stable_start_time = time.time()
                    self.pending_process = None
                    self.is_idle = False
                    self.last_loop_monotonic = now_monotonic
                    continue

                self.last_loop_monotonic = now_monotonic

                if self._handle_idle():
                    continue

                raw_title, raw_process, raw_url = self.collector.get_active_window_info()
                if not raw_title:
                    continue

                raw_title = raw_title.strip()

                if raw_process in self.collector.browser_processes and not raw_url:
                    if raw_process == self.stable_process:
                        raw_url = self.stable_url
                    elif raw_process == self.pending_process:
                        raw_url = self.pending_url

                is_stable = self._is_same_task(self.stable_process, self.stable_url, raw_process, raw_url)

                if is_stable:
                    if self.pending_process:
                        common.log(f"Skip short switch: {self.pending_process}")
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
                            if time.time() - self.pending_start_time > self.check_interval:
                                self._commit_log(self.stable_process, self.stable_title, self.stable_url,
                                               self.stable_start_time, self.pending_start_time)
                                common.log(f"Switch: {self.stable_process} -> {self.pending_process}")
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
            common.log("Stopping...")
            if self.stable_process:
                self._commit_log(self.stable_process, self.stable_title, self.stable_url,
                               self.stable_start_time, time.time())
            self.flush_buffer()
            common.log("Tracker stopped")


if __name__ == "__main__":
    import socket
    try:
        lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        lock_socket.bind(('127.0.0.1', 47832))
    except socket.error:
        common.log("Tracker already running")
        sys.exit(1)

    tracker = SmartTracker()
    tracker.run()
