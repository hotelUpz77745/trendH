# ============================================================
# FILE: consts.py
# ROLE: Global constants and robust configuration loader
# ============================================================
r"""
Глобальный модуль констант и загрузки конфигурации TrendH_Papper.
Поддерживает автоматическую нормализацию путей Windows (обратные слэши \\ и \)
для предотвращения ошибок JSONDecodeError при редактировании cfg.json пользователем.
"""

import os
import re
import json
import pathlib
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# Загрузка переменных окружения
env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path)


def fix_windows_paths_in_json(content: str) -> str:
    """
    Нормализует неэкранированные пути Windows в строках JSON.
    Заменяет одиночные обратные слэши (C:\\...) на прямые слэши (/),
    которые полностью валидны в стандарте JSON и нативно поддерживаются Windows/Python.
    """
    def _fix_path_match(match):
        prefix = match.group(1)
        val = match.group(2)
        suffix = match.group(3)
        # Заменяем все обратные слэши на прямые
        clean_val = val.replace('\\', '/')
        return f'{prefix}{clean_val}{suffix}'

    # Поиск строковых значений для ключей, оканчивающихся на _path
    content = re.sub(r'("[\w_]*path"\s*:\s*")([^"]*)(")', _fix_path_match, content)
    # Поиск строковых значений, начинающихся с буквы диска (C:\... или D:\...)
    content = re.sub(r'(":\s*")([A-Za-z]:\\[^"]*)(")', _fix_path_match, content)
    # Исправление любых оставшихся невалидных одиночных слэшей
    content = re.sub(r'\\(?!["\\/bfnrt]|u[0-9a-fA-F]{4})', r'\\\\', content)
    return content


def load_config() -> Dict[str, Any]:
    """
    Загружает конфигурационный файл cfg.json.
    В случае обнаружения неэкранированных путей Windows автоматически
    нормализует их и успешно парсит JSON.
    """
    cfg_path = os.path.join(os.path.dirname(__file__), 'cfg.json')
    if not os.path.exists(cfg_path):
        raise FileNotFoundError(f"Config file not found at: {cfg_path}")

    with open(cfg_path, 'r', encoding='utf-8') as f:
        content = f.read()

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # Автоматическое восстановление при наличии неэкранированных обратных слэшей Windows
        fixed_content = fix_windows_paths_in_json(content)
        return json.loads(fixed_content)


# Инициализация глобального словаря конфигурации
cfg: Dict[str, Any] = load_config()

# ============================================================
# ОБЩИЕ ПАРАМЕТРЫ ПРИЛОЖЕНИЯ
# ============================================================
MAIN_LOOP_DELAY_SEC: float = float(cfg.get("MAIN_LOOP_DELAY_SEC", 0.1))
MAX_RECONNECT_ATTEMPTS: int = int(cfg.get("MAX_RECONNECT_ATTEMPTS", 5))
INDICATORS_REFRESH_INTERVAL_SEC: int = int(cfg.get("INDICATORS_REFRESH_INTERVAL_SEC", 60))
DIRECTION_MODE: str = str(cfg.get("DIRECTION_MODE", "HEDGE"))
TIME_ZONE: str = str(cfg.get("TIME_ZONE", "UTC"))

# ============================================================
# ПАРАМЕТРЫ СТРАТЕГИЙ И ПРАВИЛ
# ============================================================
ENTER_RULES: Dict[str, Any] = cfg.get("enter_rules", {})
EXIT_RULES: Dict[str, Any] = cfg.get("exit_rules", {})
UNIVERSES_CFG: Dict[str, Any] = cfg.get("universes", {})
ANALYTICS_CFG: Dict[str, Any] = cfg.get("analytics", {})
PAPER_TRADING_CFG: Dict[str, Any] = cfg.get("paper_trading", {})

# ============================================================
# ПАРАМЕТРЫ ЛОГИРОВАНИЯ
# ============================================================
LOGGING_CFG: Dict[str, Any] = cfg.get("logging", {})
LOG_DEBUG: bool = bool(LOGGING_CFG.get("debug", False))
LOG_INFO: bool = bool(LOGGING_CFG.get("info", True))
LOG_WARNING: bool = bool(LOGGING_CFG.get("warning", True))
LOG_ERROR: bool = bool(LOGGING_CFG.get("error", True))
MAX_LOG_LINES: int = int(LOGGING_CFG.get("max_log_lines", 50000))
LOG_TO_CONSOLE: bool = bool(LOGGING_CFG.get("log_to_console", False))
LOG_TO_FILE: bool = bool(LOGGING_CFG.get("log_to_file", True))

# ============================================================
# БАЗОВЫЕ ДИРЕКТОРИИ И ПУТИ
# ============================================================
BASE_DIR: pathlib.Path = pathlib.Path(__file__).parent.resolve()
ANALYTICS_DIR: pathlib.Path = BASE_DIR / "logs" / "analytics"
DATA_DIR: pathlib.Path = BASE_DIR / "logs" / "data"
CFG_PATH: pathlib.Path = BASE_DIR / "cfg.json"

ANALYTICS_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================
# TELEGRAM И СЕРВИСНЫЕ ДЕМОНЫ
# ============================================================
TG_TOKEN: str = os.getenv("TG_BOT_TOKEN", "")
TG_CFG: Dict[str, Any] = cfg.get("telegram", {})
TG_ENABLED: bool = bool(TG_CFG.get("enabled", False))
TG_ALLOWED_USERS = TG_CFG.get("allowed_users", [])

WATCHDOG_CFG: Dict[str, Any] = cfg.get("watchdog", {})
BACKUP_CFG: Dict[str, Any] = cfg.get("backup", {})
NOTIFICATIONS_CFG: Dict[str, Any] = cfg.get("notifications", {})
AUTO_CLOSING_CFG: Dict[str, Any] = cfg.get("auto_closing", {})


# ============================================================
# ХЕЛПЕРЫ ДЛЯ РАБОТЫ С ИСТОЧНИКАМИ ДАННЫХ
# ============================================================
def get_data_sources_cfg() -> Dict[str, Any]:
    """Возвращает секцию data_sources из конфигурации."""
    return cfg.get("data_sources", {})


def get_symbols_path() -> Optional[str]:
    """Возвращает целевой путь к app.json сеточника."""
    return get_data_sources_cfg().get("symbols_path")


def get_runtime_path() -> Optional[str]:
    """Возвращает целевой путь к папке runtime сеточника."""
    return get_data_sources_cfg().get("runtime_path")


def reload_config() -> Dict[str, Any]:
    """Принудительно перезагружает конфигурацию из cfg.json."""
    global cfg, ENTER_RULES, EXIT_RULES, UNIVERSES_CFG, ANALYTICS_CFG
    global DIRECTION_MODE, PAPER_TRADING_CFG, LOGGING_CFG, WATCHDOG_CFG
    cfg = load_config()
    ENTER_RULES = cfg.get("enter_rules", {})
    EXIT_RULES = cfg.get("exit_rules", {})
    UNIVERSES_CFG = cfg.get("universes", {})
    ANALYTICS_CFG = cfg.get("analytics", {})
    DIRECTION_MODE = cfg.get("DIRECTION_MODE", "HEDGE")
    PAPER_TRADING_CFG = cfg.get("paper_trading", {})
    LOGGING_CFG = cfg.get("logging", {})
    WATCHDOG_CFG = cfg.get("watchdog", {})
    return cfg
