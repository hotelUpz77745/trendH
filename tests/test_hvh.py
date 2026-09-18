# ============================================================
# FILE: tests/test_hvh.py
# ROLE: Unit and integration tests for HVH indicator, rules & strategy guide
# ============================================================

import unittest
import numpy as np
from CORE.indicators.hvh import HVHCalculator, EntryHVHRule
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
        expected_leaders = {"u3_reverse_trend", "u15_reverse_fade"}
        self.assertEqual(set(PROVEN_LEADERS.keys()), expected_leaders)

        for uid in expected_leaders:
            self.assertTrue(is_proven_leader(uid))
            badge = get_leader_badge(uid)
            self.assertIn("💎", badge)
            self.assertIn("PROVEN LEADER", badge)

        self.assertFalse(is_proven_leader("u3_reverse_aggr"))
        self.assertEqual(get_leader_badge("u3_reverse_aggr"), "")
        self.assertFalse(is_proven_leader("u1"))
        self.assertEqual(get_leader_badge("u1"), "")

    def test_format_strategy_guide(self):
        text_u3 = format_strategy_guide_text("u3_reverse_trend")
        self.assertIn("ШПАРГАЛКА", text_u3)
        self.assertIn("PROVEN LEADER", text_u3)
        self.assertIn("70.6%", text_u3)
        self.assertIn("Правила входа", text_u3)
        self.assertIn("Правила выхода", text_u3)

        text_sq = format_strategy_guide_text("u_sq_hvh_impulse")
        self.assertIn("SQUEEZE", text_sq.upper())
        self.assertIn("HVH", text_sq)

        text_hvh = format_strategy_guide_text("u_hvh_pullback")
        self.assertIn("HVH", text_hvh)
        self.assertIn("MEAN-REVERSION", text_hvh.upper())
        self.assertIn("Grid Stress", text_hvh)

    def test_guide_keyboards(self):
        universes = [
            {"uid": "u3_reverse_trend", "name": "Leader 1"},
            {"uid": "u15_reverse_fade", "name": "Leader 2"},
            {"uid": "u3_reverse_aggr", "name": "High Churn"},
            {"uid": "u1", "name": "Trend"},
            {"uid": "u_hvh_pullback", "name": "HVH Pullback"}
        ]
        kb = strategy_guide_keyboard(universes, current_uid="u3_reverse_trend")
        self.assertIsNotNone(kb)
        self.assertTrue(len(kb.inline_keyboard) > 0)

        detail_kb = strategy_guide_detail_keyboard("u3_reverse_trend")
        self.assertIsNotNone(detail_kb)
        self.assertEqual(len(detail_kb.inline_keyboard), 2)


class TestSqueezeHVHStrategies(unittest.TestCase):
    """Тестирование вселенных на стыке Squeeze + HVH Breakout/Fade."""

    def test_sq_hvh_impulse_entry_logic(self):
        from consts import load_config
        from CORE.universe import UniverseManager
        cfg_data = load_config()
        u_cfg = cfg_data.get("universes", {})
        self.assertIn("u_sq_hvh_impulse", u_cfg)

        mgr = UniverseManager(
            universes_cfg={"u_sq_hvh_impulse": u_cfg["u_sq_hvh_impulse"]},
            default_enter_rules={},
            default_exit_rules={},
            get_slippage_ratio_fn=lambda s: 0.001
        )
        univ = mgr.get_universe("u_sq_hvh_impulse")

        # Bullish Squeeze Fire + HVH Breakout + HTF UP
        ind_long = {
            "trend_htf": "UP",
            "volatility_squeeze": ["SQUEEZE_LONG"],
            "hvh": ["HVH_IMPULSE_LONG"]
        }
        self.assertTrue(univ.check_entry("LONG", ind_long))
        self.assertFalse(univ.check_entry("SHORT", ind_long))

        # Bearish Squeeze Fire + HVH Breakout + HTF DOWN
        ind_short = {
            "trend_htf": "DOWN",
            "volatility_squeeze": ["SQUEEZE_SHORT"],
            "hvh": ["HVH_IMPULSE_SHORT"]
        }
        self.assertTrue(univ.check_entry("SHORT", ind_short))
        self.assertFalse(univ.check_entry("LONG", ind_short))

        # Missing squeeze signal -> No entry
        ind_no_sq = {
            "trend_htf": "UP",
            "volatility_squeeze": ["SQUEEZE_ON"],
            "hvh": ["HVH_IMPULSE_LONG"]
        }
        self.assertFalse(univ.check_entry("LONG", ind_no_sq))

    def test_sq_hvh_reverse_climax_logic(self):
        from consts import load_config
        from CORE.universe import UniverseManager
        cfg_data = load_config()
        u_cfg = cfg_data.get("universes", {})
        self.assertIn("u_sq_hvh_reverse", u_cfg)

        u_sq_cfg = dict(u_cfg["u_sq_hvh_reverse"], is_active=True)
        mgr = UniverseManager(
            universes_cfg={"u_sq_hvh_reverse": u_sq_cfg},
            default_enter_rules={},
            default_exit_rules={},
            get_slippage_ratio_fn=lambda s: 0.001
        )
        univ = mgr.get_universe("u_sq_hvh_reverse")

        # False dump: Squeeze PREV ON + HVH Pullback LONG + Bear Exhausted -> LONG Entry
        ind_rev_long = {
            "volatility_squeeze": ["SQUEEZE_PREV_ON", "SQUEEZE_COMPRESSED"],
            "hvh": ["HVH_PULLBACK_LONG"],
            "taker_flow": ["BEAR_EXHAUSTED"]
        }
        self.assertTrue(univ.check_entry("LONG", ind_rev_long))
        self.assertFalse(univ.check_entry("SHORT", ind_rev_long))

        # False pump: Squeeze PREV ON + HVH Pullback SHORT + Bull Exhausted -> SHORT Entry
        ind_rev_short = {
            "volatility_squeeze": ["SQUEEZE_PREV_ON", "SQUEEZE_COMPRESSED"],
            "hvh": ["HVH_PULLBACK_SHORT"],
            "taker_flow": ["BULL_EXHAUSTED"]
        }
        self.assertTrue(univ.check_entry("SHORT", ind_rev_short))
        self.assertFalse(univ.check_entry("LONG", ind_rev_short))

    def test_squeeze_calculator_ignore_last_bars(self):
        """Проверка, что ignore_last_bars=2 корректно исключает последние свечи из проверки сжатия."""
        from CORE.indicators.squeeze_flow import VolatilitySqueezeCalculator
        calc = VolatilitySqueezeCalculator({
            "is_active": True,
            "timeframe": "5m",
            "bb_length": 10,
            "bb_mult": 2.0,
            "kc_mult": 1.5,
            "lookback_squeeze": 10,
            "ignore_last_bars": 2,
            "min_squeeze_bars": 3
        })
        # Сначала узкий флэт (сжатие 25 свечей), затем на последних 2 свечах резкий взрыв цены вверх
        candles = []
        for i in range(25):
            candles.append({"open": 100.0, "high": 100.2, "low": 99.8, "close": 100.0, "volume": 10.0})
        # Взрыв на последних двух свечах
        candles.append({"open": 100.0, "high": 110.0, "low": 99.8, "close": 108.0, "volume": 500.0})
        candles.append({"open": 108.0, "high": 120.0, "low": 107.5, "close": 118.0, "volume": 1000.0})

        signals = calc.calculate(candles)
        # Так как последние 2 свечи исключены из проверки сжатия, предшествующее сжатие обнаружено
        self.assertIn("SQUEEZE_PREV_ON", signals)
        self.assertIn("SQUEEZE_LONG", signals)


if __name__ == "__main__":
    unittest.main()
