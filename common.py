# common.py - 改进版
import os
import json
import logging
import sys
from datetime import datetime, timedelta

# ==========================================
# 基础路径配置
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
RAW_LOG_DIR = os.path.join(LOG_DIR, "raw")
FAILED_LOG_DIR = os.path.join(LOG_DIR, "failed")  # 新增：AI处理失败的日志备份
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
RUNTIME_LOG_PATH = os.path.join(LOG_DIR, "runtime.log")
GOALS_PATH = os.path.join(BASE_DIR, "goals.json")  # 新增：每日目标配置


def ensure_dirs():
    """确保必要的目录存在"""
    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(RAW_LOG_DIR, exist_ok=True)
    os.makedirs(FAILED_LOG_DIR, exist_ok=True)


def load_config():
    """加载配置文件"""
    default_config = {
        "api_key": "",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-3.5-turbo",
        "check_interval": 30,
        "batch_size": 5,
        # 新增配置项
        "idle_timeout": 300,  # 空闲超时（秒），超过此时间无操作标记为休息
        "ai_retry_times": 3,  # AI请求失败重试次数
        "ai_retry_delay": 5,  # 重试间隔（秒）
        "focus_alert_categories": ["娱乐", "社交"],  # 切换到这些分类时提醒
        "focus_alert_enabled": False,  # 是否启用专注提醒
        "browser_processes": ["chrome.exe", "msedge.exe", "firefox.exe", "opera.exe", "brave.exe"],
    }
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
                default_config.update(user_config)
        except Exception as e:
            print(f"配置文件加载失败: {e}")
    return default_config


def save_config(config):
    """保存配置文件"""
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"配置文件保存失败: {e}")
        return False


def load_goals():
    """加载每日目标配置"""
    default_goals = {
        "enabled": False,
        "targets": {
            "开发": 240,  # 分钟
            "学习": 120,
            "娱乐": 60,  # 上限
        },
        "limits": ["娱乐", "社交"],  # 这些分类是上限，其他是下限目标
    }
    if os.path.exists(GOALS_PATH):
        try:
            with open(GOALS_PATH, 'r', encoding='utf-8') as f:
                user_goals = json.load(f)
                default_goals.update(user_goals)
        except:
            pass
    return default_goals


def save_goals(goals):
    """保存目标配置"""
    try:
        with open(GOALS_PATH, 'w', encoding='utf-8') as f:
            json.dump(goals, f, indent=4, ensure_ascii=False)
        return True
    except:
        return False


def get_today_str():
    return datetime.now().strftime('%Y-%m-%d')


def get_date_str(dt):
    """从datetime对象获取日期字符串"""
    return dt.strftime('%Y-%m-%d')


def parse_datetime(dt_str):
    """解析多种格式的日期时间字符串"""
    formats = [
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d %H:%M',
        '%H:%M:%S',
        '%H:%M',
    ]
    for fmt in formats:
        try:
            return datetime.strptime(dt_str.strip(), fmt)
        except:
            continue
    return None


def get_all_csv_files():
    """获取所有CSV日志文件"""
    if not os.path.exists(LOG_DIR):
        return []
    files = [f for f in os.listdir(LOG_DIR) if f.endswith('.csv')]
    files.sort(reverse=True)
    return files


def get_date_range_files(start_date, end_date):
    """获取指定日期范围内的CSV文件"""
    files = []
    current = start_date
    while current <= end_date:
        filename = f"{current.strftime('%Y-%m-%d')}.csv"
        filepath = os.path.join(LOG_DIR, filename)
        if os.path.exists(filepath):
            files.append(filepath)
        current += timedelta(days=1)
    return files


# ==========================================
# 日志重定向核心
# ==========================================
class LoggerWriter:
    """将 print 内容同时写入终端和文件"""

    def __init__(self, level):
        self.level = level
        self.terminal = sys.stdout
        self.log_file = None
        try:
            self.log_file = open(RUNTIME_LOG_PATH, "a", encoding="utf-8", buffering=1)
        except Exception as e:
            print(f"无法打开日志文件: {e}")

    def write(self, message):
        try:
            if self.terminal:
                self.terminal.write(message)
            if self.log_file:
                # 为每条消息添加时间戳（仅对非空行）
                if message.strip():
                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    self.log_file.write(f"[{timestamp}] {message}")
                else:
                    self.log_file.write(message)
        except Exception:
            pass

    def flush(self):
        try:
            if self.terminal:
                self.terminal.flush()
            if self.log_file:
                self.log_file.flush()
        except Exception:
            pass

    def close(self):
        try:
            if self.log_file:
                self.log_file.close()
        except:
            pass


def setup_logging():
    """配置全局日志，接管 stdout/stderr"""
    ensure_dirs()
    
    sys.stdout = LoggerWriter("INFO")
    sys.stderr = LoggerWriter("ERROR")

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger("Tracker")


# ==========================================
# 统计工具函数
# ==========================================
def calculate_category_stats(df):
    """计算分类统计数据"""
    if df.empty or '任务分类' not in df.columns or 'Duration_Min' not in df.columns:
        return {}
    
    stats = df.groupby('任务分类')['Duration_Min'].agg(['sum', 'count', 'mean']).to_dict('index')
    return stats


def format_duration(minutes):
    """格式化时长显示"""
    if minutes < 60:
        return f"{minutes:.0f}分钟"
    hours = minutes // 60
    mins = minutes % 60
    if mins == 0:
        return f"{hours:.0f}小时"
    return f"{hours:.0f}小时{mins:.0f}分钟"
