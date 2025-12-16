
# common.py
import os
import json
import logging
import sys
from datetime import datetime

# 基础路径配置
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
RAW_LOG_DIR = os.path.join(LOG_DIR, "raw")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
RUNTIME_LOG_PATH = os.path.join(LOG_DIR, "runtime.log")  # 运行日志路径


def ensure_dirs():
    """确保必要的目录存在"""
    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(RAW_LOG_DIR, exist_ok=True)


def load_config():
    """加载配置文件"""
    default_config = {
        "api_key": "",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-3.5-turbo",
        "check_interval": 30,
        "batch_size": 20
    }
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
                default_config.update(user_config)
        except Exception as e:
            print(f"配置文件加载失败: {e}")
    return default_config


def get_today_str():
    return datetime.now().strftime('%Y-%m-%d')


def get_all_csv_files():
    """获取所有CSV日志文件"""
    if not os.path.exists(LOG_DIR): return []
    files = [f for f in os.listdir(LOG_DIR) if f.endswith('.csv')]
    files.sort(reverse=True)
    return files


# --- 日志重定向核心 ---
class LoggerWriter:
    """将 print 内容同时写入终端和文件"""

    def __init__(self, level):
        self.level = level
        self.terminal = sys.stdout
        # 使用追加模式，避免每次重启清空日志
        self.log_file = open(RUNTIME_LOG_PATH, "a", encoding="utf-8", buffering=1)

    def write(self, message):
        try:
            # 终端显示
            if self.terminal:
                self.terminal.write(message)
            # 文件写入
            if self.log_file:
                self.log_file.write(message)
        except Exception:
            pass  # 忽略写入错误防止崩溃

    def flush(self):
        try:
            if self.terminal: self.terminal.flush()
            if self.log_file: self.log_file.flush()
        except Exception:
            pass


def setup_logging():
    """配置全局日志，接管 stdout/stderr"""
    # 备份原始 stdout 以便在退出时恢复（可选）
    original_stdout = sys.stdout

    # 将标准输出和错误输出重定向
    sys.stdout = LoggerWriter("INFO")
    sys.stderr = LoggerWriter("ERROR")

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S',
        handlers=[
            logging.StreamHandler(sys.stdout)  # 输出到我们要的 Writer
        ]
    )
    return logging.getLogger("Tracker")

