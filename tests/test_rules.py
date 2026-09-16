# ============================================================
# FILE: tests/test_rules.py
# ROLE: Unit tests for Entry & Exit Rules and Signal Engines
# ============================================================

import unittest
from CORE.rules import (
    EntryTrendRule,
    EntryRSIRule,
    EntryRSIWaterlineRule,
    EntrySignalEngine,
    ExitTrendReversalRule,
    ExitTakeProfitRule,
    ExitStopLossRule,
    ExitSignalEngine
)


class TestEntryRules(unittest.TestCase):
    def test_entry_trend_rule_positive(self):
        cfg = {"is_active": True, "trend_positive": True, "long_cond": "UP", "short_cond": "DOWN"}
        rule = EntryTrendRule(cfg, indicator_key="trend")

        # Base trend checks
        self.assertTrue(rule.check("LONG", indicators={"trend": "UP"}))
        self.assertFalse(rule.check("LONG", indicators={"trend": "DOWN"}))
        self.assertFalse(rule.check("LONG", indicators={"trend": "FLAT"}))
        self.assertFalse(rule.check("LONG", indicators={"trend": "UNSTABLE"}))

        self.assertTrue(rule.check("SHORT", indicators={"trend": "DOWN"}))
        self.assertFalse(rule.check("SHORT", indicators={"trend": "UP"}))

    def test_entry_trend_htf_rule(self):
        cfg = {"is_active": True, "trend_positive": True, "long_cond": "UP", "short_cond": "DOWN"}
        rule = EntryTrendRule(cfg, indicator_key="trend_htf")

        self.assertTrue(rule.check("LONG", indicators={"trend": "DOWN", "trend_htf": "UP"}))
        self.assertFalse(rule.check("LONG", indicators={"trend": "UP", "trend_htf": "DOWN"}))

    def test_entry_rsi_rule(self):
        cfg = {"is_active": True}
        rule = EntryRSIRule(cfg)

        self.assertTrue(rule.check("LONG", indicators={"rsi": ["ENTER_LONG"]}))
        self.assertFalse(rule.check("LONG", indicators={"rsi": ["ENTER_SHORT"]}))
        self.assertFalse(rule.check("LONG", indicators={"rsi": ["UNSTABLE"]}))
    def test_entry_rsi_waterline_rule(self):
        cfg = {"is_active": True, "long_cond": "CROSS_UP", "short_cond": "CROSS_DOWN"}
        rule = EntryRSIWaterlineRule(cfg)

        self.assertTrue(rule.check("LONG", indicators={"rsi_waterline50": ["CROSS_UP"]}))
        self.assertFalse(rule.check("LONG", indicators={"rsi_waterline50": ["CROSS_DOWN"]}))
        self.assertFalse(rule.check("LONG", indicators={"rsi_waterline50": []}))
        self.assertFalse(rule.check("LONG", indicators={"rsi_waterline50": ["UNSTABLE"]}))

        self.assertTrue(rule.check("SHORT", indicators={"rsi_waterline50": ["CROSS_DOWN"]}))
        self.assertFalse(rule.check("SHORT", indicators={"rsi_waterline50": ["CROSS_UP"]}))

    def test_entry_signal_engine_combined(self):
        enter_rules = {
            "trend": {"is_active": True, "trend_positive": True, "long_cond": "UP", "short_cond": "DOWN"},
            "trend_htf": {"is_active": True, "trend_positive": True, "long_cond": "UP", "short_cond": "DOWN"},
            "rsi": {"is_active": True},
            "rsi_waterline50": {"is_active": True, "long_cond": "CROSS_UP", "short_cond": "CROSS_DOWN"}
        }
        engine = EntrySignalEngine(enter_rules)

        # All matching
        ind_valid_long = {"trend": "UP", "trend_htf": "UP", "rsi": ["ENTER_LONG"], "rsi_waterline50": ["CROSS_UP"]}
        self.assertTrue(engine.check_signal("LONG", ind_valid_long))

        # Waterline mismatch -> False
        ind_wl_mismatch = {"trend": "UP", "trend_htf": "UP", "rsi": ["ENTER_LONG"], "rsi_waterline50": []}
        self.assertFalse(engine.check_signal("LONG", ind_wl_mismatch))

        # HTF mismatch -> False
        ind_htf_mismatch = {"trend": "UP", "trend_htf": "FLAT", "rsi": ["ENTER_LONG"]}
        self.assertFalse(engine.check_signal("LONG", ind_htf_mismatch))

        # RSI mismatch -> False
        ind_rsi_mismatch = {"trend": "UP", "trend_htf": "UP", "rsi": []}
        self.assertFalse(engine.check_signal("LONG", ind_rsi_mismatch))


class TestExitRules(unittest.TestCase):
    def setUp(self):
        self.analytics_cfg = {"taker_fee_ratio": 0.0006}
        self.slip_fn = lambda s: 0.001

    def test_exit_trend_reversal(self):
        cfg = {"is_active": True, "long_exit_trends": ["FLAT", "DOWN"], "short_exit_trends": ["FLAT", "UP"]}
        rule = ExitTrendReversalRule(cfg)

        self.assertTrue(rule.check("LONG", trend="FLAT"))
        self.assertTrue(rule.check("LONG", trend="DOWN"))
        self.assertFalse(rule.check("LONG", trend="UP"))

        self.assertTrue(rule.check("SHORT", trend="FLAT"))
        self.assertTrue(rule.check("SHORT", trend="UP"))
        self.assertFalse(rule.check("SHORT", trend="DOWN"))

    def test_exit_take_profit(self):
        cfg = {"value": 0.05}
        rule = ExitTakeProfitRule(cfg, self.analytics_cfg, self.slip_fn)

        # 6% gain on LONG minus ~0.32% fees = ~5.68% net > 5% TP
        self.assertTrue(rule.check("LONG", symbol="BTCUSDT", open_price=100.0, current_price=106.0))
        # 2% gain on LONG minus fees = ~1.68% net < 5% TP
        self.assertFalse(rule.check("LONG", symbol="BTCUSDT", open_price=100.0, current_price=102.0))

    def test_exit_stop_loss(self):
        cfg = {"value": 0.03}
        rule = ExitStopLossRule(cfg, self.analytics_cfg, self.slip_fn)

        # 4% loss on LONG minus fees -> net loss ~ -4.32% <= -3% SL
        self.assertTrue(rule.check("LONG", symbol="BTCUSDT", open_price=100.0, current_price=96.0))
        # 1% loss on LONG minus fees -> net loss ~ -1.32% > -3% SL
        self.assertFalse(rule.check("LONG", symbol="BTCUSDT", open_price=100.0, current_price=99.0))

    def test_exit_stop_loss_disabled(self):
        cfg = {"value": None}
        rule = ExitStopLossRule(cfg, self.analytics_cfg, self.slip_fn)

        # Disabled rule must never trigger
        self.assertFalse(rule.check("LONG", symbol="BTCUSDT", open_price=100.0, current_price=50.0))

    def test_exit_signal_engine_priority(self):
        exit_rules = {
            "trend_reversal": {"is_active": True, "long_exit_trends": ["FLAT"], "short_exit_trends": ["FLAT"]},
            "take_profit_ratio": {"value": 0.05},
            "stop_loss_ratio": {"value": 0.03}
        }
        engine = ExitSignalEngine(exit_rules, self.analytics_cfg, self.slip_fn)

        # Exits on FLAT
        self.assertTrue(engine.check_signal("LONG", symbol="BTCUSDT", trend="FLAT", open_price=100.0, current_price=101.0))
        # Exits on TP
        self.assertTrue(engine.check_signal("LONG", symbol="BTCUSDT", trend="UP", open_price=100.0, current_price=107.0))
        # Exits on SL
        self.assertTrue(engine.check_signal("LONG", symbol="BTCUSDT", trend="UP", open_price=100.0, current_price=95.0))
        # Holds position when trend is UP and price is within [-3%, +5%]
        self.assertFalse(engine.check_signal("LONG", symbol="BTCUSDT", trend="UP", open_price=100.0, current_price=101.0))


if __name__ == "__main__":
    unittest.main()
