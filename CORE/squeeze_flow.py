# ============================================================
# FILE: CORE/squeeze_flow.py
# ROLE: Institutional Order Flow (Taker Buy) & Volatility Squeeze Engine
# ============================================================

from typing import Dict, List, Any, Optional
from collections import deque
import time
import numpy as np


class RealtimeFlowTracker:
    """
    Высокоскоростной трекер потока ордеров (Live Order Flow / Tick-by-Tick CVD).
    Агрегирует реальные рыночные сделки из WebSocket-стрима @trade без задержек свечей.
    """

    def __init__(self, max_retention_sec: float = 300.0):
        self.max_retention_sec = max_retention_sec
        self.trades: Dict[str, deque] = {}

    def add_trade(self, symbol: str, price: float, qty: float, is_buyer_maker: bool, event_time_ms: int = 0) -> None:
        now_ms = event_time_ms if event_time_ms > 0 else int(time.time() * 1000)
        if symbol not in self.trades:
            self.trades[symbol] = deque()
        quote_vol = price * qty
        is_taker_buy = not is_buyer_maker
        self.trades[symbol].append((now_ms, quote_vol, is_taker_buy))
        cutoff = now_ms - int(self.max_retention_sec * 1000)
        q = self.trades[symbol]
        while q and q[0][0] < cutoff:
            q.popleft()

    def get_flow(
        self,
        symbol: str,
        window_sec: float = 60.0,
        min_buy_ratio: float = 0.58,
        max_buy_ratio: float = 0.42
    ) -> Dict[str, Any]:
        now_ms = int(time.time() * 1000)
        cutoff = now_ms - int(window_sec * 1000)
        q = self.trades.get(symbol)
        if not q:
            return {"taker_buy_ratio": 0.5, "delta": 0.0, "total_vol": 0.0, "signals": []}

        buy_vol = 0.0
        sell_vol = 0.0
        for ts, vol, is_buy in q:
            if ts >= cutoff:
                if is_buy:
                    buy_vol += vol
                else:
                    sell_vol += vol

        total_vol = buy_vol + sell_vol
        if total_vol <= 0:
            return {"taker_buy_ratio": 0.5, "delta": 0.0, "total_vol": 0.0, "signals": []}

        ratio = buy_vol / total_vol
        signals = []
        if ratio >= min_buy_ratio:
            signals.append("TAKER_BUY_DOMINANT")
        elif ratio <= max_buy_ratio:
            signals.append("TAKER_SELL_DOMINANT")

        return {
            "taker_buy_vol": buy_vol,
            "taker_sell_vol": sell_vol,
            "total_vol": total_vol,
            "taker_buy_ratio": ratio,
            "delta": buy_vol - sell_vol,
            "signals": signals,
        }


class TakerFlowCalculator:
    """
    Калькулятор потока рыночных покупок/продаж (Order Flow / Taker Volume).
    Анализирует долю покупок по рынку (Market Taker Orders) в общем объеме.
    Поддерживает:
      - mode='realtime': моментальный расчет из live тиков (sub-second)
      - mode='candle': расчет по закрытой свече
      - mode='auto': использует realtime при наличии тиков, иначе свечи
    """

    def __init__(self, cfg: Dict[str, Any]):
        self.is_active: bool = bool(cfg.get("is_active", False))
        self.timeframe: str = str(cfg.get("timeframe", "5m"))
        self.mode: str = str(cfg.get("mode", "auto"))
        self.window_sec: float = float(cfg.get("window_sec", 60.0))
        self.min_buy_ratio: float = float(cfg.get("min_buy_ratio", 0.58))
        self.max_buy_ratio: float = float(cfg.get("max_buy_ratio", 0.42))

    def calculate(self, candles: Any, realtime_flow: Optional[Dict[str, Any]] = None) -> List[str]:
        if not self.is_active:
            return ["UNSTABLE"]

        # 1. Приоритет реального времени (WS tick-by-tick)
        if self.mode in ("auto", "realtime") and realtime_flow:
            sig = realtime_flow.get("signals")
            if sig is not None and len(sig) > 0:
                return sig
            if realtime_flow.get("total_vol", 0.0) > 0:
                return []

        # 2. Фолбэк на свечи (Binance klines field 9: taker_buy_volume)
        if not candles:
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

        from CORE.native_math import NativeMath
        bb_upper, bb_lower, kc_upper, kc_lower = NativeMath.fast_squeeze(
            closes, highs, lows, self.bb_length, self.bb_mult, self.kc_mult
        )

        # 3. Детекция сжатия (Squeeze: BB внутри KC)
        squeeze_on = (bb_upper <= kc_upper) & (bb_lower >= kc_lower)

        # 4. Проверка разжатия (Fire)
        is_curr_firing = not squeeze_on[-1]
        was_squeezing = bool(np.any(squeeze_on[-self.lookback_squeeze - 1:-1]))
        mid = (bb_upper[-1] + bb_lower[-1]) / 2.0

        signals = []
        if squeeze_on[-1]:
            signals.append("SQUEEZE_ON")

        if is_curr_firing and was_squeezing:
            if closes[-1] > mid and closes[-1] > closes[-2]:
                signals.append("SQUEEZE_LONG")
            elif closes[-1] < mid and closes[-1] < closes[-2]:
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


class EntryRelativeStrengthRule(BaseRule):
    """Правило входа по относительной силе к бенчмарку BTC (Relative Strength)."""

    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.is_active: bool = bool(cfg.get("is_active", False))
        self.long_cond: str = str(cfg.get("long_cond", "RS_STRONG"))
        self.short_cond: str = str(cfg.get("short_cond", "RS_WEAK"))

    def check(self, side: str, indicators: Optional[Dict[str, Any]] = None, **kwargs) -> bool:
        if not self.is_active:
            return True
        indicators = indicators or kwargs.get("indicators", {})
        signals = indicators.get("relative_strength", kwargs.get("relative_strength", []))
        if not signals or "UNSTABLE" in signals:
            return False
        if side == "LONG":
            return self.long_cond in signals
        elif side == "SHORT":
            return self.short_cond in signals
        return False
