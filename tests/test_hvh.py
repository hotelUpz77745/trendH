# ============================================================
# FILE: tests/test_hvh.py
# ROLE: Unit and integration tests for HVH indicator, rules & strategy guide
# ============================================================

import unittest
import numpy as np
from CORE.hvh import HVHCalculator, EntryHVHRule
from CORE.indicators import IndicatorsEngine
from TG.strategy_guide import (
    PROVEN_LEADERS,
    is_proven_leader,
    get_leader_badge,
    format_strategy_guide_text,
    strategy_guide_keyboard,
    strategy_guide_detail_keyboard
)


class TestHVHCalculator(unittest.TestCase):
    """Тестирование чистого математического ядра калькулятора HVH."""

    def setUp(self):
        self.pullback_cfg = {
            "is_active": True,
            "timeframe": "15m",
            "period": 20,
            "dev": 1.5,
            "mode": "rolling",
            "signal_type": "pullback",
            "long_cond": "HVH_LONG",
            "short_cond": "HVH_SHORT"
        }
        self.impulse_cfg = {
            "is_active": True,
            "timeframe": "5m",
            "period": 20,
            "dev": 1.5,
            "mode": "rolling",
            "signal_type": "impulse",
            "long_cond": "HVH_LONG",
            "short_cond": "HVH_SHORT"
        }

    def _generate_candles(self, n: int = 30, base_price: float = 100.0, trend: float = 0.0):
        candles = []
        for i in range(n):
            p = base_price + i * trend
            candles.append({
                "open": p,
                "high": p + 1.0,
                "low": p - 1.0,
                "close": p
            })
        return candles

    def test_insufficient_history(self):
        """При недостатке свечей возвращается UNSTABLE."""
        calc = HVHCalculator(self.pullback_cfg)
        short_candles = self._generate_candles(n=10)
        signals = calc.calculate(short_candles)
        self.assertEqual(signals, ["UNSTABLE"])

    def test_inactive_calculator(self):
        """Неактивный калькулятор возвращает UNSTABLE."""
        cfg = dict(self.pullback_cfg)
        cfg["is_active"] = False
        calc = HVHCalculator(cfg)
        candles = self._generate_candles(n=30)
        self.assertEqual(calc.calculate(candles), ["UNSTABLE"])

    def test_pullback_mode_signals(self):
        """В режиме pullback при перерастяжке вверх генерируется SHORT, вниз — LONG."""
        calc = HVHCalculator(self.pullback_cfg)
        candles = self._generate_candles(n=30, base_price=100.0)

        # Тест нормального рынка внутри полос (нет сигналов)
        state_neutral = calc.get_hvh_state(candles)
        self.assertEqual(state_neutral["signals"], [])
        self.assertEqual(state_neutral["status"], "OK")
        self.assertTrue(state_neutral["lower_band"] < state_neutral["close"] < state_neutral["upper_band"])

        # Выброс цены вверх (сильная перерастяжка)
        candles_spike_up = list(candles)
        candles_spike_up[-1] = {"open": 100.0, "high": 120.0, "low": 99.0, "close": 118.0}
        state_up = calc.get_hvh_state(candles_spike_up)
        self.assertIn("HVH_SHORT", state_up["signals"])

        # Пролив цены вниз (сильная перерастяжка вниз)
        candles_dump = list(candles)
        candles_dump[-1] = {"open": 100.0, "high": 101.0, "low": 80.0, "close": 82.0}
        state_down = calc.get_hvh_state(candles_dump)
        self.assertIn("HVH_LONG", state_down["signals"])

    def test_impulse_mode_signals(self):
        """В режиме impulse при пробое границы вверх генерируется LONG, вниз — SHORT."""
        calc = HVHCalculator(self.impulse_cfg)
        candles = self._generate_candles(n=30, base_price=100.0)

        # Пробой вверх
        candles_spike_up = list(candles)
        candles_spike_up[-1] = {"open": 100.0, "high": 120.0, "low": 99.0, "close": 118.0}
        state_up = calc.get_hvh_state(candles_spike_up)
        self.assertIn("HVH_LONG", state_up["signals"])

        # Пробой вниз
        candles_dump = list(candles)
        candles_dump[-1] = {"open": 100.0, "high": 101.0, "low": 80.0, "close": 82.0}
        state_down = calc.get_hvh_state(candles_dump)
        self.assertIn("HVH_SHORT", state_down["signals"])

    def test_fixed_mode(self):
        """Проверка работы режима fixed девиации."""
        cfg = dict(self.pullback_cfg)
        cfg["mode"] = "fixed"
        calc = HVHCalculator(cfg)
        candles = self._generate_candles(n=30, base_price=100.0)
        state = calc.get_hvh_state(candles)
        self.assertEqual(state["status"], "OK")
        self.assertGreater(state["adj_dev"], 0.0)


class TestEntryHVHRule(unittest.TestCase):
    """Тестирование правила входа EntryHVHRule."""

    def setUp(self):
        self.rule = EntryHVHRule({
            "is_active": True,
            "long_cond": "HVH_LONG",
            "short_cond": "HVH_SHORT"
        })

    def test_check_rule(self):
        # Активный сигнал LONG
        indicators_long = {"hvh": ["HVH_LONG"]}
        self.assertTrue(self.rule.check("LONG", indicators=indicators_long))
        self.assertFalse(self.rule.check("SHORT", indicators=indicators_long))

        # Активный сигнал SHORT
        indicators_short = {"hvh": ["HVH_SHORT"]}
        self.assertFalse(self.rule.check("LONG", indicators=indicators_short))
        self.assertTrue(self.rule.check("SHORT", indicators=indicators_short))

        # Пустой или нестабильный сигнал
        self.assertFalse(self.rule.check("LONG", indicators={"hvh": []}))
        self.assertFalse(self.rule.check("LONG", indicators={"hvh": ["UNSTABLE"]}))


class TestIndicatorsEngineHVH(unittest.TestCase):
    """Тестирование интеграции HVH в IndicatorsEngine."""

    def test_indicators_engine_wiring(self):
        rules = {
            "hvh": {
                "is_active": True,
                "timeframe": "15m",
                "period": 20,
                "dev": 1.8,
                "mode": "rolling",
                "signal_type": "pullback"
            }
        }
        engine = IndicatorsEngine(rules)
        tfs = engine.get_required_timeframes()
        self.assertIn("15m", tfs)

        candles = [{"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0} for _ in range(30)]
        res = engine.calculate({"15m": candles})
        self.assertIn("hvh", res)
        self.assertIsInstance(res["hvh"], list)


class TestStrategyGuideAndLeaders(unittest.TestCase):
    """Тестирование справочника стратегий и маркировки доказанных лидеров."""

    def test_proven_leaders_metadata(self):
        expected_leaders = {"u3_anti_trend", "u15_anti_fade", "u3_anti_aggr"}
        self.assertEqual(set(PROVEN_LEADERS.keys()), expected_leaders)

        for uid in expected_leaders:
            self.assertTrue(is_proven_leader(uid))
            badge = get_leader_badge(uid)
            self.assertIn("💎", badge)
            self.assertIn("PROVEN LEADER", badge)

        self.assertFalse(is_proven_leader("u1"))
        self.assertEqual(get_leader_badge("u1"), "")

    def test_format_strategy_guide(self):
        text_u3 = format_strategy_guide_text("u3_anti_trend")
        self.assertIn("ШПАРГАЛКА", text_u3)
        self.assertIn("PROVEN LEADER", text_u3)
        self.assertIn("70.6%", text_u3)
        self.assertIn("Правила входа", text_u3)
        self.assertIn("Правила выхода", text_u3)

        text_hvh = format_strategy_guide_text("u_hvh_pullback")
        self.assertIn("HVH", text_hvh)
        self.assertIn("MEAN-REVERSION", text_hvh.upper())
        self.assertIn("Grid Stress", text_hvh)

    def test_guide_keyboards(self):
        universes = [
            {"uid": "u3_anti_trend", "name": "Leader 1"},
            {"uid": "u15_anti_fade", "name": "Leader 2"},
            {"uid": "u3_anti_aggr", "name": "Leader 3"},
            {"uid": "u1", "name": "Trend"},
            {"uid": "u_hvh_pullback", "name": "HVH Pullback"}
        ]
        kb = strategy_guide_keyboard(universes, current_uid="u3_anti_trend")
        self.assertIsNotNone(kb)
        self.assertTrue(len(kb.inline_keyboard) > 0)

        detail_kb = strategy_guide_detail_keyboard("u3_anti_trend")
        self.assertIsNotNone(detail_kb)
        self.assertEqual(len(detail_kb.inline_keyboard), 2)


if __name__ == "__main__":
    unittest.main()
