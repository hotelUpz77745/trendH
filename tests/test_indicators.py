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
            }
        }
        # In Python true is True
        self.enter_rules["trend_htf"]["trend_positive"] = True
        self.engine = IndicatorsEngine(self.enter_rules)

    def test_required_timeframes(self):
        tfs = self.engine.get_required_timeframes()
        self.assertEqual(tfs, {"5m", "1h", "15m"})

    def test_calculate_facade(self):
        closes_5m = [10.0 + i * 1.5 for i in range(30)]
        closes_1h = [100.0 - i * 1.0 for i in range(30)]
        closes_15m = [50.0 + i * 0.5 for i in range(30)]
        data = {
            "5m": closes_5m,
            "1h": closes_1h,
            "15m": closes_15m
        }
        result = self.engine.calculate(data)
        self.assertIn("trend", result)
        self.assertIn("trend_htf", result)
        self.assertIn("rsi", result)
        self.assertEqual(result["trend"], "UP")
        self.assertEqual(result["trend_htf"], "DOWN")
        self.assertEqual(result["rsi"], [])


if __name__ == "__main__":
    unittest.main()
