# ============================================================
# FILE: CORE/squeeze_flow.py
# ROLE: Institutional Order Flow (Taker Buy) & Volatility Squeeze Engine
# ============================================================

from typing import Dict, List, Any, Optional
import numpy as np


class TakerFlowCalculator:
    """
    Калькулятор потока рыночных покупок/продаж (Order Flow / Taker Volume).
    Анализирует долю покупок по рынку (Market Taker Orders) в общем объеме.
    """

    def __init__(self, cfg: Dict[str, Any]):
        self.is_active: bool = bool(cfg.get("is_active", False))
        self.timeframe: str = str(cfg.get("timeframe", "5m"))
        self.min_buy_ratio: float = float(cfg.get("min_buy_ratio", 0.58))
        self.max_buy_ratio: float = float(cfg.get("max_buy_ratio", 0.42))

    def calculate(self, candles: Any) -> List[str]:
        """
        Вычисляет состояние рыночного потока:
        - TAKER_BUY_DOMINANT: доминирование покупок по рынку (>= min_buy_ratio)
        - TAKER_SELL_DOMINANT: доминирование продаж по рынку (<= max_buy_ratio)
        """
        if not self.is_active or not candles:
            return ["UNSTABLE"]

        last_c = candles[-1] if isinstance(candles, list) else None
        if not last_c or not isinstance(last_c, dict):
            return ["UNSTABLE"]

        vol = float(last_c.get("volume", 0.0))
        taker_buy = float(last_c.get("taker_buy_volume", 0.0))

        if vol <= 0:
            return []

        ratio = taker_buy / vol
        signals = []
        if ratio >= self.min_buy_ratio:
            signals.append("TAKER_BUY_DOMINANT")
        elif ratio <= self.max_buy_ratio:
            signals.append("TAKER_SELL_DOMINANT")

        return signals


class VolatilitySqueezeCalculator:
    """
    Институциональный калькулятор сжатия волатильности (John Carter's Squeeze).
    Использует соотношение полос Боллинджера и каналов Кельтнера.
    Истинный импульс стреляет из фазы затухания волатильности (Squeeze).
    """

    def __init__(self, cfg: Dict[str, Any]):
        self.is_active: bool = bool(cfg.get("is_active", False))
        self.timeframe: str = str(cfg.get("timeframe", "5m"))
        self.bb_length: int = int(cfg.get("bb_length", 20))
        self.bb_mult: float = float(cfg.get("bb_mult", 2.0))
        self.kc_mult: float = float(cfg.get("kc_mult", 1.5))
        self.lookback_squeeze: int = int(cfg.get("lookback_squeeze", 3))

    @staticmethod
    def _calc_atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, length: int) -> np.ndarray:
        tr1 = highs[1:] - lows[1:]
        tr2 = np.abs(highs[1:] - closes[:-1])
        tr3 = np.abs(lows[1:] - closes[:-1])
        tr = np.maximum(np.maximum(tr1, tr2), tr3)
        atr = np.zeros(len(tr))
        if len(tr) < length:
            return atr
        atr[length - 1] = np.mean(tr[:length])
        for i in range(length, len(tr)):
            atr[i] = (atr[i - 1] * (length - 1) + tr[i]) / length
        return np.concatenate(([0.0], atr))

    def calculate(self, candles: Any) -> List[str]:
        """
        Вычисляет состояние сжатия и взрыва волатильности:
        - SQUEEZE_LONG: выход из сжатия волатильности вверх
        - SQUEEZE_SHORT: выход из сжатия волатильности вниз
        - SQUEEZE_ON: рынок находится в фазе сжатия пружины (накопление)
        """
        if not self.is_active or not candles:
            return ["UNSTABLE"]

        req_len = self.bb_length + self.lookback_squeeze + 5
        if len(candles) < req_len:
            return ["UNSTABLE"]

        if isinstance(candles, list) and isinstance(candles[0], dict):
            closes = np.array([float(c["close"]) for c in candles])
            highs = np.array([float(c["high"]) for c in candles])
            lows = np.array([float(c["low"]) for c in candles])
        else:
            return ["UNSTABLE"]

        # 1. Bollinger Bands (SMA + StdDev)
        n = len(closes)
        bb_mid = np.convolve(closes, np.ones(self.bb_length) / self.bb_length, mode='valid')
        pad = n - len(bb_mid)
        bb_mid = np.pad(bb_mid, (pad, 0), mode='edge')

        stds = np.array([np.std(closes[max(0, i - self.bb_length + 1):i + 1]) for i in range(n)])
        bb_upper = bb_mid + self.bb_mult * stds
        bb_lower = bb_mid - self.bb_mult * stds

        # 2. Keltner Channels (EMA + ATR)
        atr = self._calc_atr(highs, lows, closes, self.bb_length)
        kc_mid = bb_mid
        kc_upper = kc_mid + self.kc_mult * atr
        kc_lower = kc_mid - self.kc_mult * atr

        # 3. Детекция сжатия (Squeeze: BB внутри KC)
        squeeze_on = (bb_upper <= kc_upper) & (bb_lower >= kc_lower)

        # 4. Проверка разжатия (Fire)
        is_curr_firing = not squeeze_on[-1]
        was_squeezing = np.any(squeeze_on[-self.lookback_squeeze - 1:-1])

        signals = []
        if squeeze_on[-1]:
            signals.append("SQUEEZE_ON")

        if is_curr_firing and was_squeezing:
            if closes[-1] > kc_mid[-1] and closes[-1] > closes[-2]:
                signals.append("SQUEEZE_LONG")
            elif closes[-1] < kc_mid[-1] and closes[-1] < closes[-2]:
                signals.append("SQUEEZE_SHORT")

        return signals


class RelativeStrengthCalculator:
    """
    Калькулятор относительной силы актива к бенчмарку (BTC).
    Отсекает монеты, не имеющие независимого покупательского импульса.
    """

    def __init__(self, cfg: Dict[str, Any]):
        self.is_active: bool = bool(cfg.get("is_active", False))
        self.lookback_candles: int = int(cfg.get("lookback_candles", 12))  # 1 час на 5m
        self.min_outperformance: float = float(cfg.get("min_outperformance", 0.015))  # +1.5% к BTC

    def calculate(self, coin_closes: List[float], btc_closes: List[float]) -> List[str]:
        """
        Возвращает:
        - RS_STRONG: актив опережает BTC на min_outperformance
        - RS_WEAK: актив отстает от BTC на min_outperformance
        """
        if not self.is_active:
            return []

        if len(coin_closes) < self.lookback_candles or len(btc_closes) < self.lookback_candles:
            return ["UNSTABLE"]

        c_ret = (coin_closes[-1] - coin_closes[-self.lookback_candles]) / coin_closes[-self.lookback_candles]
        b_ret = (btc_closes[-1] - btc_closes[-self.lookback_candles]) / btc_closes[-self.lookback_candles]

        spread = c_ret - b_ret
        signals = []
        if spread >= self.min_outperformance:
            signals.append("RS_STRONG")
        elif spread <= -self.min_outperformance:
            signals.append("RS_WEAK")

        return signals


class ChandelierTrailingCalculator:
    """
    Калькулятор Chandelier Exit (трейлинг-стоп на базе волатильности ATR).
    Позволяет сидеть в сильных трендах и забирать длинные хвосты распределения прибыли (Fat Tails).
    """

    def __init__(self, cfg: Dict[str, Any]):
        self.is_active: bool = bool(cfg.get("is_active", False))
        self.length: int = int(cfg.get("length", 15))
        self.atr_mult: float = float(cfg.get("atr_mult", 2.5))

    def should_exit(self, side: str, candles: Any, current_price: float) -> bool:
        """
        Проверяет, пробит ли трейлинг Chandelier Exit:
        LONG: current_price <= highest(highs, length) - atr_mult * ATR
        SHORT: current_price >= lowest(lows, length) + atr_mult * ATR
        """
        if not self.is_active or not candles or len(candles) < self.length + 2:
            return False

        if isinstance(candles, list) and isinstance(candles[0], dict):
            highs = np.array([float(c["high"]) for c in candles[-self.length:]])
            lows = np.array([float(c["low"]) for c in candles[-self.length:]])
            closes = np.array([float(c["close"]) for c in candles[-self.length:]])
        else:
            return False

        # ATR за N свечей
        tr1 = highs[1:] - lows[1:]
        tr2 = np.abs(highs[1:] - closes[:-1])
        tr3 = np.abs(lows[1:] - closes[:-1])
        tr = np.maximum(np.maximum(tr1, tr2), tr3)
        atr = float(np.mean(tr)) if len(tr) > 0 else 0.0

        if side == "LONG":
            highest_high = float(np.max(highs))
            chandelier_stop = highest_high - (self.atr_mult * atr)
            return current_price <= chandelier_stop
        elif side == "SHORT":
            lowest_low = float(np.min(lows))
            chandelier_stop = lowest_low + (self.atr_mult * atr)
            return current_price >= chandelier_stop

        return False


from CORE.rules import BaseRule


class EntryTakerFlowRule(BaseRule):
    """Правило входа по потоку рыночных покупок (Order Flow / Taker Buy)."""

    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.is_active: bool = bool(cfg.get("is_active", False))
        self.long_cond: str = str(cfg.get("long_cond", "TAKER_BUY_DOMINANT"))
        self.short_cond: str = str(cfg.get("short_cond", "TAKER_SELL_DOMINANT"))

    def check(self, side: str, indicators: Optional[Dict[str, Any]] = None, **kwargs) -> bool:
        if not self.is_active:
            return True
        indicators = indicators or kwargs.get("indicators", {})
        signals = indicators.get("taker_flow", kwargs.get("taker_flow", []))
        if not signals or "UNSTABLE" in signals:
            return False
        if side == "LONG":
            return self.long_cond in signals
        elif side == "SHORT":
            return self.short_cond in signals
        return False


class EntryVolatilitySqueezeRule(BaseRule):
    """Правило входа по разжатию волатильности (Volatility Squeeze Fired)."""

    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.is_active: bool = bool(cfg.get("is_active", False))
        self.long_cond: str = str(cfg.get("long_cond", "SQUEEZE_LONG"))
        self.short_cond: str = str(cfg.get("short_cond", "SQUEEZE_SHORT"))

    def check(self, side: str, indicators: Optional[Dict[str, Any]] = None, **kwargs) -> bool:
        if not self.is_active:
            return True
        indicators = indicators or kwargs.get("indicators", {})
        signals = indicators.get("volatility_squeeze", kwargs.get("volatility_squeeze", []))
        if not signals or "UNSTABLE" in signals:
            return False
        if side == "LONG":
            return self.long_cond in signals
        elif side == "SHORT":
            return self.short_cond in signals
        return False


class ExitChandelierRule(BaseRule):
    """Правило трейлинг-выхода Chandelier Exit по волатильности."""

    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.is_active: bool = bool(cfg.get("is_active", False))
        self.calc = ChandelierTrailingCalculator(cfg)

    def check(self, side: str, current_price: float, candles: Any = None, **kwargs) -> bool:
        if not self.is_active:
            return False
        candles = candles or kwargs.get("candles")
        return self.calc.should_exit(side, candles, current_price)
