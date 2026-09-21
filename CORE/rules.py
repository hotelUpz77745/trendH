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
    """Правило входа по направлению тренда (базовый таймфрейм или HTF)."""
    def __init__(self, cfg: Dict[str, Any], indicator_key: str = "trend"):
        self.cfg, self.indicator_key = cfg, indicator_key
        self.is_active, self.trend_positive = bool(cfg.get("is_active", False)), bool(cfg.get("trend_positive", True))
        self.long_cond, self.short_cond = str(cfg.get("long_cond", "UP")), str(cfg.get("short_cond", "DOWN"))

    def check(self, side: str, indicators: Optional[Dict[str, Any]] = None, **kwargs) -> bool:
        if not self.is_active:
            return True
        trend = (indicators or kwargs.get("indicators", {})).get(self.indicator_key, kwargs.get(self.indicator_key, kwargs.get("trend")))
        if not trend or trend == "UNSTABLE":
            return False
        return (trend == self.long_cond if self.trend_positive else trend != self.short_cond) if side == "LONG" else ((trend == self.short_cond if self.trend_positive else trend != self.long_cond) if side == "SHORT" else False)


class EntryRSIRule(BaseRule):
    """Правило входа по осциллятору RSI (вхождение в диапазон импульса)."""
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg, self.is_active = cfg, bool(cfg.get("is_active", False))
        self.conditions = cfg.get("conditions", {})
        self.long_cond, self.short_cond = str(cfg.get("long_cond", "ENTER_LONG")), str(cfg.get("short_cond", "ENTER_SHORT"))

    def check(self, side: str, indicators: Optional[Dict[str, Any]] = None, **kwargs) -> bool:
        if not self.is_active:
            return True
        indicators = indicators or kwargs.get("indicators", {})
        rsi_val = indicators.get("rsi_value", kwargs.get("rsi_value"))
        if self.conditions and rsi_val is not None:
            from utils import eval_condition
            expr = self.conditions.get(self.long_cond if side == "LONG" else self.short_cond)
            return eval_condition(expr, rsi_val) if expr else False
        rsi = indicators.get("rsi", kwargs.get("rsi", []))
        if not rsi or "UNSTABLE" in rsi:
            return False
        return (self.long_cond in rsi) if side == "LONG" else (self.short_cond in rsi)


class EntryRSIWaterlineRule(BaseRule):
    """Правило входа по пересечению ватерлинии RSI (CROSS_UP / CROSS_DOWN)."""
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg, self.is_active = cfg, bool(cfg.get("is_active", False))
        self.long_cond, self.short_cond = str(cfg.get("long_cond", "CROSS_UP")), str(cfg.get("short_cond", "CROSS_DOWN"))

    def check(self, side: str, indicators: Optional[Dict[str, Any]] = None, **kwargs) -> bool:
        if not self.is_active:
            return True
        wl = (indicators or kwargs.get("indicators", {})).get("rsi_waterline50", kwargs.get("rsi_waterline50", []))
        return (self.long_cond in wl) if (wl and "UNSTABLE" not in wl and side == "LONG") else ((self.short_cond in wl) if (wl and "UNSTABLE" not in wl and side == "SHORT") else False)


class EntrySRLevelsRule(BaseRule):
    """Правило входа по пробою уровней поддержки/сопротивления (BREAKOUT_LONG / BREAKOUT_SHORT)."""
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg, self.is_active = cfg, bool(cfg.get("is_active", False))
        self.long_cond, self.short_cond = str(cfg.get("long_cond", "BREAKOUT_LONG")), str(cfg.get("short_cond", "BREAKOUT_SHORT"))

    def check(self, side: str, indicators: Optional[Dict[str, Any]] = None, **kwargs) -> bool:
        if not self.is_active:
            return True
        sr = (indicators or kwargs.get("indicators", {})).get("sr_levels", kwargs.get("sr_levels", []))
        return (self.long_cond in sr) if (sr and "UNSTABLE" not in sr and side == "LONG") else ((self.short_cond in sr) if (sr and "UNSTABLE" not in sr and side == "SHORT") else False)


class EntryEMACrossRule(BaseRule):
    """Правило входа по боевому EMA-кроссоверу с импульсом (CROSS_UP / CROSS_DOWN)."""
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg, self.is_active = cfg, bool(cfg.get("is_active", False))
        self.long_cond, self.short_cond = str(cfg.get("long_cond", "CROSS_UP")), str(cfg.get("short_cond", "CROSS_DOWN"))

    def check(self, side: str, indicators: Optional[Dict[str, Any]] = None, **kwargs) -> bool:
        if not self.is_active:
            return True
        ec = (indicators or kwargs.get("indicators", {})).get("ema_cross", kwargs.get("ema_cross", []))
        return (self.long_cond in ec) if (ec and "UNSTABLE" not in ec and side == "LONG") else ((self.short_cond in ec) if (ec and "UNSTABLE" not in ec and side == "SHORT") else False)


class EntryVolumeFilterRule(BaseRule):
    """Правило фильтрации всплеска объема (VOLF_PASSED)."""
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg, self.is_active = cfg, bool(cfg.get("is_active", False))
        self.long_cond, self.short_cond = str(cfg.get("long_cond", "VOLF_PASSED")), str(cfg.get("short_cond", "VOLF_PASSED"))

    def check(self, side: str, indicators: Optional[Dict[str, Any]] = None, **kwargs) -> bool:
        if not self.is_active:
            return True
        vf = (indicators or kwargs.get("indicators", {})).get("vol_filter", kwargs.get("vol_filter", []))
        return (self.long_cond in vf) if (vf and "UNSTABLE" not in vf and side == "LONG") else ((self.short_cond in vf) if (vf and "UNSTABLE" not in vf and side == "SHORT") else False)


class EntryDeltaHarvesterRule(BaseRule):
    """Правило входа Delta Harvester: подхватывает стресс сетки с фильтром Momentum Guard."""
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg, self.is_active = cfg, bool(cfg.get("is_active", False))
        self.require_momentum, self.min_rsi = bool(cfg.get("require_momentum", True)), float(cfg.get("min_rsi", 48.0))
        from cron_integration import EntryGridStressRule
        self.stress_rule = EntryGridStressRule({
            "is_active": self.is_active,
            "min_volume_ratio": float(cfg.get("min_volume_ratio", 0.40)),
            "min_filled_level": int(cfg.get("min_filled_level", 2)),
            "extreme_only": bool(cfg.get("extreme_only", False)),
            "require_shock": bool(cfg.get("require_shock", False)),
            "max_fill_duration_sec": cfg.get("max_fill_duration_sec")
        })

    def check(self, side: str, indicators: Optional[Dict[str, Any]] = None, **kwargs) -> bool:
        if not self.is_active:
            return True
        if not self.stress_rule.check(side, indicators=indicators, **kwargs):
            return False
        if self.require_momentum and indicators:
            candles = indicators.get("candles_5m", indicators.get("candles", []))
            if candles and isinstance(candles, list) and isinstance(candles[-1], dict):
                op, cl = float(candles[-1].get("open", 0.0)), float(candles[-1].get("close", 0.0))
                if op > 0 and cl > 0 and ((side == "LONG" and cl < op) or (side == "SHORT" and cl > op)):
                    return False
            rsi = indicators.get("rsi_value")
            if rsi is not None and isinstance(rsi, (int, float)):
                if (side == "LONG" and rsi < self.min_rsi) or (side == "SHORT" and rsi > (100.0 - self.min_rsi)):
                    return False
        return True


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
            if base_key in ("trend", "trend_htf") or base_key.startswith("trend"):
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
            elif base_key in ("delta_harvester", "grid_delta_harvester"):
                self.rules.append(EntryDeltaHarvesterRule(val))
            elif base_key == "hvh":
                from CORE.indicators.hvh import EntryHVHRule
                self.rules.append(EntryHVHRule(val))

    def check_signal(self, side: str, indicators: Dict[str, Any]) -> bool:
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
        self.cfg, self.is_active = cfg, bool(cfg.get("is_active", False))
        self.long_exit_trends = list(cfg.get("long_exit_trends", []))
        self.short_exit_trends = list(cfg.get("short_exit_trends", []))

    def check(self, side: str, trend: str, **kwargs) -> bool:
        if not self.is_active:
            return False
        return (trend in self.long_exit_trends) if side == "LONG" else ((trend in self.short_exit_trends) if side == "SHORT" else False)


class ExitTakeProfitRule(BaseRule):
    """Правило выхода по тейк-профиту с учетом комиссии и проскальзывания."""
    def __init__(self, cfg: Dict[str, Any], analytics_cfg: Dict[str, Any], get_slippage_ratio_fn: Callable[[str], float]):
        self.cfg, self.analytics_cfg, self.value, self.get_slippage_ratio_fn = cfg, analytics_cfg, cfg.get("value"), get_slippage_ratio_fn

    def check(self, side: str, symbol: str, open_price: float, current_price: float, **kwargs) -> bool:
        if self.value is None or open_price <= 0 or current_price <= 0:
            return False
        cost = (self.analytics_cfg.get("taker_fee_ratio", 0.0) + self.get_slippage_ratio_fn(symbol)) * 2
        return (((current_price - open_price) if side == "LONG" else (open_price - current_price)) / open_price - cost) >= self.value


class ExitStopLossRule(BaseRule):
    """Правило выхода по стоп-лоссу с учетом комиссии и проскальзывания."""
    def __init__(self, cfg: Dict[str, Any], analytics_cfg: Dict[str, Any], get_slippage_ratio_fn: Callable[[str], float]):
        self.cfg, self.analytics_cfg, self.value, self.get_slippage_ratio_fn = cfg, analytics_cfg, cfg.get("value"), get_slippage_ratio_fn

    def check(self, side: str, symbol: str, open_price: float, current_price: float, **kwargs) -> bool:
        if self.value is None or open_price <= 0 or current_price <= 0:
            return False
        cost = (self.analytics_cfg.get("taker_fee_ratio", 0.0) + self.get_slippage_ratio_fn(symbol)) * 2
        return (((current_price - open_price) if side == "LONG" else (open_price - current_price)) / open_price - cost) <= -abs(self.value)


class ExitRSIRule(BaseRule):
    """Правило выхода по RSI."""
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg, self.is_active = cfg, bool(cfg.get("is_active", False))
        self.long_exit_rsi, self.long_loss_rsi = cfg.get("long_exit_rsi"), cfg.get("long_loss_rsi")
        self.short_exit_rsi, self.short_loss_rsi = cfg.get("short_exit_rsi"), cfg.get("short_loss_rsi")
        self.long_cond, self.short_cond = cfg.get("long_cond", "EXIT_LONG"), cfg.get("short_cond", "EXIT_SHORT")

    def check(self, side: str, indicators: Optional[Dict[str, Any]] = None, **kwargs) -> bool:
        if not self.is_active:
            return False
        ind = indicators or kwargs.get("indicators", {})
        rsi_val, rsi_states = ind.get("rsi_value", kwargs.get("rsi_value")), ind.get("rsi", kwargs.get("rsi", []))
        if side == "LONG":
            return (self.long_cond in rsi_states) or (rsi_val is not None and ((self.long_exit_rsi is not None and rsi_val >= self.long_exit_rsi) or (self.long_loss_rsi is not None and rsi_val <= self.long_loss_rsi)))
        elif side == "SHORT":
            return (self.short_cond in rsi_states) or (rsi_val is not None and ((self.short_exit_rsi is not None and rsi_val <= self.short_exit_rsi) or (self.short_loss_rsi is not None and rsi_val >= self.short_loss_rsi)))
        return False



class ExitTimeStopRule(BaseRule):
    """Правило выхода по времени удержания сделки с поддержкой порога min_pnl_ratio."""
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg, self.is_active = cfg, bool(cfg.get("is_active", False))
        self.max_seconds, self.min_pnl_ratio = float(cfg.get("max_seconds", 1500.0)), cfg.get("min_pnl_ratio")

    def check(self, side: str, open_time_ms: Optional[int] = None, open_price: float = 0.0, current_price: float = 0.0, **kwargs) -> bool:
        if not self.is_active or not open_time_ms or open_time_ms <= 0:
            return False
        import time
        if ((int(time.time() * 1000) - open_time_ms) / 1000.0) < self.max_seconds:
            return False
        if self.min_pnl_ratio is not None and open_price > 0 and current_price > 0:
            pnl = ((current_price - open_price) / open_price) if side == "LONG" else ((open_price - current_price) / open_price)
            return pnl < self.min_pnl_ratio
        return True


class ExitBreakevenRatchetRule(BaseRule):
    """
    Breakeven Ratchet & Dynamic Trailing:
    При достижении trigger_ratio (+2.5%) переносит стоп в безубыток (+buffer_ratio).
    Если указан trail_ratio (например, 0.018 = 1.8%), динамически подтягивает стоп за локальным максимумом/минимумом,
    гарантируя, что стоп не опустится ниже уровня безубытка.
    """
    def __init__(self, cfg: Dict[str, Any], analytics_cfg: Optional[Dict[str, Any]] = None):
        self.cfg, self.is_active = cfg, bool(cfg.get("is_active", False))
        self.trigger_ratio = float(cfg.get("trigger_ratio", 0.025))
        self.trail_ratio = float(cfg["trail_ratio"]) if cfg.get("trail_ratio") is not None else None
        fee = (analytics_cfg.get("taker_fee_ratio", 0.0006) * 2) if analytics_cfg else 0.0012
        self.buffer_ratio = float(cfg.get("buffer_ratio", fee))

    def check(self, side: str, open_price: float = 0.0, current_price: float = 0.0, **kwargs) -> bool:
        if not self.is_active or open_price <= 0 or current_price <= 0:
            return False
        highest_price = kwargs.get("highest_price") or current_price
        lowest_price = kwargs.get("lowest_price") or current_price
        if side == "LONG":
            peak_gain = (highest_price - open_price) / open_price
            if peak_gain >= self.trigger_ratio:
                be_stop = open_price * (1.0 + self.buffer_ratio)
                trail_stop = highest_price * (1.0 - self.trail_ratio) if self.trail_ratio is not None else be_stop
                return current_price <= max(be_stop, trail_stop)
        elif side == "SHORT":
            peak_gain = (open_price - lowest_price) / open_price
            if peak_gain >= self.trigger_ratio:
                be_stop = open_price * (1.0 - self.buffer_ratio)
                trail_stop = lowest_price * (1.0 + self.trail_ratio) if self.trail_ratio is not None else be_stop
                return current_price >= min(be_stop, trail_stop)
        return False


class ExitProfitStagnationRule(BaseRule):
    """
    Profit Stagnation & Breakeven Lock Exit:
    1. Breakeven Lock: при достижении be_trigger_ratio (+2.8%) переносит стоп в безубыток (+be_buffer_ratio, e.g. +0.3%).
       Стоп фиксируется и не трейлится вверх, защищая от выбивания на микро-откатах.
    2. Profit Stagnation: если текущая прибыль >= min_profit_ratio (+5.0%),
       и в течение stagnation_seconds (1800с = 30 мин) нет прогресса >= progress_threshold (+0.5%),
       позиция закрывается по рынку для фиксации профита на вершине.
    """
    def __init__(self, cfg: Dict[str, Any], analytics_cfg: Optional[Dict[str, Any]] = None):
        self.cfg, self.is_active = cfg, bool(cfg.get("is_active", False))
        self.be_trigger_ratio = float(cfg.get("be_trigger_ratio", 0.028))
        fee = (analytics_cfg.get("taker_fee_ratio", 0.0006) * 2) if analytics_cfg else 0.0012
        self.be_buffer_ratio, self.min_profit_ratio = float(cfg.get("be_buffer_ratio", fee)), float(cfg.get("min_profit_ratio", 0.05))
        self.stagnation_seconds, self.progress_threshold = float(cfg.get("stagnation_seconds", 1800.0)), float(cfg.get("progress_threshold", 0.005))
        self.peaks: Dict[tuple, Dict[str, float]] = {}

    def check(self, side: str, symbol: str = "", open_price: float = 0.0, current_price: float = 0.0, **kwargs) -> bool:
        if not self.is_active or open_price <= 0 or current_price <= 0:
            return False
        highest_price, lowest_price = kwargs.get("highest_price") or current_price, kwargs.get("lowest_price") or current_price
        key = (symbol or "SYM", side)

        # 1. Breakeven Lock
        if side == "LONG" and ((highest_price - open_price) / open_price) >= self.be_trigger_ratio:
            if current_price <= open_price * (1.0 + self.be_buffer_ratio):
                self.peaks.pop(key, None)
                return True
        elif side == "SHORT" and ((open_price - lowest_price) / open_price) >= self.be_trigger_ratio:
            if current_price >= open_price * (1.0 - self.be_buffer_ratio):
                self.peaks.pop(key, None)
                return True

        # 2. Profit Stagnation Exit
        import time
        now = kwargs.get("current_time") or time.time()
        curr_gain = ((current_price - open_price) / open_price) if side == "LONG" else ((open_price - current_price) / open_price)

        if curr_gain >= self.min_profit_ratio:
            ext_price = highest_price if side == "LONG" else lowest_price
            if key not in self.peaks:
                self.peaks[key] = {"peak": ext_price, "time": now}
            else:
                entry = self.peaks[key]
                progress = (ext_price >= entry["peak"] * (1.0 + self.progress_threshold)) if side == "LONG" else (ext_price <= entry["peak"] * (1.0 - self.progress_threshold))
                if progress:
                    entry["peak"], entry["time"] = ext_price, now
                elif (now - entry["time"]) >= self.stagnation_seconds:

                    self.peaks.pop(key, None)
                    return True
        else:
            self.peaks.pop(key, None)

        return False


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
            elif base_key in ("breakeven_ratchet", "be_ratchet"):
                self.rules.append(ExitBreakevenRatchetRule(val, analytics_cfg))
            elif base_key in ("profit_stagnation", "stagnation_exit"):
                self.rules.append(ExitProfitStagnationRule(val, analytics_cfg))
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
                **kwargs
            ):
                self.last_exit_reason = rule.__class__.__name__
                return True
        return False

