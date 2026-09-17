# ============================================================
# FILE: tests/test_native_math.py
# ROLE: Unit tests for compiled C/LLVM NativeMath computational kernels
# ============================================================

import unittest
import time
import numpy as np
from CORE.native_math import NativeMath, HAS_NUMBA


class TestNativeMath(unittest.TestCase):
    def test_numba_availability(self):
        """Проверка наличия Numba JIT в окружении."""
        self.assertTrue(HAS_NUMBA, "Numba JIT должна быть доступна в окружении.")

    def test_fast_ema_accuracy(self):
        """Сравнение NativeMath.fast_ema с эталонным расчетом EMA."""
        prices = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0]
        length = 5
        ema = NativeMath.fast_ema(prices, length)

        self.assertEqual(len(ema), len(prices) - length + 1)
        # Первое значение должно быть SMA: (10 + 11 + 12 + 13 + 14) / 5 = 12.0
        self.assertAlmostEqual(ema[0], 12.0)

        # Проверка последующих значений
        k = 2.0 / (length + 1.0)
        expected_second = 15.0 * k + 12.0 * (1.0 - k)
        self.assertAlmostEqual(ema[1], expected_second)

    def test_fast_ema_edge_cases(self):
        """Проверка граничных случаев для EMA."""
        self.assertEqual(NativeMath.fast_ema([], 5), [])
        self.assertEqual(NativeMath.fast_ema([10.0, 12.0], 5), [])
        self.assertEqual(len(NativeMath.fast_ema([1.0] * 10, 3)), 8)

    def test_fast_ema_numpy_input(self):
        """Проверка работы fast_ema при передаче numpy array вместо списка."""
        arr = np.array([10.0, 12.0, 14.0, 16.0, 18.0], dtype=np.float64)
        ema = NativeMath.fast_ema(arr, 3)
        self.assertEqual(len(ema), 3)
        self.assertAlmostEqual(ema[0], 12.0)

    def test_fast_rsi_series_accuracy(self):
        """Проверка точности Wilder's RSI серии в NativeMath."""
        closes = [
            44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84,
            46.08, 45.89, 46.03, 45.61, 46.28, 46.28, 46.00, 46.03, 46.41,
            46.22, 45.64, 46.21, 46.25, 45.71, 46.45, 45.78, 45.35, 44.03
        ]
        rsi_series = NativeMath.fast_rsi_series(closes, length=14)
        self.assertTrue(len(rsi_series) > 0)
        for val in rsi_series:
            self.assertGreaterEqual(val, 0.0)
            self.assertLessEqual(val, 100.0)

    def test_fast_rsi_extreme_cases(self):
        """Проверка экстремальных монотонных движений для RSI."""
        rising = [float(i) for i in range(1, 20)]
        rsi_up = NativeMath.fast_rsi_series(rising, length=5)
        self.assertAlmostEqual(rsi_up[-1], 100.0)

        falling = [float(20 - i) for i in range(20)]
        rsi_down = NativeMath.fast_rsi_series(falling, length=5)
        self.assertAlmostEqual(rsi_down[-1], 0.0)

        flat = [100.0] * 20
        rsi_flat = NativeMath.fast_rsi_series(flat, length=5)
        self.assertAlmostEqual(rsi_flat[-1], 50.0)

    def test_fast_rsi_short_input(self):
        """Проверка работы fast_rsi_series с коротким массивом."""
        self.assertEqual(NativeMath.fast_rsi_series([], 14), [])
        self.assertEqual(NativeMath.fast_rsi_series([10.0, 11.0], 14), [])

    def test_fast_pivots(self):
        """Проверка нахождения опорных экстремумов (Pivots) для LuxAlgo уровней."""
        highs = np.array([10.0, 11.0, 15.0, 12.0, 10.0, 14.0, 20.0, 16.0, 12.0, 11.0])
        lows = np.array([9.0, 10.0, 12.0, 9.0, 5.0, 11.0, 14.0, 11.0, 8.0, 9.0])
        swing_len = 2

        ph, pl = NativeMath.fast_pivots(highs, lows, swing_len)

        self.assertEqual(len(ph), len(highs))
        self.assertEqual(len(pl), len(lows))
        self.assertEqual(ph[2], 15.0)
        self.assertEqual(ph[6], 20.0)
        self.assertEqual(pl[4], 5.0)

    def test_fast_pivots_short_array(self):
        """Проверка fast_pivots на массиве короче удвоенного swing_len."""
        highs = np.array([10.0, 11.0])
        lows = np.array([9.0, 10.0])
        ph, pl = NativeMath.fast_pivots(highs, lows, 3)
        self.assertTrue(np.all(ph == 0.0))
        self.assertTrue(np.all(pl == 0.0))

    def test_fast_squeeze_computation(self):
        """Проверка расчета сжатия полос Боллинджера и каналов Кельтнера."""
        n = 50
        closes = np.linspace(100.0, 110.0, n)
        highs = closes + 1.5
        lows = closes - 1.5

        bb_u, bb_l, kc_u, kc_l = NativeMath.fast_squeeze(closes, highs, lows, length=20, bb_mult=2.0, kc_mult=1.5)

        self.assertEqual(len(bb_u), n)
        self.assertEqual(len(bb_l), n)
        self.assertEqual(len(kc_u), n)
        self.assertEqual(len(kc_l), n)

        for i in range(20, n):
            self.assertGreater(bb_u[i], bb_l[i])
            self.assertGreater(kc_u[i], kc_l[i])

    def test_fast_squeeze_short_input(self):
        """Проверка fast_squeeze на длине меньше периода индикатора."""
        closes = np.array([100.0, 101.0, 102.0])
        highs = closes + 1.0
        lows = closes - 1.0
        bb_u, bb_l, kc_u, kc_l = NativeMath.fast_squeeze(closes, highs, lows, length=10, bb_mult=2.0, kc_mult=1.5)
        self.assertEqual(len(bb_u), 3)

    def test_indicators_math_integration(self):
        """Проверка обратной совместимости вызовов IndicatorsMath с NativeMath."""
        from CORE.indicators import IndicatorsMath

        prices = [10.0, 12.0, 14.0, 16.0, 18.0, 20.0]
        ema = IndicatorsMath.calc_ema(prices, 3)
        self.assertEqual(len(ema), 4)

        rsi_val = IndicatorsMath.calc_rsi(prices, 3)
        self.assertIsNotNone(rsi_val)
        self.assertAlmostEqual(rsi_val, 100.0)

    def test_large_dataset_performance(self):
        """Стресс-тест производительности C/LLVM ядра на 5,000 свечах."""
        np.random.seed(42)
        n = 5000
        closes = np.cumsum(np.random.randn(n)) + 1000.0

        t0 = time.perf_counter()
        ema = NativeMath.fast_ema(closes, 50)
        t_ema = time.perf_counter() - t0

        t1 = time.perf_counter()
        rsi = NativeMath.fast_rsi_series(closes, 14)
        t_rsi = time.perf_counter() - t1

        self.assertEqual(len(ema), n - 50 + 1)
        self.assertEqual(len(rsi), n - 14)
        # 5000 свечей должны рассчитываться быстрее 100 мс на скомпилированном ядре
        self.assertLess(t_ema, 0.1, f"fast_ema занял {t_ema:.4f}s")
        self.assertLess(t_rsi, 0.1, f"fast_rsi занял {t_rsi:.4f}s")


if __name__ == "__main__":
    unittest.main()
