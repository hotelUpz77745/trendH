# ============================================================
# FILE: consts.py
# ROLE: Global constants and configuration loader
# ============================================================
import os
import json
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path)

def load_config():
    cfg_path = os.path.join(os.path.dirname(__file__), 'cfg.json')
    with open(cfg_path, 'r', encoding='utf-8') as f:
        return json.load(f)

cfg = load_config()

# General settings
MAIN_LOOP_DELAY_SEC = cfg["MAIN_LOOP_DELAY_SEC"]
MAX_RECONNECT_ATTEMPTS = cfg["MAX_RECONNECT_ATTEMPTS"]
INDICATORS_REFRESH_INTERVAL_SEC = cfg["INDICATORS_REFRESH_INTERVAL_SEC"]

# Strategy settings
ENTER_RULES = cfg["enter_rules"]
EXIT_RULES = cfg["exit_rules"]
UNIVERSES_CFG = cfg.get("universes", {})
ANALYTICS_CFG = cfg["analytics"]
DIRECTION_MODE = cfg["DIRECTION_MODE"]
PAPER_TRADING_CFG = cfg["paper_trading"]

# Logging settings
LOGGING_CFG = cfg["logging"]
LOG_DEBUG = LOGGING_CFG["debug"]
LOG_INFO = LOGGING_CFG["info"]
LOG_WARNING = LOGGING_CFG["warning"]
LOG_ERROR = LOGGING_CFG["error"]
MAX_LOG_LINES = LOGGING_CFG["max_log_lines"]
LOG_TO_CONSOLE = LOGGING_CFG["log_to_console"]
LOG_TO_FILE = LOGGING_CFG["log_to_file"]
TIME_ZONE = LOGGING_CFG["TIME_ZONE"]

import pathlib
BASE_DIR = pathlib.Path(__file__).parent.resolve()
ANALYTICS_DIR = BASE_DIR / "logs" / "analytics"
DATA_DIR = BASE_DIR / "logs" / "data"

ANALYTICS_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

TG_TOKEN = os.getenv("TG_BOT_TOKEN", "")
TG_ENABLED = bool(cfg["telegram"].get("enabled", False))
TG_ALLOWED_USERS = cfg["telegram"]["allowed_users"]
CFG_PATH = BASE_DIR / "cfg.json"

WATCHDOG_CFG = cfg.get("watchdog", {})
BACKUP_CFG = cfg.get("backup", {})
NOTIFICATIONS_CFG = cfg.get("notifications", {})
AUTO_CLOSING_CFG = cfg.get("auto_closing", {})
