# ============================================================
# FILE: utils.py
# ROLE: Helper utilities, network management, condition evaluator
# ============================================================
import asyncio
import time
import re
import json
from pathlib import Path
from decimal import Decimal
from typing import Optional, Any
from datetime import datetime, timezone
import pytz
from curl_cffi.requests import AsyncSession
from c_log import log
from consts import MAX_RECONNECT_ATTEMPTS

_SYMBOL_REGEX = re.compile(r"^[A-Z0-9]+$")

def now() -> int:
    """Return current timestamp in milliseconds."""
    return int(time.time() * 1000)

def eval_condition(condition: str, x: float) -> bool:
    """Safe evaluation of string conditions like '50 < x <= 75'."""
    try:
        allowed_names = {"x": x}
        code = compile(condition, "<string>", "eval")
        for name in code.co_names:
            if name not in allowed_names:
                raise NameError(f"Use of '{name}' not allowed in condition")
        return bool(eval(code, {"__builtins__": {}}, allowed_names))
    except Exception as e:
        log(f"[Utils] Failed to evaluate condition '{condition}' with x={x}: {e}", level="ERROR")
        return False


class Utils:
    def __init__(self):  
        self.tz_location = pytz.timezone("Europe/Kyiv")
        
    def get_date_time_now(self):
        now_dt = datetime.now(self.tz_location)
        return now_dt.strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def safe_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
        
    @staticmethod
    def safe_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
        
    @staticmethod
    def safe_round(value: Any, ndigits: int = 2, default: float = 0.0) -> float:
        try:
            return round(float(value), ndigits)
        except (TypeError, ValueError):
            return default    

    @staticmethod
    def milliseconds_to_datetime(milliseconds):
        if milliseconds is None:
            return "N/A"
        try:
            ms = int(milliseconds)
            if milliseconds < 0: return "N/A"
        except (ValueError, TypeError):
            return "N/A"

        if ms > 1e10:
            seconds = ms / 1000
        else:
            seconds = ms

        dt = datetime.fromtimestamp(seconds, timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod    
    def format_duration(ms: int) -> str:
        if ms is None:
            return ""
        
        total_seconds = ms // 1000
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        if hours > 0 and minutes > 0:
            return f"{hours}h {minutes}m"
        elif minutes > 0 and seconds > 0:
            return f"{minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m"
        else:
            return f"{seconds}s"
        
    @staticmethod
    def to_human_digit(value):
        if value is None:
            return None
        dec_value = Decimal(str(value)).normalize()
        if dec_value == dec_value.to_integral():
            return format(dec_value, 'f')
        else:
            return format(dec_value, 'f').rstrip('0').rstrip('.')  
    
    @staticmethod
    def normalize_symbol(raw: str) -> Optional[str]:
        if not raw or not isinstance(raw, str):
            return None

        sym = raw.strip().upper()

        if not sym:
            return None

        for ch in sym:
            if "А" <= ch <= "Я" or "а" <= ch <= "я":
                return None

        if not _SYMBOL_REGEX.match(sym):
            return None

        return sym

    @staticmethod
    def get_spec_precisions(symbol_info, symbol):
        if not symbol_info or not isinstance(symbol_info, dict) or "symbols" not in symbol_info:
            return None
            
        symbol_data = next((item for item in symbol_info.get("symbols", []) if item.get('symbol') == symbol), None)
        if not symbol_data:
            return None

        lot_size_filter = next((f for f in symbol_data["filters"] if f["filterType"] == "LOT_SIZE"), None)
        price_filter = next((f for f in symbol_data["filters"] if f["filterType"] == "PRICE_FILTER"), None)

        if not lot_size_filter or not price_filter:
            return

        def count_decimal_places(number_str):
            if '.' in number_str:
                return len(number_str.rstrip('0').split('.')[-1])
            return 0

        qty_precission = count_decimal_places(lot_size_filter['stepSize'])
        price_precision = count_decimal_places(price_filter['tickSize'])

        return qty_precission, price_precision

    @staticmethod
    def read_json_file(file_path: str) -> dict:
        try:
            p = Path(file_path)
            if not p.exists():
                return {}
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    @staticmethod
    def write_json_file(file_path: str, data: dict):
        try:
            p = Path(file_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception:
            pass

    @staticmethod
    async def wait_for_fsm_sync(state, timeout_sec: float = 3.0, poll_interval: float = 0.01) -> bool:
        max_cycles = int(timeout_sec / poll_interval)
        wait_cycles = 0
        while state.avg_entry_price == state.pre_avg_price and wait_cycles < max_cycles:
            await asyncio.sleep(poll_interval)
            wait_cycles += 1
        
        return state.avg_entry_price != state.pre_avg_price


class NetworkServices:
    def __init__(self):
        self.session: Optional[AsyncSession] = None

    async def initialize_session(self):
        if not self.session:
            self.session = AsyncSession(timeout=20, impersonate="chrome110")

    async def _check_session_connection(self, session: AsyncSession) -> bool:
        url = "https://fapi.binance.com/fapi/v1/time"
        try:
            response = await session.get(url)
            return response.status_code == 200
        except Exception as e:
            log(f"[PING ERROR] Ошибка при пинге {url}: {e}", level="ERROR")
        return False

    async def validate_session(self) -> bool:
        for attempt in range(1, MAX_RECONNECT_ATTEMPTS + 1):
            if self.session:
                try:
                    if await self._check_session_connection(self.session):
                        return True
                except Exception as e:
                    log(f"[ERROR] Исключение при проверке соединения: {e}", level="ERROR")

            await asyncio.sleep((attempt * 1.6) + 1)
            log(f"🔁 Попытка восстановить сессию ({attempt}/{MAX_RECONNECT_ATTEMPTS})...", level="INFO")
            await self.initialize_session()

        log("❌ Не удалось восстановить сессию после нескольких попыток.", level="ERROR")
        return False

    async def shutdown_session(self):
        self.session = None
