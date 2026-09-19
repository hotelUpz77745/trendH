# ============================================================
# FILE: c_log.py
# ROLE: Custom unified logger
# ============================================================
from __future__ import annotations

import inspect
import logging
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from functools import wraps
import shutil
from logging.handlers import RotatingFileHandler
from pprint import pformat
from typing import Any, Optional, Dict, Tuple

from consts import (
    LOG_DEBUG,
    LOG_INFO,
    LOG_WARNING,
    LOG_ERROR,
    LOG_TO_CONSOLE,
    LOG_TO_FILE,
    MAX_LOG_LINES,
    LOG_BACKUP_COUNT,
    TIME_ZONE,
)

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass



# ============================================================
# TIME
# ============================================================

def log_time() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# ============================================================
# HELPERS
# ============================================================

def estimate_average_line_length(path: str, sample: int = 200) -> int:
    target_path = path
    if not os.path.exists(target_path):
        all_path = os.path.join(os.path.dirname(path), "all.log")
        target_path = all_path if os.path.exists(all_path) else None
    if not target_path or not os.path.exists(target_path):
        return 180
    try:
        lines = []
        with open(target_path, "r", encoding="utf-8", errors="replace") as f:
            for _ in range(sample):
                line = next(f, None)
                if line is None:
                    break
                lines.append(len(line.encode("utf-8")))
        return sum(lines) // len(lines) if lines else 180
    except Exception:
        return 180


def calc_max_bytes(avg_len: int, lines: int) -> int:
    return avg_len * lines


# ============================================================
# HANDLERS
# ============================================================

class UnlockedRotatingFileHandler(RotatingFileHandler):
    """
    Кастомный RotatingFileHandler, который не держит файл постоянно открытым.
    Каждая запись (emit) открывает, пишет и закрывает файл.
    Это снимает жесткую блокировку Windows, позволяя удалять/переименовывать логи.
    """

    def __init__(self, filename, mode='a', maxBytes=0, backupCount=0, encoding=None):
        super().__init__(filename, mode, maxBytes, backupCount, encoding, delay=True)
        self.stream = None

    def _open(self):
        return None

    def rotation_filename(self, default_name: str) -> str:
        """Превращает logs/all.log.1 -> logs/all.1.log для подсветки синтаксиса в редакторах."""
        parts = default_name.rsplit(".", 2)
        if len(parts) == 3 and parts[2].isdigit():
            return f"{parts[0]}.{parts[2]}.{parts[1]}"
        return default_name

    def doRollover(self):
        if self.stream:
            try:
                self.stream.close()
            except Exception:
                pass
            self.stream = None

        if self.backupCount > 0:
            for i in range(self.backupCount - 1, 0, -1):
                sfn = self.rotation_filename(f"{self.baseFilename}.{i}")
                dfn = self.rotation_filename(f"{self.baseFilename}.{i + 1}")
                if os.path.exists(sfn):
                    try:
                        if os.path.exists(dfn):
                            os.remove(dfn)
                        os.replace(sfn, dfn)
                    except Exception:
                        pass
            dfn = self.rotation_filename(f"{self.baseFilename}.1")
            try:
                if os.path.exists(dfn):
                    os.remove(dfn)
                os.replace(self.baseFilename, dfn)
            except Exception:
                try:
                    shutil.copy2(self.baseFilename, dfn)
                    with open(self.baseFilename, "w", encoding=self.encoding) as f:
                        f.truncate(0)
                except Exception:
                    pass

    def emit(self, record):
        try:
            if self.shouldRollover(record):
                self.doRollover()

            msg = self.format(record)
            os.makedirs(os.path.dirname(self.baseFilename), exist_ok=True)
            with open(self.baseFilename, self.mode, encoding=self.encoding) as f:
                f.write(msg + self.terminator)
        except Exception:
            self.handleError(record)

    def shouldRollover(self, record):
        if self.maxBytes > 0:
            msg = "%s\n" % self.format(record)
            try:
                size = os.path.getsize(self.baseFilename)
            except OSError:
                size = 0
            if size + len(msg.encode(self.encoding or 'utf-8')) >= self.maxBytes:
                return 1
        return 0


# ============================================================
# LOG ANTI-SPAMMER
# ============================================================

class LogAntiSpammer:
    """
    Интеллектуальный антиспамер и дедупликатор логов.
    - Автоматически подавляет циклический спам одинаковых сообщений и ошибок.
    - Накапливает счетчик скрытых дубликатов и выводит сводку при возобновлении/окне.
    - Никогда не глушит уникальные критические сигналы ([SIGNAL], [WATCHDOG]).
    """

    DEFAULT_THROTTLES: Dict[str, float] = {
        "ERROR": 5.0,    # Одинаковые ошибки не чаще 1 раза в 5 сек
        "WARNING": 10.0, # Одинаковые предупреждения не чаще 1 раза в 10 сек
        "INFO": 3.0,     # Повторяющийся статус не чаще 1 раза в 3 сек
        "DEBUG": 2.0,
    }

    CRITICAL_MARKERS = (
        "[SIGNAL ENTRY]",
        "[SIGNAL EXIT]",
        "[POSITION OPEN]",
        "[CLOSE ALL]",
        "Close All:",
        "[WATCHDOG]",
    )

    def __init__(self):
        self._records: Dict[str, Dict[str, Any]] = {}
        self._counter: int = 0

    def process(
        self,
        msg: str,
        level: str = "INFO",
        throttle_sec: float = 0.0,
        throttle_key: Optional[str] = None
    ) -> Tuple[bool, str]:
        for marker in self.CRITICAL_MARKERS:
            if marker in msg:
                return True, msg

        now = time.time()
        lvl = level.upper()

        effective_sec = throttle_sec if throttle_sec > 0 else self.DEFAULT_THROTTLES.get(lvl, 0.0)
        if effective_sec <= 0:
            return True, msg

        if throttle_key is not None:
            key = f"{lvl}:{throttle_key}"
        else:
            first_line = msg.split("\n")[0][:120].strip()
            key = f"{lvl}:{first_line}"

        rec = self._records.get(key)
        if rec is None:
            self._records[key] = {
                "last_time": now,
                "count": 0,
                "first_suppressed": 0.0
            }
            self._clean_stale(now)
            return True, msg

        elapsed = now - rec["last_time"]
        if elapsed < effective_sec:
            rec["count"] += 1
            if rec["first_suppressed"] == 0.0:
                rec["first_suppressed"] = now
            return False, msg

        suppressed = rec["count"]
        suppressed_time = now - rec["first_suppressed"] if rec["first_suppressed"] > 0 else elapsed

        rec["last_time"] = now
        rec["count"] = 0
        rec["first_suppressed"] = 0.0

        if suppressed > 0:
            return True, f"[Повторено {suppressed} раз за {suppressed_time:.1f}с] {msg}"

        return True, msg

    def _clean_stale(self, now: float) -> None:
        self._counter += 1
        if self._counter >= 150:
            self._counter = 0
            stale = [k for k, v in self._records.items() if now - v["last_time"] > 300.0]
            for k in stale:
                del self._records[k]


# ============================================================
# UNIFIED LOGGER
# ============================================================

class UnifiedLogger:
    """
    Универсальный логгер:
    - logging + RotatingFileHandler + LogAntiSpammer
    - decorator для методов
    - совместим с async / sync
    """

    def __init__(
        self,
        name: str,
        log_dir: str = "./logs",
        max_lines: int = MAX_LOG_LINES,
        context: Optional[dict] = None,
    ):
        os.makedirs(log_dir, exist_ok=True)
        all_log_path = os.path.join(log_dir, "all.log")
        avg_len = estimate_average_line_length(all_log_path)
        all_max_bytes = max(50_000, calc_max_bytes(avg_len, max_lines))

        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False  # Не всплывать в root

        # Handler добавляем ТОЛЬКО если его ещё нет
        if not logger.handlers:
            formatter = logging.Formatter(
                "%(asctime)s | %(levelname)s | %(context)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )

            if LOG_TO_FILE:
                all_handler = UnlockedRotatingFileHandler(
                    all_log_path,
                    maxBytes=all_max_bytes,
                    backupCount=LOG_BACKUP_COUNT,
                    encoding="utf-8",
                )
                all_handler.setFormatter(formatter)
                logger.addHandler(all_handler)

            if LOG_TO_CONSOLE:
                console_handler = logging.StreamHandler(sys.stdout)
                console_handler.setFormatter(formatter)
                logger.addHandler(console_handler)

        self._logger = logging.LoggerAdapter(
            logger,
            extra={"context": context or name},
        )
        self.anti_spammer = LogAntiSpammer()

    def debug(self, msg: str, *args, throttle_sec: float = 0, throttle_key: Optional[str] = None, **kwargs):
        if not LOG_DEBUG:
            return
        should_log, final_msg = self.anti_spammer.process(msg, "DEBUG", throttle_sec, throttle_key)
        if should_log:
            self._logger.debug(final_msg, *args, **kwargs)

    def info(self, msg: str, *args, throttle_sec: float = 0, throttle_key: Optional[str] = None, **kwargs):
        if not LOG_INFO:
            return
        should_log, final_msg = self.anti_spammer.process(msg, "INFO", throttle_sec, throttle_key)
        if should_log:
            self._logger.info(final_msg, *args, **kwargs)

    def warning(self, msg: str, *args, throttle_sec: float = 0, throttle_key: Optional[str] = None, **kwargs):
        if not LOG_WARNING:
            return
        should_log, final_msg = self.anti_spammer.process(msg, "WARNING", throttle_sec, throttle_key)
        if should_log:
            self._logger.warning(final_msg, *args, **kwargs)

    def error(self, msg: str, *args, throttle_sec: float = 0, throttle_key: Optional[str] = None, **kwargs):
        if not LOG_ERROR:
            return
        should_log, final_msg = self.anti_spammer.process(msg, "ERROR", throttle_sec, throttle_key)
        if should_log:
            self._logger.error(final_msg, *args, **kwargs)

    def exception(self, msg: str, *args, throttle_sec: float = 0, throttle_key: Optional[str] = None, exc: Exception = None, **kwargs):
        if not LOG_ERROR:
            return
        should_log, final_msg = self.anti_spammer.process(msg, "ERROR", throttle_sec, throttle_key)
        if should_log:
            exc_info = exc if exc is not None else True
            self._logger.exception(final_msg, *args, exc_info=exc_info, **kwargs)


    # ======================================================
    # DECORATOR
    # ======================================================

    def total_exception_decor(self, func, context: Optional[Any] = None):
        """
        Ловит ВСЕ исключения, логирует контекст,
        НЕ крашит приложение.
        """
        if getattr(func, "_is_wrapped", False):
            return func

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as ex:
                self._log_exception(func, ex, args, kwargs, context)
                return None

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as ex:
                self._log_exception(func, ex, args, kwargs, context)
                return None

        wrapper = (
            async_wrapper
            if inspect.iscoroutinefunction(func)
            else sync_wrapper
        )
        wrapper._is_wrapped = True
        return wrapper

    def _log_exception(self, func, ex, args, kwargs, context: Optional[Any] = None):
        extra = {}
        if context is not None:
            extra["context"] = context

        self._logger.error(
            f"[EXCEPTION] {func.__qualname__} -> {ex}\n"
            f"Args:\n{pformat({'args': args, 'kwargs': kwargs})}\n"
            f"Stack:\n{traceback.format_exc()}",
            extra=extra or None,
        )

    # ======================================================
    # MASS WRAP
    # ======================================================

    def wrap_object_methods(self, obj: Any, context: Optional[Any] = None):
        for cls in obj.__class__.mro():
            if cls is object:
                continue

            for name, attr in cls.__dict__.items():
                if name.startswith("_"):
                    continue

                if name.startswith("__"):
                    continue

                if not callable(attr):
                    continue

                try:
                    original = getattr(obj, name)
                    if getattr(original, "_is_wrapped", False):
                        continue

                    wrapped = self.total_exception_decor(original, context)
                    setattr(obj, name, wrapped)
                except Exception:
                    continue

# Глобальный экземпляр
_global_logger = UnifiedLogger("MAIN")

def log(msg: str, level: str = "DEBUG", *args, throttle_sec: float = 0.0, throttle_key: Optional[str] = None, exc: Exception = None, **kwargs):
    lvl = level.upper()
    if lvl == "INFO":
        _global_logger.info(msg, *args, throttle_sec=throttle_sec, throttle_key=throttle_key, **kwargs)
    elif lvl == "WARNING":
        _global_logger.warning(msg, *args, throttle_sec=throttle_sec, throttle_key=throttle_key, **kwargs)
    elif lvl == "ERROR":
        if exc:
            _global_logger.exception(msg, *args, throttle_sec=throttle_sec, throttle_key=throttle_key, exc=exc, **kwargs)
        else:
            _global_logger.error(msg, *args, throttle_sec=throttle_sec, throttle_key=throttle_key, **kwargs)
    else:
        _global_logger.debug(msg, *args, throttle_sec=throttle_sec, throttle_key=throttle_key, **kwargs)