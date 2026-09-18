# ============================================================
# FILE: CORE/indicators/trend_osc.py
# ROLE: Trend, RSI, EMA Cross & Volume Filter indicator calculators
# ============================================================

from typing import Dict, List, Any, Optional
from CORE.native_math import NativeMath


class IndicatorsMath:
    """Чистые высокопроизводительные формулы технических индикаторов на C/LLVM."""

    @staticmethod
    def calc_ema(prices: List[float], length: int) -> List[float]:
        """Высокоскоростной расчет Exponential Moving Average (EMA) на C/LLVM."""
        return NativeMath.fast_ema(prices, length)

    @staticmethod
    def calc_rsi_series(closes: List[float], length: int = 14) -> List[float]:
        """Высокоскоростной расчет серии RSI по формуле Уайлдера на C/LLVM."""
        return NativeMath.fast_rsi_series(closes, length)

    @staticmethod
    def calc_rsi(closes: List[float], length: int = 14) -> Optional[float]:
        """Расчет последнего значения Relative Strength Index (RSI)."""
        series = NativeMath.fast_rsi_series(closes, length)
        return series[-1] if series else None


class TrendCalculator:
    """Изолированный калькулятор тренда на базе быстрой и медленной EMA."""

    def __init__(self, cfg: Dict[str, Any]):
        self.is_active: bool = bool(cfg["is_active"])
        self.timeframe: str = str(cfg["timeframe"])
        self.sma_fast: int = int(cfg["sma_fast"])
        self.sma_slow: int = int(cfg["sma_slow"])
        self.confirmation_candles: int = int(cfg["confirmation_candles"])
        self.require_rising: bool = bool(cfg["require_rising"])

    def calculate(self, closes: List[float]) -> str:
        """
        Классифицирует состояние рынка по ценам закрытия:
        - UP: быстрая EMA выше медленной на протяжении N свечей (и растет, если require_rising=True)
        - DOWN: быстрая EMA ниже медленной на протяжении N свечей (и падает, если require_rising=True)
        - FLAT: расхождение условий либо боковое движение
        - UNSTABLE: недостаточно свечей для расчета
        """
        if not self.is_active or not closes:
            return "UNSTABLE"

        ema_fast = IndicatorsMath.calc_ema(closes, self.sma_fast)
        ema_slow = IndicatorsMath.calc_ema(closes, self.sma_slow)

        if not ema_fast or not ema_slow or len(ema_fast) < self.confirmation_candles:
            return "UNSTABLE"

        ef_tail = ema_fast[-self.confirmation_candles:]
        es_tail = ema_slow[-self.confirmation_candles:]

        is_above = all(f > s for f, s in zip(ef_tail, es_tail))
        is_below = all(f < s for f, s in zip(ef_tail, es_tail))
        is_rising = all(ef_tail[i] > ef_tail[i - 1] for i in range(1, len(ef_tail)))
        is_falling = all(ef_tail[i] < ef_tail[i - 1] for i in range(1, len(ef_tail)))

        if is_above and (not self.require_rising or is_rising):
            return "UP"
        elif is_below and (not self.require_rising or is_falling):
            return "DOWN"
        else:
            return "FLAT"


class RSICalculator:
    """Изолированный калькулятор осциллятора RSI."""

    def __init__(self, cfg: Dict[str, Any]):
        self.is_active: bool = bool(cfg["is_active"])
        self.timeframe: str = str(cfg["timeframe"])
        self.window: int = int(cfg["window"])
        self.conditions: Dict[str, str] = cfg.get("conditions", {})

    def calculate(self, closes: List[float]) -> List[str]:
        if not self.is_active or not closes:
            return ["UNSTABLE"]

        raw_rsi = IndicatorsMath.calc_rsi(closes, length=self.window)
        if raw_rsi is None:
            return ["UNSTABLE"]

        from utils import eval_condition
        active_states = []
        for state_key, cond_expr in self.conditions.items():
            if cond_expr and eval_condition(cond_expr, raw_rsi):
                active_states.append(state_key)

        return active_states

    def get_raw_value(self, closes: List[float]) -> Optional[float]:
        if not self.is_active or not closes:
            return None
        return IndicatorsMath.calc_rsi(closes, length=self.window)


class RSIWaterlineCalculator:
    """Изолированный калькулятор пересечения ватерлинии RSI (напр. 50)."""

    def __init__(self, cfg: Dict[str, Any]):
        self.is_active: bool = bool(cfg.get("is_active", False))
        self.timeframe: str = str(cfg.get("timeframe", "5m"))
        self.window: int = int(cfg.get("window", 14))
        self.waterline: float = float(cfg.get("waterline", 50.0))
        self.long_cond: str = str(cfg.get("long_cond", "CROSS_UP"))
        self.short_cond: str = str(cfg.get("short_cond", "CROSS_DOWN"))

    def calculate(self, closes: List[float]) -> List[str]:
        if not self.is_active or not closes:
            return ["UNSTABLE"]

        series = IndicatorsMath.calc_rsi_series(closes, length=self.window)
        if len(series) < 2:
            return ["UNSTABLE"]

        prev_rsi = series[-2]
        curr_rsi = series[-1]

        states = []
        if prev_rsi <= self.waterline and curr_rsi > self.waterline:
            states.append("CROSS_UP")
        elif prev_rsi >= self.waterline and curr_rsi < self.waterline:
            states.append("CROSS_DOWN")

        return states


class EMACrossCalculator:
    """Изолированный калькулятор EMA-кроссовера с фильтром ускорения и импульса."""

    def __init__(self, cfg: Dict[str, Any]):
        self.is_active: bool = bool(cfg.get("is_active", False))
        self.timeframe: str = str(cfg.get("timeframe", "5m"))
        self.period1: int = int(cfg.get("period1", 9))
        self.period2: int = int(cfg.get("period2", 21))
        self.long_cond: str = str(cfg.get("long_cond", "CROSS_UP"))
        self.short_cond: str = str(cfg.get("short_cond", "CROSS_DOWN"))

    def calculate(self, closes: List[float]) -> List[str]:
        """
        Вычисляет состояние EMA-кроссовера с фильтром ускорения и импульса:
        - CROSS_UP: быстрая EMA пересекает медленную снизу вверх с нарастающим расхождением
        - CROSS_DOWN: быстрая EMA пересекает медленную сверху вниз с нарастающим расхождением
        - UNSTABLE: недостаточно свечей
        - []: нет сигнала
        """
        if not self.is_active or not closes:
            return ["UNSTABLE"]

        req_len = max(self.period1, self.period2) + 5
        if len(closes) < req_len:
            return ["UNSTABLE"]

        ema1 = IndicatorsMath.calc_ema(closes, self.period1)
        ema2 = IndicatorsMath.calc_ema(closes, self.period2)

        min_len = min(len(ema1), len(ema2))
        if min_len < 3:
            return ["UNSTABLE"]

        e1_tail = ema1[-min_len:]
        e2_tail = ema2[-min_len:]

        diff = [e1 - e2 for e1, e2 in zip(e1_tail, e2_tail)]
        if len(diff) < 3:
            return ["UNSTABLE"]

        d_now = diff[-1]
        d_prev = diff[-2]
        d_prev2 = diff[-3]

        delta_now = abs(d_now - d_prev)
        delta_prev = abs(d_prev - d_prev2)
        impulse = delta_now > delta_prev

        cross_up = (d_now > 0) and (d_prev2 < 0) and (d_prev > d_prev2) and impulse
        cross_down = (d_now < 0) and (d_prev2 > 0) and (d_prev < d_prev2) and impulse

        signals = []
        if cross_up:
            signals.append("CROSS_UP")
        if cross_down:
            signals.append("CROSS_DOWN")

        return signals


class VolumeFilterCalculator:
    """Изолированный калькулятор фильтра всплеска объема (VOLF)."""

    def __init__(self, cfg: Dict[str, Any]):
        self.is_active: bool = bool(cfg.get("is_active", False))
        self.timeframe: str = str(cfg.get("timeframe", "1m"))
        self.mode: str = str(cfg.get("mode", "a"))  # 'a' (absolute max) / 'r' (rolling average)
        self.period: int = int(cfg.get("period", 14))

        mode_cfg = cfg.get(self.mode, {}) if isinstance(cfg.get(self.mode), dict) else {}
        self.slice_factor: float = float(mode_cfg.get("slice_factor", 1.1 if self.mode == "a" else 2.1))

        self.long_cond: str = str(cfg.get("long_cond", "VOLF_PASSED"))
        self.short_cond: str = str(cfg.get("short_cond", "VOLF_PASSED"))

    def calculate(self, candles: Any) -> List[str]:
        """
        Вычисляет условие всплеска объема:
        - mode 'a': last_vol > max(ref_values) * slice_factor
        - mode 'r': last_vol > avg(ref_values) * slice_factor
        """
        if not self.is_active or not candles:
            return ["UNSTABLE"]

        volumes: List[float] = []
        if isinstance(candles, list):
            for c in candles:
                if isinstance(c, dict):
                    volumes.append(abs(float(c.get("volume", 0.0))))
                elif isinstance(c, (int, float)):
                    volumes.append(abs(float(c)))
        elif isinstance(candles, dict) and "volume" in candles:
            volumes = [abs(float(v)) for v in candles["volume"]]

        if len(volumes) < self.period + 1:
            return ["UNSTABLE"]

        last_vol = volumes[-1]
        ref_values = volumes[-(self.period + 1):-1]

        passed = False
        if self.mode == "a":
            past_max = max(ref_values)
            passed = (last_vol > past_max * self.slice_factor) if past_max > 0 else (last_vol > 0)
        elif self.mode == "r":
            past_avg = sum(ref_values) / len(ref_values)
            passed = (last_vol > past_avg * self.slice_factor) if past_avg > 0 else (last_vol > 0)

        if passed:
            return [self.long_cond]
        return []
