# ============================================================
# FILE: CORE/indicators/regime.py
# ROLE: Volatility Regime Gate (VRG) - гейт по режиму рынка
#
# ГИПОТЕЗА:
#   HVH impulse не работает не потому что HVH плохой, а потому что
#   он не знает, в каком режиме рынок. В mean-reverting режиме
#   пробой = откат. В trending режиме пробой = продолжение.
#   VRG определяет режим через Hurst exponent (variance ratio)
#   и разрешает HVH impulse только в trending режиме.
#
# МЕТОД:
#   Variance Ratio VR(k) = Var(r_k) / (k * Var(r_1))
#   H = log(VR) / log(k)
#
#   H > 0.55  → trending (импульс продолжается)
#   H < 0.45  → mean-reverting (импульс гасится)
#   0.45..0.55 → random walk (не торгуем)
#
#   Для крипты типичный H на 5m лежит в 0.40..0.55, на 1H — 0.45..0.60.
#   Пороги можно калибровать per timeframe.
# ============================================================

from typing import Dict, Any, Optional, List
import numpy as np

from CORE.rules import BaseRule
from CORE.indicators.hvh import HVHCalculator, EntryHVHRule
from c_log import log


class HurstRegimeCalculator:
    """
    Определяет режим рынка через variance ratio / Hurst exponent.
    
    Поддерживает два режима:
      - 'rolling': H считается на последнем окне (адаптивен)
      - 'expanding': H считается на всей доступной истории (стабильнее)
    """

    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.is_active: bool = bool(cfg.get("is_active", False))
        self.timeframe: str = str(cfg.get("timeframe", "5m"))
        self.window: int = int(cfg.get("window", 200))
        self.k: int = int(cfg.get("k", 5))  # агрегация: 5-баровые returns
        self.mode: str = str(cfg.get("mode", "rolling"))
        self.trending_threshold: float = float(cfg.get("trending_threshold", 0.55))
        self.mean_rev_threshold: float = float(cfg.get("mean_rev_threshold", 0.45))

    @staticmethod
    def _variance_ratio(log_rets: np.ndarray, k: int) -> Optional[float]:
        """
        Variance ratio на массиве лог-returns.
        VR = Var(r_k) / (k * Var(r_1))
        """
        if log_rets.size < k * 4:
            return None

        var_1 = float(np.var(log_rets, ddof=1))
        if var_1 < 1e-12:
            return None

        # r_k: cumulative k-bar returns, непересекающиеся окна
        n = log_rets.size // k
        if n < 2:
            return None
        agg = log_rets[: n * k].reshape(n, k).sum(axis=1)
        var_k = float(np.var(agg, ddof=1))

        vr = var_k / (k * var_1)
        return vr

    def calculate(self, closes: List[float]) -> Dict[str, Any]:
        """
        Возвращает:
        {
          "hurst": float | None,
          "regime": "TRENDING"|"MEAN_REVERTING"|"NEUTRAL"|"UNSTABLE",
          "status": "OK"|"UNSTABLE"
        }
        """
        if not self.is_active or not closes:
            return {"hurst": None, "regime": "UNSTABLE", "status": "INACTIVE"}

        arr = np.asarray(closes, dtype=np.float64)
        if arr.size < self.window + self.k * 4:
            return {"hurst": None, "regime": "UNSTABLE", "status": "UNSTABLE"}

        if self.mode == "rolling":
            segment = arr[-self.window - 1:]
        else:
            segment = arr

        if np.any(segment <= 0):
            return {"hurst": None, "regime": "UNSTABLE", "status": "UNSTABLE"}

        log_rets = np.diff(np.log(segment))
        vr = self._variance_ratio(log_rets, self.k)
        if vr is None or vr <= 0:
            return {"hurst": None, "regime": "UNSTABLE", "status": "UNSTABLE"}

        hurst = float(np.log(vr) / np.log(self.k))

        # Клиппинг: H в разумных пределах (0..1)
        hurst = max(0.0, min(1.0, hurst))

        if hurst >= self.trending_threshold:
            regime = "TRENDING"
        elif hurst <= self.mean_rev_threshold:
            regime = "MEAN_REVERTING"
        else:
            regime = "NEUTRAL"

        return {
            "hurst": hurst,
            "vr": vr,
            "regime": regime,
            "status": "OK",
        }


class EntryRegimeGatedHVHRule(BaseRule):
    """
    Обёртка над EntryHVHRule с гейтом по режиму рынка.
    
    Логика:
      - В TRENDING режиме (H > 0.55) разрешаем HVH impulse (пробой = продолжение).
      - В MEAN_REVERTING режиме (H < 0.45) разрешаем HVH pullback (пробой = откат).
      - В NEUTRAL (0.45..0.55) — не торгуем вообще.
    
    Это тот же HVH, но с условным включением. Один сигнал — два режима.
    """

    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.is_active: bool = bool(cfg.get("is_active", False))

        # Режим по умолчанию: 'impulse' или 'pullback'
        # Если режим совпадает с market regime — торгуем, иначе молчим
        self.trade_in_trending: bool = bool(cfg.get("trade_in_trending", True))
        self.trade_in_mean_reverting: bool = bool(cfg.get("trade_in_mean_reverting", False))

        # Внутренний HVH (impulse или pullback) — параметризуется отдельно
        self.hvh_signal_type: str = str(cfg.get("hvh_signal_type", "impulse"))
        hvh_cfg = dict(cfg)
        hvh_cfg["signal_type"] = self.hvh_signal_type
        self.hvh_calc = HVHCalculator(hvh_cfg)
        self.hvh_rule = EntryHVHRule({
            "is_active": True,
            "long_cond": cfg.get("hvh_long_cond", "HVH_LONG"),
            "short_cond": cfg.get("hvh_short_cond", "HVH_SHORT"),
        })

        self.regime_calc = HurstRegimeCalculator(cfg)

    def check(self, side: str, indicators: Optional[Dict[str, Any]] = None, **kwargs) -> bool:
        if not self.is_active:
            return True

        indicators = indicators or kwargs.get("indicators", {})
        closes = indicators.get("candles_closes") or []
        candles = indicators.get("candles", [])

        # 1. Режим
        regime_state = self.regime_calc.calculate(closes)
        if regime_state.get("status") != "OK":
            return False
        regime = regime_state["regime"]

        if regime == "TRENDING" and not self.trade_in_trending:
            return False
        if regime == "MEAN_REVERTING" and not self.trade_in_mean_reverting:
            return False
        if regime == "NEUTRAL":
            return False

        # 2. HVH сигнал
        hvh_state = self.hvh_calc.get_hvh_state(candles)
        hvh_signals = hvh_state.get("signals", [])
        if not hvh_signals or "UNSTABLE" in hvh_signals:
            return False

        target_cond = "HVH_LONG" if side == "LONG" else "HVH_SHORT"
        if target_cond not in hvh_signals:
            return False

        log(
            f"[VRG ENTRY] [{kwargs.get('symbol', 'SYM')}][{side}] "
            f"regime={regime} H={regime_state.get('hurst', 0):.3f} "
            f"hvh_type={self.hvh_signal_type}",
            level="INFO"
        )
        return True
    


# Как подключается:

# В indicators должно быть поле candles_closes — список close-цен (обычно уже есть как closes или можно извлечь из candles).

# EntryRegimeGatedHVHRule инстанцируется дважды — один раз с hvh_signal_type="impulse" (для TRENDING), второй раз с hvh_signal_type="pullback" (для MEAN_REVERTING). Оба регистрируются под разными ключами в EntrySignalEngine.