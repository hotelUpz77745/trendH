# ============================================================
# FILE: tests/test_indicators.py
# ROLE: Unit tests for IndicatorsEngine, TrendCalculator, and RSICalculator
# ============================================================

import unittest
from CORE.indicators import (
    IndicatorsMath,
    TrendCalculator,
    RSICalculator,
    RSIWaterlineCalculator,
    SRLevelsCalculator,
    EMACrossCalculator,
    VolumeFilterCalculator,
    IndicatorsEngine
)


class TestIndicatorsMath(unittest.TestCase):
    def test_ema_empty_and_short(self):
        self.assertEqual(IndicatorsMath.calc_ema([], 5), [])
        self.assertEqual(IndicatorsMath.calc_ema([10.0, 11.0], 5), [])

    def test_ema_calculation(self):
        prices = [10.0, 10.0, 10.0, 10.0, 10.0, 10.0]
        ema = IndicatorsMath.calc_ema(prices, 3)
        self.assertEqual(len(ema), 4)
        for val in ema:
            self.assertAlmostEqual(val, 10.0, places=4)

    def test_rsi_flat_prices(self):
        prices = [100.0] * 30
        rsi = IndicatorsMath.calc_rsi(prices, 14)
        self.assertAlmostEqual(rsi, 50.0, places=1)

    def test_rsi_purely_rising(self):
        prices = [float(i) for i in range(1, 40)]
        rsi = IndicatorsMath.calc_rsi(prices, 14)
        self.assertEqual(rsi, 100.0)

    def test_rsi_purely_falling(self):
        prices = [float(100 - i) for i in range(40)]
        rsi = IndicatorsMath.calc_rsi(prices, 14)
        self.assertAlmostEqual(rsi, 0.0, places=1)


class TestTrendCalculator(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            "is_active": True,
            "timeframe": "5m",
            "sma_fast": 5,
            "sma_slow": 10,
            "confirmation_candles": 3,
            "require_rising": True
        }
        self.calc = TrendCalculator(self.cfg)

    def test_insufficient_data(self):
        self.assertEqual(self.calc.calculate([100.0, 101.0]), "UNSTABLE")

    def test_trend_up(self):
        # Строго растущий сильный тренд
        prices = [10.0 + i * 2.0 for i in range(30)]
        self.assertEqual(self.calc.calculate(prices), "UP")

    def test_trend_down(self):
        # Строго падающий сильный тренд
        prices = [100.0 - i * 2.0 for i in range(30)]
        self.assertEqual(self.calc.calculate(prices), "DOWN")

    def test_trend_flat(self):
        # Боковик / осцилляции вокруг одного значения
        prices = [10.0, 10.1, 9.9, 10.0, 10.1, 9.9] * 5
        self.assertIn(self.calc.calculate(prices), ["FLAT", "UNSTABLE"])


class TestRSICalculator(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            "is_active": True,
            "timeframe": "15m",
            "window": 14,
            "conditions": {
                "ENTER_LONG": "50 < x <= 75",
                "ENTER_SHORT": "25 <= x < 50"
            }
        }
        self.calc = RSICalculator(self.cfg)

    def test_insufficient_data(self):
        self.assertEqual(self.calc.calculate([100.0] * 10), ["UNSTABLE"])

    def test_rsi_neutral(self):
        prices = [100.0] * 30
        self.assertEqual(self.calc.calculate(prices), [])


class TestRSIWaterlineCalculator(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            "is_active": True,
            "timeframe": "5m",
            "window": 14,
            "waterline": 50.0,
            "long_cond": "CROSS_UP",
            "short_cond": "CROSS_DOWN"
        }
        self.calc = RSIWaterlineCalculator(self.cfg)

    def test_cross_up(self):
        # Falling prices to put RSI below 50, then a big upward jump
        prices = [100.0 - i * 1.0 for i in range(20)] + [150.0]
        states = self.calc.calculate(prices)
        self.assertIn("CROSS_UP", states)

    def test_cross_down(self):
        # Rising prices to put RSI above 50, then a big drop
        prices = [10.0 + i * 1.0 for i in range(20)] + [5.0]
        states = self.calc.calculate(prices)
        self.assertIn("CROSS_DOWN", states)


class TestSRLevelsCalculator(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            "is_active": True,
            "timeframe": "5m",
            "swing_len": 5,
            "window": 100,
            "margin": 2.0,
            "thickness_k": 0.17,
            "max_zones": 5,
            "level_mode": "latest",
            "breakout_edge": "h",
            "long_cond": "BREAKOUT_LONG",
            "short_cond": "BREAKOUT_SHORT"
        }
        self.calc = SRLevelsCalculator(self.cfg)

    def test_sr_levels_breakout_long(self):
        # Create candles with a peak (resistance) in the middle, then price breaking above it
        candles = []
        base_ts = 1700000000000
        # 15 bars rising to 100, then dropping to 80, then rising to 105 (breakout)
        prices = [50 + i * 5 for i in range(11)] + [100 - i * 4 for i in range(1, 6)] + [80 + i * 6 for i in range(1, 6)]
        for i, p in enumerate(prices):
            candles.append({
                "ts": base_ts + i * 60000,
                "open": float(p - 1),
                "high": float(p + 1),
                "low": float(p - 1),
                "close": float(p),
                "volume": 100.0
            })
        
        result = self.calc.calculate(candles, current_price=110.0)
        self.assertIn("support", result)
        self.assertIn("resistance", result)
        self.assertIn("BREAKOUT_LONG", result["signals"])

    def test_sr_levels_breakout_short(self):
        # Create candles with a trough (support), then price dropping below it
        candles = []
        base_ts = 1700000000000
        prices = [100 - i * 5 for i in range(11)] + [50 + i * 4 for i in range(1, 6)] + [70 - i * 6 for i in range(1, 6)]
        for i, p in enumerate(prices):
            candles.append({
                "ts": base_ts + i * 60000,
                "open": float(p + 1),
                "high": float(p + 1),
                "low": float(p - 1),
                "close": float(p),
                "volume": 100.0
            })
        
        result = self.calc.calculate(candles, current_price=30.0)
        self.assertIn("BREAKOUT_SHORT", result["signals"])


class TestEMACrossCalculator(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            "is_active": True,
            "timeframe": "5m",
            "period1": 5,
            "period2": 10,
            "long_cond": "CROSS_UP",
            "short_cond": "CROSS_DOWN"
        }
        self.calc = EMACrossCalculator(self.cfg)

    def test_insufficient_data(self):
        self.assertEqual(self.calc.calculate([10.0] * 5), ["UNSTABLE"])

    def test_ema_cross_up_with_impulse(self):
        # Long downtrend so ema1 < ema2, then explosive upside surge
        prices = [100.0 - i * 2.0 for i in range(25)] + [80.0, 110.0, 150.0]
        states = self.calc.calculate(prices)
        self.assertIn("CROSS_UP", states)

    def test_ema_cross_down_with_impulse(self):
        # Long uptrend so ema1 > ema2, then sharp downward plunge
        prices = [10.0 + i * 2.0 for i in range(25)] + [50.0, 30.0, 5.0]
        states = self.calc.calculate(prices)
        self.assertIn("CROSS_DOWN", states)


class TestVolumeFilterCalculator(unittest.TestCase):
    def test_insufficient_data(self):
        cfg = {"is_active": True, "timeframe": "1m", "mode": "a", "period": 14, "a": {"slice_factor": 1.1}}
        calc = VolumeFilterCalculator(cfg)
        self.assertEqual(calc.calculate([100.0] * 10), ["UNSTABLE"])

    def test_mode_a_passed(self):
        cfg = {"is_active": True, "timeframe": "1m", "mode": "a", "period": 5, "a": {"slice_factor": 1.1}}
        calc = VolumeFilterCalculator(cfg)
        # Previous 5 volumes: 100, max is 100. Last volume: 115 (> 100 * 1.1 = 110)
        vols = [100.0, 95.0, 100.0, 90.0, 98.0, 115.0]
        self.assertEqual(calc.calculate(vols), ["VOLF_PASSED"])

    def test_mode_a_failed(self):
        cfg = {"is_active": True, "timeframe": "1m", "mode": "a", "period": 5, "a": {"slice_factor": 1.1}}
        calc = VolumeFilterCalculator(cfg)
        # Previous 5 volumes: 100, max is 100. Last volume: 105 (<= 110)
        vols = [100.0, 95.0, 100.0, 90.0, 98.0, 105.0]
        self.assertEqual(calc.calculate(vols), [])

    def test_mode_r_passed(self):
        cfg = {"is_active": True, "timeframe": "1m", "mode": "r", "period": 5, "r": {"slice_factor": 2.0}}
        calc = VolumeFilterCalculator(cfg)
        # Previous 5 volumes: 50, avg is 50. Last volume: 105 (> 50 * 2.0 = 100)
        vols = [50.0, 50.0, 50.0, 50.0, 50.0, 105.0]
        self.assertEqual(calc.calculate(vols), ["VOLF_PASSED"])

    def test_mode_r_failed(self):
        cfg = {"is_active": True, "timeframe": "1m", "mode": "r", "period": 5, "r": {"slice_factor": 2.0}}
        calc = VolumeFilterCalculator(cfg)
        # Previous 5 volumes: 50, avg is 50. Last volume: 95 (<= 100)
        vols = [50.0, 50.0, 50.0, 50.0, 50.0, 95.0]
        self.assertEqual(calc.calculate(vols), [])

    def test_with_candle_dicts(self):
        cfg = {"is_active": True, "timeframe": "1m", "mode": "a", "period": 3, "a": {"slice_factor": 1.1}}
        calc = VolumeFilterCalculator(cfg)
        candles = [
            {"ts": 1, "open": 10, "high": 11, "low": 9, "close": 10, "volume": 100.0},
            {"ts": 2, "open": 10, "high": 11, "low": 9, "close": 10, "volume": 100.0},
            {"ts": 3, "open": 10, "high": 11, "low": 9, "close": 10, "volume": 100.0},
            {"ts": 4, "open": 10, "high": 11, "low": 9, "close": 10, "volume": 120.0},
        ]
        self.assertEqual(calc.calculate(candles), ["VOLF_PASSED"])


class TestIndicatorsEngine(unittest.TestCase):
    def setUp(self):
        self.enter_rules = {
            "trend": {
                "is_active": True,
                "timeframe": "5m",
                "sma_fast": 5,
                "sma_slow": 10,
                "confirmation_candles": 3,
                "require_rising": True,
                "trend_positive": True,
                "long_cond": "UP",
                "short_cond": "DOWN"
            },
            "trend_htf": {
                "is_active": True,
                "timeframe": "1h",
                "sma_fast": 5,
                "sma_slow": 10,
                "confirmation_candles": 2,
                "require_rising": False,
                "trend_positive": True,
                "long_cond": "UP",
                "short_cond": "DOWN"
            },
            "rsi": {
                "is_active": True,
                "timeframe": "15m",
                "window": 14,
                "conditions": {
                    "ENTER_LONG": "50 < x <= 75",
                    "ENTER_SHORT": "25 <= x < 50"
                }
            },
            "sr_levels": {
                "is_active": True,
                "timeframe": "5m",
                "swing_len": 5,
                "window": 100,
                "margin": 2.0,
                "thickness_k": 0.17,
                "max_zones": 5,
                "level_mode": "latest",
                "breakout_edge": "h",
                "long_cond": "BREAKOUT_LONG",
                "short_cond": "BREAKOUT_SHORT"
            },
            "ema_cross": {
                "is_active": True,
                "timeframe": "5m",
                "period1": 5,
                "period2": 10,
                "long_cond": "CROSS_UP",
                "short_cond": "CROSS_DOWN"
            },
            "vol_filter": {
                "is_active": True,
                "timeframe": "1m",
                "mode": "a",
                "period": 5,
                "a": {"slice_factor": 1.1},
                "r": {"slice_factor": 2.1},
                "long_cond": "VOLF_PASSED",
                "short_cond": "VOLF_PASSED"
            }
        }
        self.engine = IndicatorsEngine(self.enter_rules)

    def test_required_timeframes(self):
        tfs = self.engine.get_required_timeframes()
        self.assertEqual(tfs, {"5m", "1h", "15m", "1m"})

    def test_calculate_facade(self):
        closes_5m = [10.0 + i * 1.5 for i in range(30)]
        closes_1h = [100.0 - i * 1.0 for i in range(30)]
        closes_15m = [50.0 + i * 0.5 for i in range(30)]
        vols_1m = [{"ts": i, "open": 10, "high": 11, "low": 9, "close": 10, "volume": 100.0} for i in range(10)]
        vols_1m.append({"ts": 10, "open": 10, "high": 11, "low": 9, "close": 10, "volume": 150.0})
        data = {
            "5m": closes_5m,
            "1h": closes_1h,
            "15m": closes_15m,
            "1m": vols_1m
        }
        result = self.engine.calculate(data, current_price=60.0)
        self.assertIn("trend", result)
        self.assertIn("trend_htf", result)
        self.assertIn("rsi", result)
        self.assertIn("sr_levels", result)
        self.assertIn("ema_cross", result)
        self.assertIn("vol_filter", result)
        self.assertEqual(result["trend"], "UP")
        self.assertEqual(result["trend_htf"], "DOWN")
        self.assertEqual(result["rsi"], [])
        self.assertEqual(result["vol_filter"], ["VOLF_PASSED"])


if __name__ == "__main__":
    unittest.main()
