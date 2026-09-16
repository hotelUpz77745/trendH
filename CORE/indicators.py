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
    def calc_rsi(closes: List[float], length: int = 14) -> Optional[float]:
        """Расчет Relative Strength Index (RSI) по формуле Уайлдера."""
        if not closes or len(closes) < length + 1:
            return None

        diffs = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        gains = [d if d > 0 else 0.0 for d in diffs]
        losses = [-d if d < 0 else 0.0 for d in diffs]

        avg_gain = sum(gains[:length]) / length
        avg_loss = sum(losses[:length]) / length

        for i in range(length, len(gains)):
            avg_gain = (avg_gain * (length - 1) + gains[i]) / length
            avg_loss = (avg_loss * (length - 1) + losses[i]) / length

        if avg_loss == 0 and avg_gain == 0:
            return 50.0
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))


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


class IndicatorsEngine:
    """
    Фасадный интерфейс индикаторного блока системы.
    Может быть скопирован и вызван в одну строку в ЛЮБОМ проекте.
    """

    def __init__(self, enter_rules: Dict[str, Any]):
        # Чтение структуры правил входа
        trend_cfg = enter_rules["trend"]
        rsi_cfg = enter_rules["rsi"]

        self.trend_calc = TrendCalculator(trend_cfg)
        self.rsi_calc = RSICalculator(rsi_cfg)

    def get_required_timeframes(self) -> Set[str]:
        """Возвращает набор таймфреймов, данные по которым требуются для расчетов."""
        tfs = set()
        if self.trend_calc.is_active:
            tfs.add(self.trend_calc.timeframe)
        if self.rsi_calc.is_active:
            tfs.add(self.rsi_calc.timeframe)
        return tfs if tfs else {"5m"}

    def calculate(self, closes_by_tf: Dict[str, List[float]]) -> Dict[str, Any]:
        """
        Вычисляет показатели индикаторов по переданному словарю {таймфрейм: список_closes}.
        Пример возвращаемого значения: {"trend": "UP", "rsi": 62.4}
        """
        trend_val = "UNSTABLE"
        if self.trend_calc.is_active:
            closes_trend = closes_by_tf.get(self.trend_calc.timeframe, [])
            trend_val = self.trend_calc.calculate(closes_trend)

        rsi_states = ["UNSTABLE"]
        if self.rsi_calc.is_active:
            closes_rsi = closes_by_tf.get(self.rsi_calc.timeframe, [])
            rsi_states = self.rsi_calc.calculate(closes_rsi)

        return {
            "trend": trend_val,
            "rsi": rsi_states
        }