# ============================================================
# FILE: CORE/native_math.py
# ROLE: High-performance C/LLVM compiled computational kernels
# ============================================================

from typing import Tuple, List, Optional, Any
import numpy as np

try:
    import numba  # type: ignore
    HAS_NUMBA = True
except ImportError:
    HAS_NUMBA = False

    class _DummyNumba:
        def njit(self, *args: Any, **kwargs: Any) -> Any:
            def decorator(f: Any) -> Any:
                return f
            return decorator

    numba: Any = _DummyNumba()


# ============================================================
# 1. Скомпилированные машинные ядра (JIT LLVM / C-speed / nogil)
# ============================================================

if HAS_NUMBA:
    @numba.njit(fastmath=True, nogil=True)
    def _fast_ema_kernel(prices: np.ndarray, length: int) -> np.ndarray:
        n = len(prices)
        out = np.empty(n - length + 1, dtype=np.float64)
        if n < length:
            return np.empty(0, dtype=np.float64)

        k = 2.0 / (length + 1.0)
        s = 0.0
        for i in range(length):
            s += prices[i]
        ema = s / length
        out[0] = ema

        for i in range(length, n):
            ema = prices[i] * k + ema * (1.0 - k)
            out[i - length + 1] = ema
        return out

    @numba.njit(fastmath=True, nogil=True)
    def _fast_rsi_series_kernel(closes: np.ndarray, length: int) -> np.ndarray:
        n = len(closes)
        if n < length + 1:
            return np.empty(0, dtype=np.float64)

        gains = np.empty(n - 1, dtype=np.float64)
        losses = np.empty(n - 1, dtype=np.float64)
        for i in range(1, n):
            diff = closes[i] - closes[i - 1]
            if diff > 0.0:
                gains[i - 1] = diff
                losses[i - 1] = 0.0
            else:
                gains[i - 1] = 0.0
                losses[i - 1] = -diff

        avg_gain = 0.0
        avg_loss = 0.0
        for i in range(length):
            avg_gain += gains[i]
            avg_loss += losses[i]
        avg_gain /= length
        avg_loss /= length

        num_out = n - length
        out = np.empty(num_out, dtype=np.float64)

        if avg_loss == 0.0 and avg_gain == 0.0:
            out[0] = 50.0
        elif avg_loss == 0.0:
            out[0] = 100.0
        else:
            rs = avg_gain / avg_loss
            out[0] = 100.0 - (100.0 / (1.0 + rs))

        for i in range(length, n - 1):
            avg_gain = (avg_gain * (length - 1.0) + gains[i]) / length
            avg_loss = (avg_loss * (length - 1.0) + losses[i]) / length
            idx = i - length + 1
            if avg_loss == 0.0 and avg_gain == 0.0:
                out[idx] = 50.0
            elif avg_loss == 0.0:
                out[idx] = 100.0
            else:
                rs = avg_gain / avg_loss
                out[idx] = 100.0 - (100.0 / (1.0 + rs))

        return out

    @numba.njit(fastmath=True, nogil=True)
    def _fast_atr_kernel(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, length: int) -> np.ndarray:
        n = len(highs)
        if n < length + 1:
            return np.zeros(n, dtype=np.float64)

        tr = np.empty(n - 1, dtype=np.float64)
        for i in range(1, n):
            tr1 = highs[i] - lows[i]
            tr2 = abs(highs[i] - closes[i - 1])
            tr3 = abs(lows[i] - closes[i - 1])
            tr[i - 1] = max(tr1, max(tr2, tr3))

        atr = np.zeros(n, dtype=np.float64)
        s = 0.0
        for i in range(length):
            s += tr[i]
        curr_atr = s / length
        atr[length] = curr_atr

        for i in range(length, n - 1):
            curr_atr = (curr_atr * (length - 1.0) + tr[i]) / length
            atr[i + 1] = curr_atr

        return atr

    @numba.njit(fastmath=True, nogil=True)
    def _fast_pivots_kernel(highs: np.ndarray, lows: np.ndarray, swing_len: int) -> Tuple[np.ndarray, np.ndarray]:
        n = len(highs)
        pivot_highs = np.zeros(n, dtype=np.float64)
        pivot_lows = np.zeros(n, dtype=np.float64)

        if n < swing_len * 2 + 1:
            return pivot_highs, pivot_lows

        for i in range(swing_len, n - swing_len):
            val_h = highs[i]
            is_ph = True
            for j in range(i - swing_len, i + swing_len + 1):
                if highs[j] > val_h:
                    is_ph = False
                    break
            if is_ph:
                pivot_highs[i] = val_h

            val_l = lows[i]
            is_pl = True
            for j in range(i - swing_len, i + swing_len + 1):
                if lows[j] < val_l:
                    is_pl = False
                    break
            if is_pl:
                pivot_lows[i] = val_l

        return pivot_highs, pivot_lows

    @numba.njit(fastmath=True, nogil=True)
    def _fast_bollinger_keltner_kernel(
        closes: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        length: int,
        bb_mult: float,
        kc_mult: float
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        n = len(closes)
        bb_upper = np.empty(n, dtype=np.float64)
        bb_lower = np.empty(n, dtype=np.float64)
        kc_upper = np.empty(n, dtype=np.float64)
        kc_lower = np.empty(n, dtype=np.float64)

        if n < length:
            return bb_upper, bb_lower, kc_upper, kc_lower

        # 1. TR & ATR
        tr = np.zeros(n, dtype=np.float64)
        for i in range(1, n):
            tr1 = highs[i] - lows[i]
            tr2 = abs(highs[i] - closes[i - 1])
            tr3 = abs(lows[i] - closes[i - 1])
            tr[i] = max(tr1, max(tr2, tr3))

        atr = np.zeros(n, dtype=np.float64)
        s_tr = 0.0
        for i in range(1, length + 1):
            s_tr += tr[i]
        curr_atr = s_tr / length
        atr[length] = curr_atr

        for i in range(length + 1, n):
            curr_atr = (curr_atr * (length - 1.0) + tr[i]) / length
            atr[i] = curr_atr

        # 2. BB (SMA + StdDev) and KC
        for i in range(length - 1, n):
            s = 0.0
            for j in range(i - length + 1, i + 1):
                s += closes[j]
            mean = s / length

            var = 0.0
            for j in range(i - length + 1, i + 1):
                diff = closes[j] - mean
                var += diff * diff
            std = np.sqrt(var / length)

            bb_upper[i] = mean + bb_mult * std
            bb_lower[i] = mean - bb_mult * std
            kc_upper[i] = mean + kc_mult * atr[i]
            kc_lower[i] = mean - kc_mult * atr[i]

        return bb_upper, bb_lower, kc_upper, kc_lower


# ============================================================
# 2. Фасадные безопасные функции (высокоскоростной API)
# ============================================================

class NativeMath:
    """Высокопроизводительный фасад низкоуровневых вычислений."""

    @staticmethod
    def fast_ema(prices: List[float] | np.ndarray, length: int) -> List[float]:
        if not isinstance(prices, np.ndarray):
            arr = np.asarray(prices, dtype=np.float64)
        else:
            arr = prices.astype(np.float64, copy=False)

        if len(arr) < length:
            return []

        if HAS_NUMBA:
            res = _fast_ema_kernel(arr, length)
            return res.tolist()

        # Pure NumPy fallback
        k = 2.0 / (length + 1.0)
        out = [float(np.mean(arr[:length]))]
        ema = out[0]
        for p in arr[length:]:
            ema = p * k + ema * (1.0 - k)
            out.append(ema)
        return out

    @staticmethod
    def fast_rsi_series(closes: List[float] | np.ndarray, length: int = 14) -> List[float]:
        if not isinstance(closes, np.ndarray):
            arr = np.asarray(closes, dtype=np.float64)
        else:
            arr = closes.astype(np.float64, copy=False)

        if len(arr) < length + 1:
            return []

        if HAS_NUMBA:
            res = _fast_rsi_series_kernel(arr, length)
            return res.tolist()

        # Fallback
        diffs = np.diff(arr)
        gains = np.where(diffs > 0, diffs, 0.0)
        losses = np.where(diffs < 0, -diffs, 0.0)
        avg_gain = float(np.mean(gains[:length]))
        avg_loss = float(np.mean(losses[:length]))
        out = [50.0 if avg_loss == 0 and avg_gain == 0 else (100.0 if avg_loss == 0 else 100.0 - (100.0 / (1.0 + avg_gain / avg_loss)))]
        for i in range(length, len(gains)):
            avg_gain = (avg_gain * (length - 1) + gains[i]) / length
            avg_loss = (avg_loss * (length - 1) + losses[i]) / length
            out.append(50.0 if avg_loss == 0 and avg_gain == 0 else (100.0 if avg_loss == 0 else 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))))
        return out

    @staticmethod
    def fast_pivots(highs: np.ndarray, lows: np.ndarray, swing_len: int) -> Tuple[np.ndarray, np.ndarray]:
        if HAS_NUMBA:
            return _fast_pivots_kernel(highs, lows, swing_len)
        n = len(highs)
        ph = np.zeros(n, dtype=np.float64)
        pl = np.zeros(n, dtype=np.float64)
        for i in range(swing_len, n - swing_len):
            if np.all(highs[i] >= highs[i - swing_len:i + swing_len + 1]):
                ph[i] = highs[i]
            if np.all(lows[i] <= lows[i - swing_len:i + swing_len + 1]):
                pl[i] = lows[i]
        return ph, pl

    @staticmethod
    def fast_squeeze(
        closes: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        length: int,
        bb_mult: float,
        kc_mult: float
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        if HAS_NUMBA:
            return _fast_bollinger_keltner_kernel(closes, highs, lows, length, bb_mult, kc_mult)
        # NumPy fallback
        n = len(closes)
        bb_mid = np.convolve(closes, np.ones(length) / length, mode='valid')
        pad = n - len(bb_mid)
        bb_mid = np.pad(bb_mid, (pad, 0), mode='edge')
        stds = np.array([np.std(closes[max(0, i - length + 1):i + 1]) for i in range(n)])
        bb_u = bb_mid + bb_mult * stds
        bb_l = bb_mid - bb_mult * stds
        tr = np.maximum(highs[1:] - lows[1:], np.maximum(np.abs(highs[1:] - closes[:-1]), np.abs(lows[1:] - closes[:-1])))
        atr = np.zeros(n)
        if len(tr) >= length:
            atr[length] = np.mean(tr[:length])
            for i in range(length, len(tr)):
                atr[i + 1] = (atr[i] * (length - 1) + tr[i]) / length
        kc_u = bb_mid + kc_mult * atr
        kc_l = bb_mid - kc_mult * atr
        return bb_u, bb_l, kc_u, kc_l
