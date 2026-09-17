# ============================================================
# FILE: CORE/sr_levels.py
# ROLE: Pure NumPy LuxAlgo Support/Resistance levels detector & breakout calculator
# ============================================================

from typing import Dict, List, Any, Optional
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view


class SRLevelsCalculator:
    """Изолированный калькулятор уровней поддержки/сопротивления LuxAlgo и пробоев."""

    def __init__(self, cfg: Dict[str, Any]):
        self.is_active: bool = bool(cfg.get("is_active", False))
        self.timeframe: str = str(cfg.get("timeframe", "5m"))
        self.swing_len: int = int(cfg.get("swing_len", 15))
        self.window: int = int(cfg.get("window", 300))
        self.margin: float = float(cfg.get("margin", 2.0))
        self.thickness_k: float = float(cfg.get("thickness_k", 0.17))
        self.max_zones: int = int(cfg.get("max_zones", 10))
        self.level_mode: str = str(cfg.get("level_mode", "latest"))
        self.breakout_edge: str = str(cfg.get("breakout_edge", "h"))
        self.long_cond: str = str(cfg.get("long_cond", "BREAKOUT_LONG"))
        self.short_cond: str = str(cfg.get("short_cond", "BREAKOUT_SHORT"))

    @staticmethod
    def detect_sr_levels(data: dict, rules: dict) -> dict:
        """
        SR-DETECTOR v3 — приближение LuxAlgo Support/Resistance.
        Формат вывода:
        {
            "support": [{"idx": 1, "ts": 1762938900000, "l": 0.00747, "h": 0.0076876}, ...],
            "resistance": [{"idx": 1, "ts": 1763068500000, "l": 0.0080972, "h": 0.0082400}, ...]
        }
        """
        try:
            if not data:
                return {"support": [], "resistance": []}

            highs = data.get("high")
            lows = data.get("low")
            ts = data.get("ts")

            if not isinstance(highs, np.ndarray) or not isinstance(lows, np.ndarray) or not isinstance(ts, np.ndarray):
                return {"support": [], "resistance": []}

            n = highs.size
            if n == 0 or lows.size != n or ts.size != n:
                return {"support": [], "resistance": []}

            if not np.isfinite(highs).all() or not np.isfinite(lows).all() or not np.isfinite(ts).all():
                return {"support": [], "resistance": []}

            L = int(rules.get("swing_len", 15))
            window_len = int(rules.get("window", 300))
            margin = float(rules.get("margin", 2.0))
            thickness_k = float(rules.get("thickness_k", 0.17))
            max_zones = int(rules.get("max_zones", 10))

            if n < 2 * L + 3:
                return {"support": [], "resistance": []}

            cutoff = max(0, n - window_len)
            from CORE.native_math import NativeMath
            ph, pl = NativeMath.fast_pivots(highs, lows, L)
            hi_idx = np.nonzero(ph > 0)[0]
            lo_idx = np.nonzero(pl > 0)[0]

            hi_idx = hi_idx[hi_idx >= cutoff]
            lo_idx = lo_idx[lo_idx >= cutoff]

            def remove_consecutive(idx: np.ndarray):
                if idx.size == 0:
                    return idx
                cleaned = [idx[0]]
                last = idx[0]
                for x in idx[1:]:
                    if x - last > L:
                        cleaned.append(x)
                        last = x
                return np.array(cleaned, dtype=np.int32)

            hi_idx = remove_consecutive(hi_idx)
            lo_idx = remove_consecutive(lo_idx)

            if hi_idx.size == 0 and lo_idx.size == 0:
                return {"support": [], "resistance": []}

            def calc_zone(level: float, idx: int, is_res: bool):
                start2 = max(0, idx - L + 1)
                pHST = float(highs[start2:idx+1].max())
                pLST = float(lows[start2:idx+1].min())

                if pHST <= 0 or not np.isfinite(pHST):
                    return float(level), float(level)

                m = (pHST - pLST) / pHST
                th = m * thickness_k * margin

                if is_res:
                    top = level
                    bottom = level * (1 - th)
                else:
                    bottom = level
                    top = level * (1 + th)

                if top < bottom:
                    top, bottom = bottom, top

                return float(bottom), float(top)

            piv_idx = np.concatenate([hi_idx, lo_idx])
            piv_typ = np.concatenate([
                np.ones_like(hi_idx, dtype=np.int8),
                -np.ones_like(lo_idx, dtype=np.int8)
            ])

            order = np.argsort(piv_idx)
            piv_idx = piv_idx[order]
            piv_typ = piv_typ[order]

            support = []
            resistance = []

            for idx, typ in zip(piv_idx, piv_typ):
                ts_val = int(ts[idx]) if isinstance(ts[idx], (int, float, np.integer, np.floating)) else 0
                level = highs[idx] if typ == 1 else lows[idx]

                z_l, z_h = calc_zone(level, idx, typ == 1)

                rec = {
                    "idx": int(idx),
                    "ts": ts_val,
                    "l": z_l,
                    "h": z_h
                }

                if typ == 1:
                    resistance.append(rec)
                else:
                    support.append(rec)

            support.sort(key=lambda x: x["idx"])
            resistance.sort(key=lambda x: x["idx"])

            for i, it in enumerate(support, start=1):
                it["idx"] = i
            for i, it in enumerate(resistance, start=1):
                it["idx"] = i

            if len(support) > max_zones:
                support = support[-max_zones:]
            if len(resistance) > max_zones:
                resistance = resistance[-max_zones:]

            return {
                "support": support,
                "resistance": resistance
            }
        except Exception:
            return {"support": [], "resistance": []}

    @staticmethod
    def format_klines_data(candles: Any) -> Optional[Dict[str, np.ndarray]]:
        """Преобразует входные свечи (список словарей, dict массивов или список floats) в Dict[str, np.ndarray]."""
        if not candles:
            return None
        if isinstance(candles, dict) and "high" in candles and isinstance(candles["high"], np.ndarray):
            return candles
        if isinstance(candles, list) and len(candles) > 0:
            if isinstance(candles[0], dict):
                ts_list = [int(c.get("ts", i)) for i, c in enumerate(candles)]
                high_list = [float(c.get("high", c.get("close", 0.0))) for c in candles]
                low_list = [float(c.get("low", c.get("close", 0.0))) for c in candles]
                close_list = [float(c.get("close", 0.0)) for c in candles]
                return {
                    "ts": np.array(ts_list, dtype=np.int64),
                    "high": np.array(high_list, dtype=np.float64),
                    "low": np.array(low_list, dtype=np.float64),
                    "close": np.array(close_list, dtype=np.float64),
                }
            elif isinstance(candles[0], (float, int)):
                arr = np.array(candles, dtype=np.float64)
                return {
                    "ts": np.arange(len(candles), dtype=np.int64),
                    "high": arr.copy(),
                    "low": arr.copy(),
                    "close": arr.copy(),
                }
        return None

    def calculate(self, candles: Any, current_price: Optional[float] = None) -> Dict[str, Any]:
        """
        Вычисляет уровни поддержки/сопротивления и проверяет условие пробоя:
        - LONG: current_price >= resistance_level -> BREAKOUT_LONG
        - SHORT: current_price <= support_level -> BREAKOUT_SHORT
        """
        if not self.is_active or not candles:
            return {"signals": ["UNSTABLE"], "support": [], "resistance": [], "active_res": None, "active_sup": None}

        data = self.format_klines_data(candles)
        if not data:
            return {"signals": ["UNSTABLE"], "support": [], "resistance": [], "active_res": None, "active_sup": None}

        rules = {
            "swing_len": self.swing_len,
            "window": self.window,
            "margin": self.margin,
            "thickness_k": self.thickness_k,
            "max_zones": self.max_zones,
        }

        sr = self.detect_sr_levels(data, rules)
        support = sr.get("support", [])
        resistance = sr.get("resistance", [])

        if not support and not resistance:
            return {"signals": ["UNSTABLE"], "support": [], "resistance": [], "active_res": None, "active_sup": None}

        # Референсная цена для проверки пробоя
        price = current_price
        if price is None or price <= 0:
            if "close" in data and len(data["close"]) > 0:
                price = float(data["close"][-1])
            else:
                price = 0.0

        if price <= 0:
            return {"signals": ["UNSTABLE"], "support": support, "resistance": resistance, "active_res": None, "active_sup": None}

        def get_level_val(rec: dict, is_res: bool) -> float:
            if self.breakout_edge == "h":
                return float(rec["h"])
            elif self.breakout_edge == "l":
                return float(rec["l"])
            else:
                return float((rec["h"] + rec["l"]) / 2)

        active_res = None
        active_sup = None

        if resistance:
            if self.level_mode == "latest":
                active_res = get_level_val(resistance[-1], is_res=True)
            elif self.level_mode == "nearest":
                closest = min(resistance, key=lambda r: abs(get_level_val(r, True) - price))
                active_res = get_level_val(closest, is_res=True)

        if support:
            if self.level_mode == "latest":
                active_sup = get_level_val(support[-1], is_res=False)
            elif self.level_mode == "nearest":
                closest = min(support, key=lambda s: abs(get_level_val(s, False) - price))
                active_sup = get_level_val(closest, is_res=False)

        signals = []
        if self.level_mode == "any":
            if any(price >= get_level_val(r, is_res=True) for r in resistance):
                signals.append("BREAKOUT_LONG")
            if any(price <= get_level_val(s, is_res=False) for s in support):
                signals.append("BREAKOUT_SHORT")
        else:
            if active_res is not None and price >= active_res:
                signals.append("BREAKOUT_LONG")
            if active_sup is not None and price <= active_sup:
                signals.append("BREAKOUT_SHORT")

        return {
            "signals": signals,
            "support": support,
            "resistance": resistance,
            "active_res": active_res,
            "active_sup": active_sup
        }
