# ============================================================
# FILE: tests/test_rules.py
# ROLE: Unit tests for Entry & Exit Rules and Signal Engines
# ============================================================

import unittest
from CORE.rules import (
    EntryTrendRule,
    EntryRSIRule,
    EntryRSIWaterlineRule,
    EntrySRLevelsRule,
    EntryEMACrossRule,
    EntryVolumeFilterRule,
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

        # Custom conditions directly from config (e.g. anti-strategy)
        anti_cfg = {
            "is_active": True,
            "conditions": {
                "ENTER_LONG": "40 <= x < 50",
                "ENTER_SHORT": "50 < x <= 60"
            }
        }
        anti_rule = EntryRSIRule(anti_cfg)
        self.assertTrue(anti_rule.check("SHORT", indicators={"rsi_value": 55.0}))
        self.assertFalse(anti_rule.check("LONG", indicators={"rsi_value": 55.0}))
        self.assertTrue(anti_rule.check("LONG", indicators={"rsi_value": 45.0}))
        self.assertFalse(anti_rule.check("SHORT", indicators={"rsi_value": 45.0}))


    def test_entry_rsi_waterline_rule(self):
        cfg = {"is_active": True, "long_cond": "CROSS_UP", "short_cond": "CROSS_DOWN"}
        rule = EntryRSIWaterlineRule(cfg)

        self.assertTrue(rule.check("LONG", indicators={"rsi_waterline50": ["CROSS_UP"]}))
        self.assertFalse(rule.check("LONG", indicators={"rsi_waterline50": ["CROSS_DOWN"]}))
        self.assertFalse(rule.check("LONG", indicators={"rsi_waterline50": []}))
        self.assertFalse(rule.check("LONG", indicators={"rsi_waterline50": ["UNSTABLE"]}))

        self.assertTrue(rule.check("SHORT", indicators={"rsi_waterline50": ["CROSS_DOWN"]}))
        self.assertFalse(rule.check("SHORT", indicators={"rsi_waterline50": ["CROSS_UP"]}))

    def test_entry_sr_levels_rule(self):
        cfg = {"is_active": True, "long_cond": "BREAKOUT_LONG", "short_cond": "BREAKOUT_SHORT"}
        rule = EntrySRLevelsRule(cfg)

        self.assertTrue(rule.check("LONG", indicators={"sr_levels": ["BREAKOUT_LONG"]}))
        self.assertFalse(rule.check("LONG", indicators={"sr_levels": ["BREAKOUT_SHORT"]}))
        self.assertFalse(rule.check("LONG", indicators={"sr_levels": []}))
        self.assertFalse(rule.check("LONG", indicators={"sr_levels": ["UNSTABLE"]}))

        self.assertTrue(rule.check("SHORT", indicators={"sr_levels": ["BREAKOUT_SHORT"]}))
        self.assertFalse(rule.check("SHORT", indicators={"sr_levels": ["BREAKOUT_LONG"]}))

    def test_entry_ema_cross_rule(self):
        cfg = {"is_active": True, "long_cond": "CROSS_UP", "short_cond": "CROSS_DOWN"}
        rule = EntryEMACrossRule(cfg)

        self.assertTrue(rule.check("LONG", indicators={"ema_cross": ["CROSS_UP"]}))
        self.assertFalse(rule.check("LONG", indicators={"ema_cross": ["CROSS_DOWN"]}))
        self.assertFalse(rule.check("LONG", indicators={"ema_cross": []}))
        self.assertFalse(rule.check("LONG", indicators={"ema_cross": ["UNSTABLE"]}))

        self.assertTrue(rule.check("SHORT", indicators={"ema_cross": ["CROSS_DOWN"]}))
        self.assertFalse(rule.check("SHORT", indicators={"ema_cross": ["CROSS_UP"]}))

    def test_entry_volume_filter_rule(self):
        cfg = {"is_active": True, "long_cond": "VOLF_PASSED", "short_cond": "VOLF_PASSED"}
        rule = EntryVolumeFilterRule(cfg)

        self.assertTrue(rule.check("LONG", indicators={"vol_filter": ["VOLF_PASSED"]}))
        self.assertFalse(rule.check("LONG", indicators={"vol_filter": []}))
        self.assertFalse(rule.check("LONG", indicators={"vol_filter": ["UNSTABLE"]}))

        self.assertTrue(rule.check("SHORT", indicators={"vol_filter": ["VOLF_PASSED"]}))
        self.assertFalse(rule.check("SHORT", indicators={"vol_filter": []}))

    def test_entry_signal_engine_combined(self):
        enter_rules = {
            "trend": {"is_active": True, "trend_positive": True, "long_cond": "UP", "short_cond": "DOWN"},
            "trend_htf": {"is_active": True, "trend_positive": True, "long_cond": "UP", "short_cond": "DOWN"},
            "rsi": {"is_active": True},
            "rsi_waterline50": {"is_active": True, "long_cond": "CROSS_UP", "short_cond": "CROSS_DOWN"},
            "sr_levels": {"is_active": True, "long_cond": "BREAKOUT_LONG", "short_cond": "BREAKOUT_SHORT"},
            "ema_cross": {"is_active": True, "long_cond": "CROSS_UP", "short_cond": "CROSS_DOWN"},
            "vol_filter": {"is_active": True, "long_cond": "VOLF_PASSED", "short_cond": "VOLF_PASSED"}
        }
        engine = EntrySignalEngine(enter_rules)

        # All matching
        ind_valid_long = {
            "trend": "UP",
            "trend_htf": "UP",
            "rsi": ["ENTER_LONG"],
            "rsi_waterline50": ["CROSS_UP"],
            "sr_levels": ["BREAKOUT_LONG"],
            "ema_cross": ["CROSS_UP"],
            "vol_filter": ["VOLF_PASSED"]
        }
        self.assertTrue(engine.check_signal("LONG", ind_valid_long))

        # Volume filter mismatch -> False
        ind_vol_mismatch = {
            "trend": "UP",
            "trend_htf": "UP",
            "rsi": ["ENTER_LONG"],
            "rsi_waterline50": ["CROSS_UP"],
            "sr_levels": ["BREAKOUT_LONG"],
            "ema_cross": ["CROSS_UP"],
            "vol_filter": []
        }
        self.assertFalse(engine.check_signal("LONG", ind_vol_mismatch))

        # EMA cross mismatch -> False
        ind_ec_mismatch = {
            "trend": "UP",
            "trend_htf": "UP",
            "rsi": ["ENTER_LONG"],
            "rsi_waterline50": ["CROSS_UP"],
            "sr_levels": ["BREAKOUT_LONG"],
            "ema_cross": [],
            "vol_filter": ["VOLF_PASSED"]
        }
        self.assertFalse(engine.check_signal("LONG", ind_ec_mismatch))

        # SR levels mismatch -> False
        ind_sr_mismatch = {
            "trend": "UP",
            "trend_htf": "UP",
            "rsi": ["ENTER_LONG"],
            "rsi_waterline50": ["CROSS_UP"],
            "sr_levels": [],
            "ema_cross": ["CROSS_UP"],
            "vol_filter": ["VOLF_PASSED"]
        }
        self.assertFalse(engine.check_signal("LONG", ind_sr_mismatch))

        # Waterline mismatch -> False
        ind_wl_mismatch = {
            "trend": "UP",
            "trend_htf": "UP",
            "rsi": ["ENTER_LONG"],
            "rsi_waterline50": [],
            "sr_levels": ["BREAKOUT_LONG"],
            "ema_cross": ["CROSS_UP"],
            "vol_filter": ["VOLF_PASSED"]
        }
        self.assertFalse(engine.check_signal("LONG", ind_wl_mismatch))

        # HTF mismatch -> False
        ind_htf_mismatch = {
            "trend": "UP",
            "trend_htf": "FLAT",
            "rsi": ["ENTER_LONG"],
            "sr_levels": ["BREAKOUT_LONG"],
            "ema_cross": ["CROSS_UP"],
            "vol_filter": ["VOLF_PASSED"]
        }
        self.assertFalse(engine.check_signal("LONG", ind_htf_mismatch))

        # RSI mismatch -> False
        ind_rsi_mismatch = {
            "trend": "UP",
            "trend_htf": "UP",
            "rsi": [],
            "sr_levels": ["BREAKOUT_LONG"],
            "ema_cross": ["CROSS_UP"],
            "vol_filter": ["VOLF_PASSED"]
        }
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

    def test_exit_rsi_rule(self):
        from CORE.rules import ExitRSIRule
        cfg = {"is_active": True, "long_exit_rsi": 70.0, "long_loss_rsi": 48.0, "short_exit_rsi": 30.0, "short_loss_rsi": 52.0}
        rule = ExitRSIRule(cfg)

        # Overbought exit
        self.assertTrue(rule.check("LONG", indicators={"rsi_value": 72.0}))
        # Momentum loss exit
        self.assertTrue(rule.check("LONG", indicators={"rsi_value": 45.0}))
        # Normal range
        self.assertFalse(rule.check("LONG", indicators={"rsi_value": 55.0}))

        # Oversold exit short
        self.assertTrue(rule.check("SHORT", indicators={"rsi_value": 28.0}))
        # Loss of short momentum
        self.assertTrue(rule.check("SHORT", indicators={"rsi_value": 55.0}))
        # Normal short range
        self.assertFalse(rule.check("SHORT", indicators={"rsi_value": 45.0}))

    def test_exit_time_stop_rule(self):
        import time
        from CORE.rules import ExitTimeStopRule
        cfg = {"is_active": True, "max_seconds": 10.0}
        rule = ExitTimeStopRule(cfg)

        now_ms = int(time.time() * 1000)
        # Position opened 15 seconds ago -> should exit
        self.assertTrue(rule.check("LONG", open_time_ms=now_ms - 15000))
        # Position opened 2 seconds ago -> hold
        self.assertFalse(rule.check("LONG", open_time_ms=now_ms - 2000))

    def test_taker_flow_rule(self):
        from CORE.indicators.squeeze_flow import EntryTakerFlowRule
        cfg = {"is_active": True, "min_buy_ratio": 0.58, "max_buy_ratio": 0.42}
        rule = EntryTakerFlowRule(cfg)

        self.assertTrue(rule.check("LONG", indicators={"taker_flow": ["TAKER_BUY_DOMINANT"]}))
        self.assertFalse(rule.check("LONG", indicators={"taker_flow": ["TAKER_SELL_DOMINANT"]}))
        self.assertFalse(rule.check("LONG", indicators={"taker_flow": []}))

        self.assertTrue(rule.check("SHORT", indicators={"taker_flow": ["TAKER_SELL_DOMINANT"]}))
        self.assertFalse(rule.check("SHORT", indicators={"taker_flow": ["TAKER_BUY_DOMINANT"]}))

    def test_volatility_squeeze_rule(self):
        from CORE.indicators.squeeze_flow import EntryVolatilitySqueezeRule
        cfg = {"is_active": True}
        rule = EntryVolatilitySqueezeRule(cfg)

        self.assertTrue(rule.check("LONG", indicators={"volatility_squeeze": ["SQUEEZE_LONG"]}))
        self.assertFalse(rule.check("LONG", indicators={"volatility_squeeze": ["SQUEEZE_SHORT"]}))
        self.assertFalse(rule.check("LONG", indicators={"volatility_squeeze": ["SQUEEZE_ON"]}))

        self.assertTrue(rule.check("SHORT", indicators={"volatility_squeeze": ["SQUEEZE_SHORT"]}))
        self.assertFalse(rule.check("SHORT", indicators={"volatility_squeeze": ["SQUEEZE_LONG"]}))

    def test_chandelier_exit_rule(self):
        from CORE.indicators.squeeze_flow import ExitChandelierRule
        cfg = {"is_active": True, "length": 5, "atr_mult": 2.0}
        rule = ExitChandelierRule(cfg)

        # Mock candles: highs around 100-110, lows around 95-100, closes 98-105
        candles = [
            {"high": 100.0, "low": 95.0, "close": 98.0},
            {"high": 102.0, "low": 96.0, "close": 100.0},
            {"high": 105.0, "low": 98.0, "close": 103.0},
            {"high": 108.0, "low": 100.0, "close": 105.0},
            {"high": 110.0, "low": 102.0, "close": 108.0},
            {"high": 110.0, "low": 101.0, "close": 107.0},
            {"high": 109.0, "low": 99.0, "close": 101.0},
        ]
        # Highest high = 110, ATR = 8.75 -> chandelier stop = 110 - (2 * 8.75) = 92.5.
        # If current price drops to 90.0 -> triggers chandelier exit
        self.assertTrue(rule.check("LONG", current_price=90.0, candles=candles))
        # If price is at 105 -> hold
        self.assertFalse(rule.check("LONG", current_price=105.0, candles=candles))

    def test_realtime_flow_tracker(self):
        from CORE.indicators.squeeze_flow import RealtimeFlowTracker
        tracker = RealtimeFlowTracker(max_retention_sec=60.0)
        # Add aggressive taker buys (is_buyer_maker=False)
        tracker.add_trade("TESTUSDT", price=100.0, qty=10.0, is_buyer_maker=False)
        tracker.add_trade("TESTUSDT", price=100.0, qty=10.0, is_buyer_maker=False)
        tracker.add_trade("TESTUSDT", price=100.0, qty=5.0, is_buyer_maker=True)
        # Total = 2500 USDT, Buy = 2000 USDT -> ratio = 0.8
        flow = tracker.get_flow("TESTUSDT", window_sec=60.0)
        self.assertAlmostEqual(flow["taker_buy_ratio"], 0.8)
        self.assertIn("TAKER_BUY_DOMINANT", flow["signals"])

    def test_relative_strength_rule(self):
        from CORE.indicators.squeeze_flow import EntryRelativeStrengthRule
        cfg = {"is_active": True}
        rule = EntryRelativeStrengthRule(cfg)
        self.assertTrue(rule.check("LONG", indicators={"relative_strength": ["RS_STRONG"]}))
        self.assertFalse(rule.check("LONG", indicators={"relative_strength": ["RS_WEAK"]}))
        self.assertTrue(rule.check("SHORT", indicators={"relative_strength": ["RS_WEAK"]}))

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

    def test_anti_reverse_suffixed_rules(self):
        enter_rules = {
            "trend_htf_anti": {"is_active": True, "long_cond": "DOWN", "short_cond": "UP"},
            "sr_levels_anti": {"is_active": True, "long_cond": "BREAKOUT_SHORT", "short_cond": "BREAKOUT_LONG"},
            "taker_flow_anti": {"is_active": True, "long_cond": "TAKER_SELL_DOMINANT", "short_cond": "TAKER_BUY_DOMINANT"}
        }
        engine = EntrySignalEngine(enter_rules)
        # In a falling market (bearish breakdown), anti-strategy enters LONG
        bearish_ind = {
            "trend_htf": "DOWN",
            "sr_levels": ["BREAKOUT_SHORT"],
            "taker_flow": ["TAKER_SELL_DOMINANT"]
        }
        self.assertTrue(engine.check_signal("LONG", bearish_ind))
        self.assertFalse(engine.check_signal("SHORT", bearish_ind))

        # In a rising market (bullish breakout), anti-strategy enters SHORT
        bullish_ind = {
            "trend_htf": "UP",
            "sr_levels": ["BREAKOUT_LONG"],
            "taker_flow": ["TAKER_BUY_DOMINANT"]
        }
        self.assertFalse(engine.check_signal("LONG", bullish_ind))
        self.assertTrue(engine.check_signal("SHORT", bullish_ind))

        # Exit engine with trend_reversal_anti
        exit_rules = {
            "trend_reversal_anti": {"is_active": True, "long_exit_trends": ["FLAT", "UP"], "short_exit_trends": ["FLAT", "DOWN"]},
            "take_profit_ratio": {"value": 0.02},
            "stop_loss_ratio": {"value": 0.04}
        }
        exit_engine = ExitSignalEngine(exit_rules, self.analytics_cfg, self.slip_fn)
        # Exits LONG when trend becomes UP
        self.assertTrue(exit_engine.check_signal("LONG", symbol="BTCUSDT", trend="UP", open_price=100.0, current_price=100.5))
        # Holds LONG when trend is still DOWN and PnL is safe
        self.assertFalse(exit_engine.check_signal("LONG", symbol="BTCUSDT", trend="DOWN", open_price=100.0, current_price=100.5))


if __name__ == "__main__":
    unittest.main()
