# ============================================================
# FILE: CORE/indicators.py
# ROLE: Standalone modular indicator calculation engine (Trend, RSI & SR Levels)
# ============================================================

from typing import Dict, List, Set, Any, Optional
from CORE.sr_levels import SRLevelsCalculator


class IndicatorsMath:
    """Чистые математические формулы технических индикаторов."""

    @staticmethod
    def calc_ema(prices: List[float], length: int) -> List[float]:
        """Расчет Exponential Moving Average (EMA)."""
        if not prices or len(prices) < length:
            return []
        k = 2 / (length + 1)
        ema_list = []
        ema = sum(prices[:length]) / length
        ema_list.append(ema)
        for price in prices[length:]:
            ema = price * k + ema * (1 - k)
            ema_list.append(ema)
        return ema_list

    @staticmethod
    def calc_rsi_series(closes: List[float], length: int = 14) -> List[float]:
        """Расчет серии Relative Strength Index (RSI) по формуле Уайлдера."""
        if not closes or len(closes) < length + 1:
            return []

        diffs = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        gains = [d if d > 0 else 0.0 for d in diffs]
        losses = [-d if d < 0 else 0.0 for d in diffs]

        avg_gain = sum(gains[:length]) / length
        avg_loss = sum(losses[:length]) / length

        rsi_list = []
        if avg_loss == 0 and avg_gain == 0:
            rsi_list.append(50.0)
        elif avg_loss == 0:
            rsi_list.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsi_list.append(100.0 - (100.0 / (1.0 + rs)))

        for i in range(length, len(gains)):
            avg_gain = (avg_gain * (length - 1) + gains[i]) / length
            avg_loss = (avg_loss * (length - 1) + losses[i]) / length

            if avg_loss == 0 and avg_gain == 0:
                rsi_list.append(50.0)
            elif avg_loss == 0:
                rsi_list.append(100.0)
            else:
                rs = avg_gain / avg_loss
                rsi_list.append(100.0 - (100.0 / (1.0 + rs)))

        return rsi_list

    @staticmethod
    def calc_rsi(closes: List[float], length: int = 14) -> Optional[float]:
        """Расчет последнего значения Relative Strength Index (RSI)."""
        series = IndicatorsMath.calc_rsi_series(closes, length)
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
    """Изолированный калькулятор боевого EMA-кроссовера с фильтром ускорения и импульса."""

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
        - CROSS_UP: быстрая EMA пересекает медленную снизу вверх с нарастающим расхождением (импульс)
        - CROSS_DOWN: быстрая EMA пересекает медленную сверху вниз с нарастающим расхождением (импульс)
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
            signals.append(self.long_cond)
        if cross_down:
            signals.append(self.short_cond)

        return signals


class IndicatorsEngine:
    """
    Фасадный интерфейс индикаторного блока системы.
    Может быть скопирован и вызван в одну строку в ЛЮБОМ проекте.
    """

    def __init__(self, enter_rules: Dict[str, Any]):
        self.trend_calcs: Dict[str, TrendCalculator] = {}
        for key in ["trend", "trend_htf"]:
            if key in enter_rules:
                self.trend_calcs[key] = TrendCalculator(enter_rules[key])
        
        # Поддержка дополнительных ключей тренда при их наличии
        for key, val in enter_rules.items():
            if key.startswith("trend") and key not in self.trend_calcs and isinstance(val, dict):
                self.trend_calcs[key] = TrendCalculator(val)

        rsi_cfg = enter_rules.get("rsi")
        self.rsi_calc = RSICalculator(rsi_cfg) if rsi_cfg else None

        waterline_cfg = enter_rules.get("rsi_waterline50")
        self.rsi_waterline_calc = RSIWaterlineCalculator(waterline_cfg) if waterline_cfg else None

        sr_cfg = enter_rules.get("sr_levels")
        self.sr_calc = SRLevelsCalculator(sr_cfg) if sr_cfg else None

        ema_cross_cfg = enter_rules.get("ema_cross")
        self.ema_cross_calc = EMACrossCalculator(ema_cross_cfg) if ema_cross_cfg else None

    def get_required_timeframes(self) -> Set[str]:
        """Возвращает набор таймфреймов, данные по которым требуются для расчетов."""
        tfs = set()
        for calc in self.trend_calcs.values():
            if calc.is_active:
                tfs.add(calc.timeframe)
        if self.rsi_calc and self.rsi_calc.is_active:
            tfs.add(self.rsi_calc.timeframe)
        if self.rsi_waterline_calc and self.rsi_waterline_calc.is_active:
            tfs.add(self.rsi_waterline_calc.timeframe)
        if self.sr_calc and self.sr_calc.is_active:
            tfs.add(self.sr_calc.timeframe)
        if self.ema_cross_calc and self.ema_cross_calc.is_active:
            tfs.add(self.ema_cross_calc.timeframe)
        return tfs if tfs else {"5m"}

    def calculate(self, klines_by_tf: Dict[str, Any], current_price: Optional[float] = None) -> Dict[str, Any]:
        """
        Вычисляет показатели индикаторов по переданному словарю {таймфрейм: список_свечей_или_closes}.
        Возвращает: {"trend": str, "trend_htf": str, "rsi": list[str], "rsi_value": float | None,
                     "rsi_waterline50": list[str], "sr_levels": list[str], "sr_levels_data": dict,
                     "ema_cross": list[str]}
        """
        # Извлечение close цен для EMA и RSI
        closes_by_tf: Dict[str, List[float]] = {}
        for tf, raw in klines_by_tf.items():
            if isinstance(raw, list):
                if raw and isinstance(raw[0], dict):
                    closes_by_tf[tf] = [float(c.get("close", 0.0)) for c in raw]
                else:
                    closes_by_tf[tf] = [float(c) for c in raw]
            elif isinstance(raw, dict) and "close" in raw:
                closes_by_tf[tf] = [float(x) for x in raw["close"]]
            else:
                closes_by_tf[tf] = []

        result: Dict[str, Any] = {}
        for key, calc in self.trend_calcs.items():
            if calc.is_active:
                closes = closes_by_tf.get(calc.timeframe, [])
                result[key] = calc.calculate(closes)
            else:
                result[key] = "UNSTABLE"

        if "trend" not in result:
            result["trend"] = "UNSTABLE"

        rsi_states = ["UNSTABLE"]
        rsi_val = None
        if self.rsi_calc and self.rsi_calc.is_active:
            closes_rsi = closes_by_tf.get(self.rsi_calc.timeframe, [])
            rsi_states = self.rsi_calc.calculate(closes_rsi)
            rsi_val = self.rsi_calc.get_raw_value(closes_rsi)

        result["rsi"] = rsi_states
        result["rsi_value"] = rsi_val

        if self.rsi_waterline_calc and self.rsi_waterline_calc.is_active:
            closes_wl = closes_by_tf.get(self.rsi_waterline_calc.timeframe, [])
            result["rsi_waterline50"] = self.rsi_waterline_calc.calculate(closes_wl)
        else:
            result["rsi_waterline50"] = []

        if self.sr_calc and self.sr_calc.is_active:
            candles_sr = klines_by_tf.get(self.sr_calc.timeframe, [])
            sr_res = self.sr_calc.calculate(candles_sr, current_price=current_price)
            result["sr_levels"] = sr_res["signals"]
            result["sr_levels_data"] = sr_res
        else:
            result["sr_levels"] = []
            result["sr_levels_data"] = {"signals": [], "support": [], "resistance": []}

        if self.ema_cross_calc and self.ema_cross_calc.is_active:
            closes_ec = closes_by_tf.get(self.ema_cross_calc.timeframe, [])
            result["ema_cross"] = self.ema_cross_calc.calculate(closes_ec)
        else:
            result["ema_cross"] = []

        return result