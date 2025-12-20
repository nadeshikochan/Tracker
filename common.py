# common.py - v3.0 Simplified
import os
import json
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
RAW_LOG_DIR = os.path.join(LOG_DIR, "raw")
FAILED_LOG_DIR = os.path.join(LOG_DIR, "failed")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
RUNTIME_LOG_PATH = os.path.join(LOG_DIR, "runtime.log")
GOALS_PATH = os.path.join(BASE_DIR, "goals.json")


def ensure_dirs():
    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(RAW_LOG_DIR, exist_ok=True)
    os.makedirs(FAILED_LOG_DIR, exist_ok=True)


def log(msg):
    """日志记录 - 写入文件并输出到终端（支持中文）"""
    ensure_dirs()
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{timestamp}] {msg}"
    
    # 写入文件
    try:
        with open(RUNTIME_LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(line + "\n")
    except:
        pass
    
    # 输出到终端（处理中文编码问题）
    try:
        import sys
        import io
        # 确保stdout使用UTF-8编码
        if sys.stdout.encoding != 'utf-8':
            sys.stdout.reconfigure(encoding='utf-8')
        print(line)
    except Exception:
        try:
            # 回退方案：强制UTF-8输出
            print(line.encode('utf-8').decode('utf-8'))
        except:
            pass


def load_config():
    default_config = {
        "api_key": "",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-3.5-turbo",
        "check_interval": 30,
        "batch_size": 5,
        "idle_timeout": 300,
        "ai_retry_times": 3,
        "ai_retry_delay": 5,
        "browser_processes": ["chrome.exe", "msedge.exe", "firefox.exe", "opera.exe", "brave.exe"],
    }
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                default_config.update(json.load(f))
        except:
            pass
    return default_config


def save_config(config):
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        return True
    except:
        return False


def load_goals():
    default_goals = {
        "enabled": False,
        "targets": {"开发": 240, "学习": 120, "娱乐": 60},
        "limits": ["娱乐", "社交"],
    }
    if os.path.exists(GOALS_PATH):
        try:
            with open(GOALS_PATH, 'r', encoding='utf-8') as f:
                default_goals.update(json.load(f))
        except:
            pass
    return default_goals


def save_goals(goals):
    try:
        with open(GOALS_PATH, 'w', encoding='utf-8') as f:
            json.dump(goals, f, indent=4, ensure_ascii=False)
        return True
    except:
        return False


def get_today_str():
    return datetime.now().strftime('%Y-%m-%d')
