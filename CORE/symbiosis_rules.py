# ============================================================
# FILE: CORE/symbiosis_rules.py
# ROLE: Symbiotic Rules & Cross-Bot Portfolio Filters
# PROJECT: TrendH_Papper & Hron3 (cron3Papper) Symbiosis
# ============================================================

import os
import json
import time
from typing import Dict, Any, Optional, List
from c_log import log
from CORE.rules import BaseRule

# Default path to external Grid Bot (cron3Papper) analytics
DEFAULT_CRON_ANALYTICS_PATH = "C:/Users/user/Desktop/My_Pro/HP_EliteBook_735_old/MY/HRON_3/cron3Papper/ANALYTICS/analytics.json"


class CronAnalyticsCache:
    """
    Потокобезопасный кэш аналитики сеточного бота (cron3Papper) с TTL.
    Предотвращает избыточные дисковые операции чтения при обработке тиков.
    """
    _cache: Dict[str, Any] = {}
    _last_read_ts: float = 0.0
    _cache_ttl_sec: float = 15.0

    @classmethod
    def get_data(cls, path: str = DEFAULT_CRON_ANALYTICS_PATH) -> Dict[str, Any]:
        """Возвращает кэшированные данные аналитики сеточника или читает с диска при истечении TTL."""
        now = time.time()
        if cls._cache and (now - cls._last_read_ts) < cls._cache_ttl_sec:
            return cls._cache

        if not os.path.exists(path):
            return cls._cache or {}

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            cls._cache = data
            cls._last_read_ts = now
            return data
        except Exception as e:
            log(f"[CronAnalyticsCache] Ошибка чтения {path}: {e}", level="WARN", throttle_sec=30)
            return cls._cache or {}

    @classmethod
    def get_per_coin(cls, path: str = DEFAULT_CRON_ANALYTICS_PATH) -> Dict[str, Any]:
        """Возвращает словарь метрик per_coin сеточника."""
        data = cls.get_data(path)
        return data.get("per_coin", {})

    @classmethod
    def clear(cls) -> None:
        """Сбрасывает кэш."""
        cls._cache.clear()
        cls._last_read_ts = 0.0


class EntryGridNetFilterRule(BaseRule):
    """
    Правило фильтрации входа на базе статистики чистого PnL сеточника (Grid Net PnL).
    
    Режимы:
    1. 'ALPHA_ONLY': Вход разрешен ТОЛЬКО на монетах в фазе сильного трендового импульса
       Alpha Momentum (где сеточник тянет просадку, net_profit <= max_grid_net, по умолчанию <= 0.0).
       Защищает от ложных входов во флэтовых монетах-донорах сетки.
    2. 'EXCLUDE_TOP_CASH_COWS': Запрещает вход на топ-N (по умолчанию 10) монетах сеточника
       с наибольшей прибылью (кэш-коровы сетки: PIEVERSE, CROSS, FLOCK и т.д.).
    """

    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.is_active: bool = bool(cfg.get("is_active", False))
        self.mode: str = str(cfg.get("mode", "ALPHA_ONLY")).upper()
        self.max_grid_net: float = float(cfg.get("max_grid_net", 0.0))
        self.exclude_top_n: int = int(cfg.get("exclude_top_n", 10))
        self.analytics_path: str = str(cfg.get("analytics_path", DEFAULT_CRON_ANALYTICS_PATH))

    def _get_coin_stats(self, symbol: str) -> Dict[str, Any]:
        per_coin = CronAnalyticsCache.get_per_coin(self.analytics_path)
        return per_coin.get(symbol, {})

    def _is_top_cash_cow(self, symbol: str) -> bool:
        per_coin = CronAnalyticsCache.get_per_coin(self.analytics_path)
        if not per_coin:
            return False
        # Сортируем монеты по чистому PnL сеточника по убыванию
        sorted_coins = sorted(
            per_coin.items(),
            key=lambda x: float(x[1].get("net_profit_usdt", x[1].get("realized_pnl_net_usdt", 0.0))),
            reverse=True
        )
        top_symbols = {sym for sym, _ in sorted_coins[:self.exclude_top_n]}
        return symbol in top_symbols

    def check(self, side: str, indicators: Optional[Dict[str, Any]] = None, **kwargs) -> bool:
        if not self.is_active:
            return True

        symbol = kwargs.get("symbol") or (indicators or {}).get("symbol")
        if not symbol:
            return True

        stats = self._get_coin_stats(symbol)
        grid_net = float(stats.get("net_profit_usdt", stats.get("realized_pnl_net_usdt", 0.0)))

        if self.mode in ("ALPHA_ONLY", "OUTSIDERS_ONLY"):
            # Разрешено входить только если на монете идет трендовый вынос против сетки (Net <= 0)
            passed = grid_net <= self.max_grid_net
            if not passed:
                log(
                    f"[GRID_NET_FILTER] [{symbol}][{side}] Вход заблокирован: монета во флэтовом коридоре сетки "
                    f"(Grid Net: +{grid_net:.2f}$ > {self.max_grid_net:.2f}$)",
                    level="DEBUG", throttle_sec=60, throttle_key=f"gnf_block_{symbol}"
                )
            return passed

        elif self.mode == "EXCLUDE_TOP_CASH_COWS":
            # Запрещено входить, если монета входит в топ кормильцев сетки
            is_top = self._is_top_cash_cow(symbol)
            if is_top or grid_net > self.max_grid_net:
                log(
                    f"[GRID_NET_FILTER] [{symbol}][{side}] Вход заблокирован: топ-корова сетки "
                    f"(Grid Net: +{grid_net:.2f}$, is_top={is_top})",
                    level="DEBUG", throttle_sec=60, throttle_key=f"gnf_top_{symbol}"
                )
                return False
            return True

        return True


class EntryHTFRSIRule(BaseRule):
    """
    Институциональный фильтр экстремумов старшего таймфрейма (Daily/4H RSI Filter).
    Отсекает входы на излете тренда:
    - Для LONG: запрещает покупку при перекупленности старшего таймфрейма (RSI >= max_rsi_long, по умолчанию 70).
    - Для SHORT: запрещает продажу при перепроданности старшего таймфрейма (RSI <= min_rsi_short, по умолчанию 30).
    """

    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.is_active: bool = bool(cfg.get("is_active", False))
        self.timeframe: str = str(cfg.get("timeframe", "1d"))
        self.max_rsi_long: float = float(cfg.get("max_rsi_long", 70.0))
        self.min_rsi_short: float = float(cfg.get("min_rsi_short", 30.0))
        self.indicator_key: str = str(cfg.get("indicator_key", f"rsi_{self.timeframe}"))

    def check(self, side: str, indicators: Optional[Dict[str, Any]] = None, **kwargs) -> bool:
        if not self.is_active:
            return True

        ind = indicators or kwargs.get("indicators", {})
        # Поиск значения RSI старшего таймфрейма
        rsi_val = ind.get(f"{self.indicator_key}_value")
        if rsi_val is None:
            rsi_val = ind.get(self.indicator_key)
        if rsi_val is None and self.timeframe in ("1d", "daily"):
            rsi_val = ind.get("rsi_1d_value", ind.get("rsi_1d"))
        if rsi_val is None and self.timeframe in ("4h", "240m"):
            rsi_val = ind.get("rsi_4h_value", ind.get("rsi_4h"))

        # Если RSI старшего таймфрейма недоступен или нестабилен, не блокируем
        if rsi_val is None or not isinstance(rsi_val, (int, float)):
            return True

        if side == "LONG":
            if rsi_val >= self.max_rsi_long:
                log(
                    f"[HTF_RSI_FILTER] [{kwargs.get('symbol', 'SYM')}][LONG] Блокировка: "
                    f"RSI_{self.timeframe} = {rsi_val:.1f} >= {self.max_rsi_long}",
                    level="DEBUG", throttle_sec=30
                )
                return False
        elif side == "SHORT":
            if rsi_val <= self.min_rsi_short:
                log(
                    f"[HTF_RSI_FILTER] [{kwargs.get('symbol', 'SYM')}][SHORT] Блокировка: "
                    f"RSI_{self.timeframe} = {rsi_val:.1f} <= {self.min_rsi_short}",
                    level="DEBUG", throttle_sec=30
                )
                return False

        return True


class EntryPortfolioModeFilterRule(BaseRule):
    """
    Фильтр допуска монет на базе активного режима портфеля (PortfolioMode):
    - FOR_GRID_ONLY: допуск только кэш-коров сетки (отсекает волатильные ракеты).
    - FOR_GRIDE_FIRSTABLE: допуск стабильных монет с нулевой просадкой импульсника.
    - FOR_TRENDH_ONLY: допуск проверенных трендовых лидеров с высоким винрейтом.
    - FOR_TRENDH_FIRSTABLE: допуск монет с положительным совокупным PnL (Combined Net >= 0).
    """

    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.is_active: bool = bool(cfg.get("is_active", False))
        self.mode: str = str(cfg.get("mode", "FOR_TRENDH_FIRSTABLE"))
        self.allowed_symbols: List[str] = list(cfg.get("allowed_symbols", []))

    def check(self, side: str, indicators: Optional[Dict[str, Any]] = None, **kwargs) -> bool:
        if not self.is_active:
            return True

        symbol = kwargs.get("symbol") or (indicators or {}).get("symbol")
        if not symbol:
            return True

        if self.allowed_symbols and symbol not in self.allowed_symbols:
            return False

        return True
