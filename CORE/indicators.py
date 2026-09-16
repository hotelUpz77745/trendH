# ============================================================
# FILE: indicators.py
# ROLE: Standalone modular indicator calculation engine (Trend & RSI)
# ============================================================

from typing import Dict, List, Set, Any, Optional


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
        # Чтение конфига строго по п. 2 протокола ([''])
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
        # Чтение конфига строго по п. 2 протокола ([''])
        self.is_active: bool = bool(cfg["is_active"])
        self.timeframe: str = str(cfg["timeframe"])
        self.window: int = int(cfg["window"])
        self.conditions: Dict[str, str] = cfg.get("conditions", {})

    def calculate(self, closes: List[float]) -> List[str]:
        """
        Вычисляет состояние RSI:
        Возвращает список ключей сработавших условий (напр. ['ENTER_LONG']).
        Если данных недостаточно, возвращает ['UNSTABLE'].
        """
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
        """Возвращает числовое значение RSI (float) или None при нехватке данных."""
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
        """
        Возвращает:
        - ['CROSS_UP']: если RSI пересек ватерлинию снизу вверх (prev <= waterline < curr)
        - ['CROSS_DOWN']: если RSI пересек ватерлинию сверху вниз (prev >= waterline > curr)
        - ['UNSTABLE']: если недостаточно свечей
        - []: если пересечения не произошло
        """
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
        return tfs if tfs else {"5m"}

    def calculate(self, closes_by_tf: Dict[str, List[float]]) -> Dict[str, Any]:
        """
        Вычисляет показатели индикаторов по переданному словарю {таймфрейм: список_closes}.
        Возвращает: {"trend": str, "trend_htf": str, "rsi": list[str], "rsi_value": float | None, "rsi_waterline50": list[str]}
        """
        result: Dict[str, Any] = {}
        for key, calc in self.trend_calcs.items():
            if calc.is_active:
                closes = closes_by_tf.get(calc.timeframe, [])
                result[key] = calc.calculate(closes)
            else:
                result[key] = "UNSTABLE"

        # Дефолт для базового trend если не задан
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

        return result