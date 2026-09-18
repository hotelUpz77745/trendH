# ============================================================
# FILE: rules.py - Strategy Pattern Rules Engine
# ============================================================
from abc import ABC, abstractmethod
from typing import Dict, Any, Callable, Optional, List
from c_log import log


class BaseRule(ABC):
    """Базовый абстрактный класс торгового правила."""
    @abstractmethod
    def check(self, *args, **kwargs) -> bool:
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
        self.conditions: Dict[str, str] = cfg.get("conditions", {})
        self.long_cond: str = str(cfg.get("long_cond", "ENTER_LONG"))
        self.short_cond: str = str(cfg.get("short_cond", "ENTER_SHORT"))

    def check(self, side: str, indicators: Optional[Dict[str, Any]] = None, **kwargs) -> bool:
        if not self.is_active:
            return True
        indicators = indicators or kwargs.get("indicators", {})
        rsi_val = indicators.get("rsi_value", kwargs.get("rsi_value"))
        if self.conditions and rsi_val is not None:
            from utils import eval_condition
            cond_key = self.long_cond if side == "LONG" else self.short_cond
            expr = self.conditions.get(cond_key)
            return eval_condition(expr, rsi_val) if expr else False
        rsi = indicators.get("rsi", kwargs.get("rsi", []))
        if not rsi or "UNSTABLE" in rsi:
            return False
        target_cond = self.long_cond if side == "LONG" else self.short_cond
        return target_cond in rsi


class EntryRSIWaterlineRule(BaseRule):
    """Правило входа по пересечению ватерлинии RSI (CROSS_UP / CROSS_DOWN)."""
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg, self.is_active = cfg, bool(cfg.get("is_active", False))
        self.long_cond, self.short_cond = str(cfg.get("long_cond", "CROSS_UP")), str(cfg.get("short_cond", "CROSS_DOWN"))

    def check(self, side: str, indicators: Optional[Dict[str, Any]] = None, **kwargs) -> bool:
        if not self.is_active:
            return True
        wl = (indicators or kwargs.get("indicators", {})).get("rsi_waterline50", kwargs.get("rsi_waterline50", []))
        if not wl or "UNSTABLE" in wl:
            return False
        return (self.long_cond in wl) if side == "LONG" else ((self.short_cond in wl) if side == "SHORT" else False)


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
        for key, val in enter_rules_cfg.items():
            if not isinstance(val, dict):
                continue
            base_key = key
            for suffix in ("_anti", "_reverse", "_inv"):
                if key.endswith(suffix):
                    base_key = key[:-len(suffix)]
                    break
            if base_key == "trend":
                self.rules.append(EntryTrendRule(val, indicator_key="trend"))
            elif base_key == "trend_htf":
                self.rules.append(EntryTrendRule(val, indicator_key="trend_htf"))
            elif base_key.startswith("trend"):
                self.rules.append(EntryTrendRule(val, indicator_key=base_key))
            elif base_key == "rsi":
                self.rules.append(EntryRSIRule(val))
            elif base_key == "rsi_waterline50":
                self.rules.append(EntryRSIWaterlineRule(val))
            elif base_key == "sr_levels":
                self.rules.append(EntrySRLevelsRule(val))
            elif base_key == "ema_cross":
                self.rules.append(EntryEMACrossRule(val))
            elif base_key == "vol_filter":
                self.rules.append(EntryVolumeFilterRule(val))
            elif base_key == "taker_flow":
                from CORE.indicators.squeeze_flow import EntryTakerFlowRule
                self.rules.append(EntryTakerFlowRule(val))
            elif base_key == "volatility_squeeze":
                from CORE.indicators.squeeze_flow import EntryVolatilitySqueezeRule
                self.rules.append(EntryVolatilitySqueezeRule(val))
            elif base_key == "relative_strength":
                from CORE.indicators.squeeze_flow import EntryRelativeStrengthRule
                self.rules.append(EntryRelativeStrengthRule(val))
            elif base_key in ("grid_stress", "grid_inventory_stress", "grid_stress_extreme"):
                from cron_integration import EntryGridStressRule
                self.rules.append(EntryGridStressRule(val))
            elif base_key == "hvh":
                from CORE.indicators.hvh import EntryHVHRule
                self.rules.append(EntryHVHRule(val))

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
    """Правило выхода по тейк-профиту с учетом комиссии и проскальзывания."""
    def __init__(self, cfg: Dict[str, Any], analytics_cfg: Dict[str, Any], get_slippage_ratio_fn: Callable[[str], float]):
        self.cfg, self.analytics_cfg = cfg, analytics_cfg
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
    """Правило выхода по стоп-лоссу с учетом комиссии и проскальзывания."""
    def __init__(self, cfg: Dict[str, Any], analytics_cfg: Dict[str, Any], get_slippage_ratio_fn: Callable[[str], float]):
        self.cfg, self.analytics_cfg = cfg, analytics_cfg
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
        for key, val in exit_rules_cfg.items():
            if not isinstance(val, dict):
                continue
            base_key = key
            for suffix in ("_anti", "_reverse", "_inv"):
                if key.endswith(suffix):
                    base_key = key[:-len(suffix)]
                    break
            if base_key == "trend_reversal":
                self.rules.append(ExitTrendReversalRule(val))
            elif base_key == "rsi":
                self.rules.append(ExitRSIRule(val))
            elif base_key == "take_profit_ratio":
                if val.get("value") is not None:
                    self.rules.append(ExitTakeProfitRule(val, analytics_cfg, get_slippage_ratio_fn))
            elif base_key == "stop_loss_ratio":
                if val.get("value") is not None:
                    self.rules.append(ExitStopLossRule(val, analytics_cfg, get_slippage_ratio_fn))
            elif base_key == "time_stop":
                self.rules.append(ExitTimeStopRule(val))
            elif base_key == "chandelier_exit":
                from CORE.indicators.squeeze_flow import ExitChandelierRule
                self.rules.append(ExitChandelierRule(val))
            elif base_key in ("grid_relief", "grid_tp_exit"):
                from cron_integration import ExitGridReliefRule
                self.rules.append(ExitGridReliefRule(val))
        self.last_exit_reason: str = ""

    def check_signal(
        self,
        side: str,
        symbol: str,
        trend: str,
        open_price: float,
        current_price: float,
        indicators: Optional[Dict[str, Any]] = None,
        open_time_ms: Optional[int] = None,
        **kwargs
    ) -> bool:
        """
        Проверяет правила выхода.
        Возвращает True, если ХОТЯ БЫ ОДНО активное правило сработало.
        """
        indicators = indicators or {}
        self.last_exit_reason = ""
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
                open_time_ms=open_time_ms,
                candles=indicators.get("candles_5m", indicators.get("candles")),
                highest_price=kwargs.get("highest_price"),
                lowest_price=kwargs.get("lowest_price")
            ):
                self.last_exit_reason = rule.__class__.__name__
                return True
        return False
