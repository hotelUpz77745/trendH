# ============================================================
# FILE: rules.py - Strategy Pattern Rules Engine
# ============================================================
from abc import ABC, abstractmethod
from typing import Dict, Any, Callable, Optional, List
from c_log import log


class BaseRule(ABC):
    """Базовый абстрактный класс торгового правила."""
    @abstractmethod
    def check(self, side: str, **kwargs) -> bool:
        pass


# ==========================================
# ENTRY RULES (All active must pass for signal)
# ==========================================
class EntryTrendRule(BaseRule):
    """
    Правило входа по направлению тренда (базовый таймфрейм или HTF).
    Поддерживает прямую проверку (trend_positive=True) и от обратного (False).
    """

    def __init__(self, cfg: Dict[str, Any], indicator_key: str = "trend"):
        self.cfg = cfg
        self.indicator_key = indicator_key
        self.is_active: bool = bool(cfg.get("is_active", False))
        self.trend_positive: bool = bool(cfg.get("trend_positive", True))
        self.long_cond: str = str(cfg.get("long_cond", "UP"))
        self.short_cond: str = str(cfg.get("short_cond", "DOWN"))

    def check(self, side: str, indicators: Optional[Dict[str, Any]] = None, **kwargs) -> bool:
        if not self.is_active:
            return True

        indicators = indicators or kwargs.get("indicators", {})
        trend = indicators.get(self.indicator_key, kwargs.get(self.indicator_key, kwargs.get("trend")))

        if not trend or trend == "UNSTABLE":
            return False

        if side == "LONG":
            if self.trend_positive:
                return trend == self.long_cond
            else:
                return trend != self.short_cond
        elif side == "SHORT":
            if self.trend_positive:
                return trend == self.short_cond
            else:
                return trend != self.long_cond
        return False


class EntryRSIRule(BaseRule):
    """Правило входа по осциллятору RSI (вхождение в диапазон импульса)."""

    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.is_active: bool = bool(cfg.get("is_active", False))

    def check(self, side: str, indicators: Optional[Dict[str, Any]] = None, **kwargs) -> bool:
        if not self.is_active:
            return True

        indicators = indicators or kwargs.get("indicators", {})
        rsi = indicators.get("rsi", kwargs.get("rsi", []))

        if not rsi or "UNSTABLE" in rsi:
            return False

        if side == "LONG":
            return "ENTER_LONG" in rsi
        elif side == "SHORT":
            return "ENTER_SHORT" in rsi

        return False


class EntryRSIWaterlineRule(BaseRule):
    """Правило входа по пересечению ватерлинии RSI (CROSS_UP / CROSS_DOWN)."""

    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.is_active: bool = bool(cfg.get("is_active", False))
        self.long_cond: str = str(cfg.get("long_cond", "CROSS_UP"))
        self.short_cond: str = str(cfg.get("short_cond", "CROSS_DOWN"))

    def check(self, side: str, indicators: Optional[Dict[str, Any]] = None, **kwargs) -> bool:
        if not self.is_active:
            return True

        indicators = indicators or kwargs.get("indicators", {})
        wl_states = indicators.get("rsi_waterline50", kwargs.get("rsi_waterline50", []))

        if not wl_states or "UNSTABLE" in wl_states:
            return False

        if side == "LONG":
            return self.long_cond in wl_states
        elif side == "SHORT":
            return self.short_cond in wl_states

        return False


class EntrySRLevelsRule(BaseRule):
    """Правило входа по пробою уровней поддержки/сопротивления (BREAKOUT_LONG / BREAKOUT_SHORT)."""

    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.is_active: bool = bool(cfg.get("is_active", False))
        self.long_cond: str = str(cfg.get("long_cond", "BREAKOUT_LONG"))
        self.short_cond: str = str(cfg.get("short_cond", "BREAKOUT_SHORT"))

    def check(self, side: str, indicators: Optional[Dict[str, Any]] = None, **kwargs) -> bool:
        if not self.is_active:
            return True

        indicators = indicators or kwargs.get("indicators", {})
        sr_states = indicators.get("sr_levels", kwargs.get("sr_levels", []))

        if not sr_states or "UNSTABLE" in sr_states:
            return False

        if side == "LONG":
            return self.long_cond in sr_states
        elif side == "SHORT":
            return self.short_cond in sr_states

        return False


class EntryEMACrossRule(BaseRule):
    """Правило входа по боевому EMA-кроссоверу с импульсом (CROSS_UP / CROSS_DOWN)."""

    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.is_active: bool = bool(cfg.get("is_active", False))
        self.long_cond: str = str(cfg.get("long_cond", "CROSS_UP"))
        self.short_cond: str = str(cfg.get("short_cond", "CROSS_DOWN"))

    def check(self, side: str, indicators: Optional[Dict[str, Any]] = None, **kwargs) -> bool:
        if not self.is_active:
            return True

        indicators = indicators or kwargs.get("indicators", {})
        ec_states = indicators.get("ema_cross", kwargs.get("ema_cross", []))

        if not ec_states or "UNSTABLE" in ec_states:
            return False

        if side == "LONG":
            return self.long_cond in ec_states
        elif side == "SHORT":
            return self.short_cond in ec_states

        return False


class EntryVolumeFilterRule(BaseRule):
    """Правило фильтрации всплеска объема (VOLF_PASSED)."""

    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.is_active: bool = bool(cfg.get("is_active", False))
        self.long_cond: str = str(cfg.get("long_cond", "VOLF_PASSED"))
        self.short_cond: str = str(cfg.get("short_cond", "VOLF_PASSED"))

    def check(self, side: str, indicators: Optional[Dict[str, Any]] = None, **kwargs) -> bool:
        if not self.is_active:
            return True

        indicators = indicators or kwargs.get("indicators", {})
        vol_states = indicators.get("vol_filter", kwargs.get("vol_filter", []))

        if not vol_states or "UNSTABLE" in vol_states:
            return False

        if side == "LONG":
            return self.long_cond in vol_states
        elif side == "SHORT":
            return self.short_cond in vol_states

        return False


class EntrySignalEngine:
    """
    Движок сигналов на вход.
    Агрегирует все активные правила входа; сигнал генерируется только при успехе ВСЕХ правил.
    """

    def __init__(self, enter_rules_cfg: Dict[str, Any]):
        self.rules: List[BaseRule] = []

        if "trend" in enter_rules_cfg:
            self.rules.append(EntryTrendRule(enter_rules_cfg["trend"], indicator_key="trend"))

        if "trend_htf" in enter_rules_cfg:
            self.rules.append(EntryTrendRule(enter_rules_cfg["trend_htf"], indicator_key="trend_htf"))

        # Регистрация дополнительных индикаторов тренда при наличии
        for key, val in enter_rules_cfg.items():
            if key.startswith("trend") and key not in ("trend", "trend_htf") and isinstance(val, dict):
                self.rules.append(EntryTrendRule(val, indicator_key=key))

        if "rsi" in enter_rules_cfg:
            self.rules.append(EntryRSIRule(enter_rules_cfg["rsi"]))

        if "rsi_waterline50" in enter_rules_cfg:
            self.rules.append(EntryRSIWaterlineRule(enter_rules_cfg["rsi_waterline50"]))

        if "sr_levels" in enter_rules_cfg:
            self.rules.append(EntrySRLevelsRule(enter_rules_cfg["sr_levels"]))

        if "ema_cross" in enter_rules_cfg:
            self.rules.append(EntryEMACrossRule(enter_rules_cfg["ema_cross"]))

        if "vol_filter" in enter_rules_cfg:
            self.rules.append(EntryVolumeFilterRule(enter_rules_cfg["vol_filter"]))

    def check_signal(self, side: str, indicators: Dict[str, Any]) -> bool:
        """
        Проверяет все правила входа.
        Возвращает True только если ВСЕ активные правила возвращают True.
        """
        for rule in self.rules:
            if not rule.check(side, indicators=indicators):
                return False
        return True


# ==========================================
# EXIT RULES (Any one passing triggers exit)
# ==========================================
class ExitTrendReversalRule(BaseRule):
    """Правило выхода по изменению тренда (например, при переходе в FLAT или развороте)."""

    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.is_active: bool = bool(cfg.get("is_active", False))
        self.long_exit_trends: List[str] = list(cfg.get("long_exit_trends", []))
        self.short_exit_trends: List[str] = list(cfg.get("short_exit_trends", []))

    def check(self, side: str, trend: str, **kwargs) -> bool:
        if not self.is_active:
            return False
        if side == "LONG" and trend in self.long_exit_trends:
            return True
        if side == "SHORT" and trend in self.short_exit_trends:
            return True
        return False


class ExitTakeProfitRule(BaseRule):
    """
    Правило выхода по тейк-профиту с учетом комиссии и проскальзывания.
    """

    def __init__(
        self,
        cfg: Dict[str, Any],
        analytics_cfg: Dict[str, Any],
        get_slippage_ratio_fn: Callable[[str], float]
    ):
        self.cfg = cfg
        self.analytics_cfg = analytics_cfg
        self.value: Optional[float] = cfg.get("value")
        self.get_slippage_ratio_fn = get_slippage_ratio_fn

    def check(self, side: str, symbol: str, open_price: float, current_price: float, **kwargs) -> bool:
        if self.value is None or open_price <= 0 or current_price <= 0:
            return False

        fee_ratio = self.analytics_cfg.get("taker_fee_ratio", 0.0) * 2
        slippage_ratio = self.get_slippage_ratio_fn(symbol) * 2
        fee_slip_ratio = fee_ratio + slippage_ratio

        if side == "LONG":
            pnl_ratio = (current_price - open_price) / open_price - fee_slip_ratio
        else:
            pnl_ratio = (open_price - current_price) / open_price - fee_slip_ratio

        if pnl_ratio >= self.value:
            log(f"[{symbol}][TAKE PROFIT] PnL {pnl_ratio * 100:.2f}% >= {self.value * 100:.2f}%", level="DEBUG")
            return True

        return False


class ExitStopLossRule(BaseRule):
    """
    Правило выхода по стоп-лоссу с учетом комиссии и проскальзывания.
    """

    def __init__(
        self,
        cfg: Dict[str, Any],
        analytics_cfg: Dict[str, Any],
        get_slippage_ratio_fn: Callable[[str], float]
    ):
        self.cfg = cfg
        self.analytics_cfg = analytics_cfg
        self.value: Optional[float] = cfg.get("value")
        self.get_slippage_ratio_fn = get_slippage_ratio_fn

    def check(self, side: str, symbol: str, open_price: float, current_price: float, **kwargs) -> bool:
        if self.value is None or open_price <= 0 or current_price <= 0:
            return False

        fee_ratio = self.analytics_cfg.get("taker_fee_ratio", 0.0) * 2
        slippage_ratio = self.get_slippage_ratio_fn(symbol) * 2
        fee_slip_ratio = fee_ratio + slippage_ratio

        if side == "LONG":
            pnl_ratio = (current_price - open_price) / open_price - fee_slip_ratio
        else:
            pnl_ratio = (open_price - current_price) / open_price - fee_slip_ratio

        threshold = -abs(self.value)
        if pnl_ratio <= threshold:
            log(f"[{symbol}][STOP LOSS] PnL {pnl_ratio * 100:.2f}% <= {threshold * 100:.2f}%", level="DEBUG")
            return True

        return False


class ExitRSIRule(BaseRule):
    """
    Правило выхода по RSI:
    - Перекупленность / перепроданность (long_exit_rsi, short_exit_rsi)
    - Потеря импульса (long_loss_rsi, short_loss_rsi)
    - Кастомные строковые условия (long_cond, short_cond)
    """

    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.is_active: bool = bool(cfg.get("is_active", False))
        self.long_exit_rsi: Optional[float] = cfg.get("long_exit_rsi")
        self.long_loss_rsi: Optional[float] = cfg.get("long_loss_rsi")
        self.short_exit_rsi: Optional[float] = cfg.get("short_exit_rsi")
        self.short_loss_rsi: Optional[float] = cfg.get("short_loss_rsi")
        self.long_cond: Optional[str] = cfg.get("long_cond", "EXIT_LONG")
        self.short_cond: Optional[str] = cfg.get("short_cond", "EXIT_SHORT")

    def check(self, side: str, indicators: Optional[Dict[str, Any]] = None, **kwargs) -> bool:
        if not self.is_active:
            return False

        indicators = indicators or kwargs.get("indicators", {})
        rsi_val = indicators.get("rsi_value", kwargs.get("rsi_value"))
        rsi_states = indicators.get("rsi", kwargs.get("rsi", []))

        if side == "LONG":
            if self.long_cond and self.long_cond in rsi_states:
                return True
            if rsi_val is not None:
                if self.long_exit_rsi is not None and rsi_val >= self.long_exit_rsi:
                    return True
                if self.long_loss_rsi is not None and rsi_val <= self.long_loss_rsi:
                    return True
        elif side == "SHORT":
            if self.short_cond and self.short_cond in rsi_states:
                return True
            if rsi_val is not None:
                if self.short_exit_rsi is not None and rsi_val <= self.short_exit_rsi:
                    return True
                if self.short_loss_rsi is not None and rsi_val >= self.short_loss_rsi:
                    return True

        return False


class ExitTimeStopRule(BaseRule):
    """Правило выхода по истечению времени удержания сделки (Time-based Stop)."""

    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.is_active: bool = bool(cfg.get("is_active", False))
        self.max_seconds: float = float(cfg.get("max_seconds", 1500.0))

    def check(self, side: str, open_time_ms: Optional[int] = None, **kwargs) -> bool:
        if not self.is_active or not open_time_ms or open_time_ms <= 0:
            return False
        import time
        now_ms = int(time.time() * 1000)
        return ((now_ms - open_time_ms) / 1000.0) >= self.max_seconds


class ExitSignalEngine:
    """
    Движок сигналов на выход.
    Агрегирует все активные правила выхода; сигнал генерируется при срабатывании ХОТЯ БЫ ОДНОГО правила.
    """

    def __init__(
        self,
        exit_rules_cfg: Dict[str, Any],
        analytics_cfg: Dict[str, Any],
        get_slippage_ratio_fn: Callable[[str], float]
    ):
        self.rules: List[BaseRule] = []
        if "trend_reversal" in exit_rules_cfg:
            self.rules.append(ExitTrendReversalRule(exit_rules_cfg["trend_reversal"]))
        if "rsi" in exit_rules_cfg:
            self.rules.append(ExitRSIRule(exit_rules_cfg["rsi"]))
        if "take_profit_ratio" in exit_rules_cfg:
            self.rules.append(ExitTakeProfitRule(exit_rules_cfg["take_profit_ratio"], analytics_cfg, get_slippage_ratio_fn))
        if "stop_loss_ratio" in exit_rules_cfg:
            self.rules.append(ExitStopLossRule(exit_rules_cfg["stop_loss_ratio"], analytics_cfg, get_slippage_ratio_fn))
        if "time_stop" in exit_rules_cfg:
            self.rules.append(ExitTimeStopRule(exit_rules_cfg["time_stop"]))

    def check_signal(
        self,
        side: str,
        symbol: str,
        trend: str,
        open_price: float,
        current_price: float,
        indicators: Optional[Dict[str, Any]] = None,
        open_time_ms: Optional[int] = None
    ) -> bool:
        """
        Проверяет правила выхода.
        Возвращает True, если ХОТЯ БЫ ОДНО активное правило сработало.
        """
        indicators = indicators or {}
        for rule in self.rules:
            if rule.check(
                side,
                symbol=symbol,
                trend=trend,
                open_price=open_price,
                current_price=current_price,
                indicators=indicators,
                rsi_value=indicators.get("rsi_value"),
                rsi=indicators.get("rsi", []),
                open_time_ms=open_time_ms
            ):
                return True
        return False
