
# tracker.py
import time
import os
import psutil
import threading
import common
from datetime import datetime
# win32gui 和 win32process 用于获取 Windows 窗口句柄和进程ID
import win32gui
import win32process

# ==========================================
# 1. 环境初始化与依赖检查
# ==========================================

# 确保日志和数据目录存在
common.ensure_dirs()
# 设置日志系统（这里不仅配置了 logger，还可能重定向了 stdout/stderr 以便 WebUI 读取）
logger = common.setup_logging()

# 尝试导入核心功能依赖库
try:
    from openai import OpenAI, AuthenticationError  # 用于调用 AI 模型进行日志总结
    import uiautomation as auto  # 用于获取浏览器地址栏 URL (UI 自动化)
    from pynput import mouse, keyboard  # 用于监听全局鼠标和键盘事件
except ImportError:
    # 如果缺少依赖，记录错误但不立即崩溃，防止 Launcher 误判为 Crash
    logger.error("缺少依赖库，请运行: pip install openai psutil pywin32 uiautomation pynput pystray Pillow")
    pass

# 加载配置文件 (config.json 或类似文件)
CONFIG = common.load_config()

# ==========================================
# 2. AI 提示词 (System Prompt)
# ==========================================
# 这是发送给 LLM (如 ChatGPT/Gemini) 的核心指令，定义了如何将原始日志转化为结构化数据
SYSTEM_PROMPT = """
你是一个专业的时间管理助手。根据电脑操作日志对用户行为进行分类。

【日志字段说明】
格式：[时间段] <进程名> [活跃度: 低/中/高] [URL: ...] 窗口标题
- **活跃度**：反映用户键鼠操作频率。
- **URL**：如果是浏览器，会提供当前网页链接。

【8大分类规则】
1. 【开发】: 编写代码(PyCharm等), 调试, 查阅技术文档( GitHub), 终端操作。
2. 【AI】: 使用 ChatGPT, gemimi等。
3. 【知识库】: 使用 Obsidian, Notion, 等笔记软件整理知识。
4. 【学习】: 观看教学视频(bilibli网课), 阅读PDF书籍, 查阅百科资料、问AI有关学习的问题。
5. 【办公】: 处理文档(Word, Excel, PPT)而且是编辑文档、不是学习文档 。
6. 【社交】: 即时通讯(微信, QQ, Telegram, )。
7. 【娱乐】: 玩游戏(Steam, 各种游戏), 看娱乐视频(B站动画, 抖音), 听音乐, 浏览非技术类网页。
8. 【系统】: 文件资源管理器, 系统设置, 锁屏, 桌面待机。

【输出要求】
1. 严格CSV格式，无表头。
2. 每一行：开始时间,结束时间,任务分类,任务详情（包含原始的概括和你的解释）
"""


# ==========================================
# 3. 活跃度监听器 (InputMonitor)
# ==========================================
class InputMonitor:
    """
    后台监听鼠标点击和键盘敲击次数，用于判断用户当前的活跃程度。
    """

    def __init__(self):
        self.click_count = 0
        self.key_count = 0
        self.lock = threading.Lock()  # 线程锁，防止数据竞争

        try:
            # 启动非阻塞的监听线程
            self.mouse_listener = mouse.Listener(on_click=self._on_click)
            self.key_listener = keyboard.Listener(on_release=self._on_key)
            self.mouse_listener.start()
            self.key_listener.start()
        except Exception as e:
            logger.error(f"输入监听启动失败: {e}")

    def _on_click(self, x, y, button, pressed):
        """鼠标点击回调"""
        if pressed:
            with self.lock: self.click_count += 1

    def _on_key(self, key):
        """键盘按键回调"""
        with self.lock: self.key_count += 1

    def get_and_reset(self):
        """
        获取当前时间段内的总操作数，并重置计数器。
        返回：'低', '中', '高'
        """
        with self.lock:
            total = self.click_count + self.key_count
            self.click_count = 0
            self.key_count = 0

        # 根据操作频次定义活跃度阈值 (这里是基于采集周期的，例如每几秒采集一次)
        if total < 5: return "低"
        if total < 50: return "中"
        return "高"


# ==========================================
# 4. 数据采集器 (DataCollector)
# ==========================================
class DataCollector:
    """
    负责获取当前前台窗口的信息，包括标题、进程名以及浏览器 URL。
    """

    def __init__(self):
        self.process_cache = {}  # 缓存 PID -> 进程名，减少系统调用开销
        self.browser_processes = ['chrome.exe', 'msedge.exe']  # 需要特殊处理 URL 的浏览器进程

    def get_process_name(self, pid):
        """根据 PID 获取进程名，带缓存机制"""
        if pid in self.process_cache: return self.process_cache[pid]
        try:
            p = psutil.Process(pid)
            name = p.name().lower()
            self.process_cache[pid] = name
            return name
        except:
            return "Unknown"

    def get_browser_url(self, hwnd):
        """
        利用 UI Automation 技术获取浏览器地址栏的 URL。
        这是一个耗时操作，仅在检测到是浏览器窗口时调用。
        """
        try:
            window = auto.ControlFromHandle(hwnd)
            # Chrome 通常在 EditControl 中，Depth=10 是搜索深度，foundIndex=1 是第一个编辑框
            edit = window.EditControl(searchDepth=10, foundIndex=1)

            # Edge 浏览器的地址栏名称可能不同，做兼容处理
            if not edit.Exists():
                edit = window.EditControl(Name="Address and search bar")  # Edge

            # 获取 ValuePattern 中的值 (即 URL)
            if edit.Exists():
                return edit.GetValuePattern().Value
        except:
            pass
        return ""

    def get_active_window_info(self):
        """
        获取当前前台窗口的所有关键信息。
        返回: (窗口标题, 进程名, URL)
        """
        try:
            # 获取前台窗口句柄
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd: return None, None, None

            # 获取窗口标题
            title = win32gui.GetWindowText(hwnd)
            # 获取线程ID和进程ID
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            process = self.get_process_name(pid)

            # 如果是浏览器，尝试提取 URL
            url = ""
            if process in self.browser_processes and title:
                url = self.get_browser_url(hwnd)

            return title, process, url
        except:
            return None, None, None


# ==========================================
# 5. 异步 AI 总结器 (AsyncAISummarizer)
# ==========================================
class AsyncAISummarizer:
    """
    负责将收集到的原始日志发送给 AI 进行分析，并保存结果。
    采用异步线程处理，避免阻塞主循环。
    """

    def __init__(self):
        self.client = None
        # 初始化 OpenAI 客户端
        if CONFIG["api_key"]:
            try:
                self.client = OpenAI(api_key=CONFIG["api_key"], base_url=CONFIG["base_url"])
            except:
                pass
        self.lock = threading.Lock()  # 文件写入锁

    def _save_raw(self, log_lines):
        """保存原始日志 (Raw Logs)，作为备份或调试用"""
        date_str = common.get_today_str()
        raw_path = os.path.join(common.RAW_LOG_DIR, f"{date_str}_raw.txt")
        try:
            with open(raw_path, "a", encoding="utf-8") as f:
                f.write("\n".join(log_lines) + "\n")
        except Exception as e:
            logger.error(f"Raw日志保存失败: {e}")

    def _save_csv(self, csv_content):
        """保存 AI 分析后的 CSV 数据"""
        date_str = common.get_today_str()
        file_path = os.path.join(common.LOG_DIR, f"{date_str}.csv")

        # 清理 AI 返回内容中的 Markdown 标记
        clean_text = csv_content.replace("```csv", "").replace("```", "").strip()
        lines = [line for line in clean_text.split('\n') if line.strip()]
        if not lines: return

        with self.lock:
            new_file = not os.path.exists(file_path)
            try:
                # 'utf-8-sig' 用于确保 Excel 能正确打开中文 CSV
                with open(file_path, "a", encoding="utf-8-sig", newline="") as f:
                    # 如果是新文件，写入表头
                    if new_file: f.write("开始时间,结束时间,任务分类,任务详情\n")
                    f.write("\n".join(lines) + "\n")
                logger.info(f"✅ AI分析完成: 写入 {len(lines)} 条记录")
            except Exception as e:
                logger.error(f"❌ CSV写入失败: {e}")

    def process_logs_async(self, log_lines):
        """
        公共接口：接收日志列表，启动后台线程进行 AI 处理。
        """
        if not log_lines: return

        # 1. 先保存原始日志
        self._save_raw(log_lines)

        # 2. 检查是否有 API Key
        if not self.client:
            logger.warning("⚠️ 未配置API Key，跳过AI分析")
            return

        # 定义后台任务函数
        def run_ai_task(lines):
            logger.info(f"🔄 请求AI分析 {len(lines)} 条日志...")
            user_content = "分析日志:\n" + "\n".join(lines)
            try:
                # 调用 AI 模型
                response = self.client.chat.completions.create(
                    model=CONFIG["model"],
                    messages=[
                        {'role': 'system', 'content': SYSTEM_PROMPT},
                        {'role': 'user', 'content': user_content}
                    ],
                    stream=False
                )
                # 保存结果
                self._save_csv(response.choices[0].message.content)
            except Exception as e:
                logger.error(f"⚠️ AI 请求失败: {e}")

        # 启动守护线程
        thread = threading.Thread(target=run_ai_task, args=(log_lines,))
        thread.daemon = True
        thread.start()


# ==========================================
# 6. 智能追踪器主类 (SmartTracker)
# ==========================================
# ================= 智能追踪器 (优化去重版) =================
# ================= 智能追踪器 (防抖+回滚版) =================
class SmartTracker:
    def __init__(self):
        self.collector = DataCollector()
        self.input_monitor = InputMonitor()
        self.ai = AsyncAISummarizer()
        self.log_buffer = []

        # 读取配置
        self.batch_size = CONFIG.get("batch_size", 10)
        self.check_interval = CONFIG.get("check_interval", 30)  # 阈值

        # === 状态机变量 ===
        # 1. 稳定态 (当前认定的主任务)
        self.stable_process = ""
        self.stable_title = ""
        self.stable_url = ""
        self.stable_start_time = time.time()

        # 2. 待定态 (可能是短暂干扰，也可能是新任务的开始)
        self.pending_process = None
        self.pending_title = None
        self.pending_url = None
        self.pending_start_time = 0

    def flush_buffer(self):
        if not self.log_buffer: return
        logs = self.log_buffer[:]
        self.log_buffer = []
        self.ai.process_logs_async(logs)

    def _is_same_task(self, proc1, url1, proc2, url2):
        """判断两个状态是否属于同一个任务"""
        # 进程不同 -> 肯定是不同任务
        if proc1 != proc2:
            return False

        # 进程相同，如果是浏览器，需要检查 URL
        if proc1 in self.collector.browser_processes:
            # 如果 URL 都有值且不相等 -> 不同任务
            if url1 and url2 and url1 != url2:
                return False
            # 如果其中一个 URL 没取到 (闪烁)，视为相同，防止误判
            return True

        # 普通软件，只要进程一样，就算同一个任务 (忽略标题变化)
        return True

    def run(self):
        logger.info(f"🚀 Tracker 运行中... (PID: {os.getpid()})")
        logger.info(f"🛡️ 强力防抖模式: 持续 < {self.check_interval}秒 的切换将被完全忽略")

        # 初始化：先获取第一个稳定状态
        while not self.stable_title:
            t, p, u = self.collector.get_active_window_info()
            if t:
                self.stable_title = t
                self.stable_process = p
                self.stable_url = u
                self.stable_start_time = time.time()
                print(f"✅ 初始化任务: {self.stable_process}")
            time.sleep(1)

        try:
            while True:
                # 采样频率必须快 (1秒)，才能捕捉到“切出去又切回来”的动作
                time.sleep(1)

                # 获取实时窗口信息
                raw_title, raw_process, raw_url = self.collector.get_active_window_info()
                if not raw_title: continue

                raw_title = raw_title.strip()
                # 浏览器 URL 容错：如果闪烁变空，沿用之前的
                if raw_process in self.collector.browser_processes and not raw_url:
                    if raw_process == self.stable_process: raw_url = self.stable_url
                    if raw_process == self.pending_process: raw_url = self.pending_url

                # === 核心逻辑 ===

                # 1. 判断“当前窗口”和“稳定态”是不是同一个任务
                is_stable = self._is_same_task(self.stable_process, self.stable_url, raw_process, raw_url)

                if is_stable:
                    # ---> 我们依然在主任务上 (或者切出去了又切回来了)

                    if self.pending_process:
                        # 如果之前有“待定任务”，说明刚才切出去了一小会儿，现在又回来了
                        # 触发“回滚”：忽略刚才那段干扰时间，假装一直都在主任务
                        duration = time.time() - self.pending_start_time
                        print(
                            f"↩️ 忽略短暂切换: {self.pending_process} ({int(duration)}s) -> 回归 {self.stable_process}")
                        self.pending_process = None  # 清空待定

                    # 更新稳定态的标题 (保持最新)
                    self.stable_title = raw_title
                    if raw_url: self.stable_url = raw_url

                else:
                    # ---> 我们现在的窗口和主任务不一样！

                    if not self.pending_process:
                        # 这是一个新的“异动”，开始记录待定
                        self.pending_process = raw_process
                        self.pending_title = raw_title
                        self.pending_url = raw_url
                        self.pending_start_time = time.time()
                        # print(f"⏳ 检测到切换: {raw_process}... 观察中")

                    else:
                        # 我们已经处于待定状态了，检查是不是同一个待定任务
                        if self._is_same_task(self.pending_process, self.pending_url, raw_process, raw_url):
                            # 依然停留在同一个新任务上，检查时间是否达标
                            pending_duration = time.time() - self.pending_start_time

                            if pending_duration > self.check_interval:
                                # ⏰【超时确权】⏰
                                # 确实切走了，而且超过了设定时间。
                                # 1. 结算旧任务 (结束时间 = 新任务开始的那一刻，而不是现在)
                                self._commit_log(self.stable_process, self.stable_title, self.stable_url,
                                                 self.stable_start_time, self.pending_start_time)

                                # 2. 新任务“转正”
                                print(f"👉 任务切换确认: {self.stable_process} -> {self.pending_process}")
                                self.stable_process = self.pending_process
                                self.stable_title = self.pending_title
                                self.stable_url = self.pending_url
                                self.stable_start_time = self.pending_start_time  # 开始时间回溯到刚切过来的那一刻

                                # 3. 清空待定
                                self.pending_process = None

                        else:
                            # 处于待定状态时，又切到了第三个软件！
                            # 策略：重置待定，重新开始观察这第三个软件
                            # print(f"🔀 待定期间又变了: {self.pending_process} -> {raw_process}")
                            self.pending_process = raw_process
                            self.pending_title = raw_title
                            self.pending_url = raw_url
                            self.pending_start_time = time.time()

        except KeyboardInterrupt:
            self.flush_buffer()
            logger.info("Tracker 退出。")

    def _commit_log(self, process, title, url, start_ts, end_ts):
        """生成并保存日志"""
        duration = end_ts - start_ts
        # 再次过滤：如果算下来的持续时间依然极短（理论上不会），也跳过
        if duration < 2: return

        activity_level = self.input_monitor.get_and_reset()
        start_t = datetime.fromtimestamp(start_ts).strftime('%H:%M:%S')
        end_t = datetime.fromtimestamp(end_ts).strftime('%H:%M:%S')

        url_part = f"[URL: {url}]" if url else ""
        log_content = f"<{process}> [活跃度:{activity_level}] {url_part} {title}"
        log_line = f"[{start_t}-{end_t}] {log_content}"

        self.log_buffer.append(log_line)
        print(f"📝 写入日志: {process} ({int(duration)}s)")

        if len(self.log_buffer) >= self.batch_size:
            self.flush_buffer()


# ==========================================
# 7. 程序入口
# ==========================================
if __name__ == "__main__":
    tracker = SmartTracker()
    tracker.run()
