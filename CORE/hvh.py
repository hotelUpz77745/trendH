# ============================================================
# FILE: CORE/hvh.py
# ROLE: High Volatility Highway (HVH) indicator and entry rule
# ============================================================

from typing import Dict, List, Any, Optional
import numpy as np
import pandas as pd
from CORE.rules import BaseRule


class HVHCalculator:
    """
    Индикатор динамических полос экстремальной волатильности (High Volatility Highway).
    
    Методология:
    - Скользящая средняя цен закрытия: MA(close, period)
    - Оценка девиаций high/low относительно MA:
        high_dev = max(high - MA, 0)
        low_dev  = max(MA - low, 0)
        deviation = max(high_dev, low_dev)
    - Адаптивная ширина полосы (adj_dev):
        * mode='rolling': rolling_max(deviation, period) * dev_multiplier
        * mode='fixed':   max(deviation[-period:]) * dev_multiplier
    - Верхний триггер: MA + adj_dev
    - Нижний триггер:  MA - adj_dev

    Режимы генерации сигналов (signal_type):
    1. 'pullback' (Mean-Reversion / Inverted):
       - close >= Upper Trigger -> HVH_SHORT (перерастяжка цены вверх, продаем откат)
       - close <= Lower Trigger -> HVH_LONG  (перерастяжка цены вниз, покупаем отскок)
    2. 'impulse' (Momentum Breakout / Direct):
       - close >= Upper Trigger -> HVH_LONG  (импульсный пробой границы вверх)
       - close <= Lower Trigger -> HVH_SHORT (импульсный пробой границы вниз)
    """

    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.is_active: bool = bool(cfg.get("is_active", False))
        self.timeframe: str = str(cfg.get("timeframe", "5m"))
        self.period: int = int(cfg.get("period", 20))
        self.dev_multiplier: float = float(cfg.get("dev", 1.8))
        self.mode: str = str(cfg.get("mode", "rolling")).lower()
        self.signal_type: str = str(cfg.get("signal_type", "pullback")).lower()
        self.is_trend: int = int(cfg.get("is_trend", 1))
        self.long_cond: str = str(cfg.get("long_cond", "HVH_LONG"))
        self.short_cond: str = str(cfg.get("short_cond", "HVH_SHORT"))

    def _extract_arrays(self, candles: Any) -> Optional[Dict[str, np.ndarray]]:
        """Извлекает числовые массивы close, high, low из входящих данных свечей."""
        if not candles:
            return None

        if isinstance(candles, list):
            if not candles:
                return None
            first = candles[0]
            if isinstance(first, dict):
                closes = np.array([float(c.get("close", 0.0)) for c in candles], dtype=np.float64)
                highs = np.array([float(c.get("high", 0.0)) for c in candles], dtype=np.float64)
                lows = np.array([float(c.get("low", 0.0)) for c in candles], dtype=np.float64)
            elif isinstance(first, (int, float)):
                closes = np.array([float(x) for x in candles], dtype=np.float64)
                highs = closes.copy()
                lows = closes.copy()
            else:
                return None
        elif isinstance(candles, dict):
            if "close" in candles and "high" in candles and "low" in candles:
                closes = np.array(candles["close"], dtype=np.float64)
                highs = np.array(candles["high"], dtype=np.float64)
                lows = np.array(candles["low"], dtype=np.float64)
            else:
                return None
        elif isinstance(candles, pd.DataFrame):
            closes = candles["close"].to_numpy(dtype=np.float64)
            highs = candles["high"].to_numpy(dtype=np.float64)
            lows = candles["low"].to_numpy(dtype=np.float64)
        else:
            return None

        return {"close": closes, "high": highs, "low": lows}

    def get_hvh_state(self, candles: Any) -> Dict[str, Any]:
        """
        Полный математический расчет HVH с возвратом всех расчетных уровней.
        Используется для аудита, логирования и юнит-тестирования.
        """
        if not self.is_active or not candles:
            return {"signals": ["UNSTABLE"], "status": "INACTIVE_OR_EMPTY"}

        arrays = self._extract_arrays(candles)
        if arrays is None:
            return {"signals": ["UNSTABLE"], "status": "INVALID_FORMAT"}

        closes = arrays["close"]
        highs = arrays["high"]
        lows = arrays["low"]
        n = len(closes)

        if n < self.period:
            return {"signals": ["UNSTABLE"], "status": "INSUFFICIENT_HISTORY"}

        close_series = pd.Series(closes)
        high_series = pd.Series(highs)
        low_series = pd.Series(lows)

        ma_series = close_series.rolling(window=self.period, min_periods=self.period).mean()
        high_dev = np.where(high_series > ma_series, (high_series - ma_series).abs(), 0.0)
        low_dev = np.where(low_series < ma_series, (ma_series - low_series).abs(), 0.0)
        dev_series = pd.Series(np.maximum(high_dev, low_dev))

        if self.mode == "fixed":
            # Фиксированная максимальная девиация за предшествующий период (lookback)
            valid_tail = dev_series.iloc[-self.period - 1:-1].dropna() if len(dev_series) > self.period else dev_series.iloc[-self.period:].dropna()
            if valid_tail.empty:
                valid_tail = dev_series.iloc[-self.period:].dropna()
            max_dev = float(valid_tail.max()) if not valid_tail.empty else 0.0
            curr_adj_dev = max_dev * self.dev_multiplier
        else:
            # Скользящая максимальная девиация за предшествующее окно (lookback)
            rolling_max = dev_series.shift(1).rolling(window=self.period, min_periods=1).max()
            if rolling_max.empty or pd.isna(rolling_max.iloc[-1]) or rolling_max.iloc[-1] <= 0:
                rolling_max = dev_series.rolling(window=self.period, min_periods=1).max()
            curr_adj_dev = float(rolling_max.iloc[-1] * self.dev_multiplier)

        curr_ma = float(ma_series.iloc[-1])
        curr_close = float(closes[-1])

        if np.isnan(curr_ma) or np.isnan(curr_adj_dev):
            return {"signals": ["UNSTABLE"], "status": "NAN_METRICS"}

        upper_band = curr_ma + curr_adj_dev
        lower_band = curr_ma - curr_adj_dev

        signals = []
        is_pullback = (self.signal_type in ("pullback", "fade", "counter", "mean_reversion"))

        if is_pullback:
            # Контртрендовый отскок от экстремальной перерастяжки
            if curr_close >= upper_band:
                signals.append(self.short_cond)
            elif curr_close <= lower_band:
                signals.append(self.long_cond)
        else:
            # Импульсный пробой волатильности
            if curr_close >= upper_band:
                signals.append(self.long_cond)
            elif curr_close <= lower_band:
                signals.append(self.short_cond)

        return {
            "signals": signals,
            "status": "OK",
            "close": curr_close,
            "ma": curr_ma,
            "adj_dev": curr_adj_dev,
            "upper_band": upper_band,
            "lower_band": lower_band,
            "signal_type": self.signal_type
        }

    def calculate(self, candles: Any) -> List[str]:
        """
        Основной метод фасада индикатора. Возвращает список сигналов для торговых правил.
        """
        state = self.get_hvh_state(candles)
        return state.get("signals", [])


class EntryHVHRule(BaseRule):
    """
    Правило входа по сигналам индикатора HVH (High Volatility Highway).
    Проверяет наличие активного сигнала LONG или SHORT в расчетном состоянии индикатора.
    """

    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.is_active: bool = bool(cfg.get("is_active", False))
        self.long_cond: str = str(cfg.get("long_cond", "HVH_LONG"))
        self.short_cond: str = str(cfg.get("short_cond", "HVH_SHORT"))

    def check(self, side: str, indicators: Optional[Dict[str, Any]] = None, **kwargs) -> bool:
        if not self.is_active:
            return True

        indicators = indicators or kwargs.get("indicators", {})
        hvh_signals = indicators.get("hvh", kwargs.get("hvh", []))

        if not hvh_signals or "UNSTABLE" in hvh_signals:
            return False

        if side == "LONG":
            return self.long_cond in hvh_signals
        elif side == "SHORT":
            return self.short_cond in hvh_signals

        return False
