# ============================================================
# FILE: tests/test_universe.py
# ROLE: Unit tests for Multi-Strategy Parallel Universes
# ============================================================

import unittest
from pathlib import Path
from CORE.universe import UniverseState, StrategyUniverse, UniverseManager


from consts import DATA_DIR, ANALYTICS_DIR


class TestUniverseState(unittest.TestCase):
    def setUp(self):
        self.state1 = UniverseState(universe_id="test_u1")
        self.state2 = UniverseState(universe_id="test_u2")

    def tearDown(self):
        for uid in ["test_u1", "test_u2", "test_u3", "u1", "u2"]:
            for folder in [DATA_DIR, ANALYTICS_DIR]:
                for f in folder.glob(f"*{uid}*"):
                    try:
                        f.unlink(missing_ok=True)
                    except Exception:
                        pass

    def test_state_isolation(self):
        self.state1.open_position("BTCUSDT", "LONG", 50000.0, 100.0)
        self.assertIsNotNone(self.state1.get_position("BTCUSDT", "LONG"))
        self.assertIsNone(self.state2.get_position("BTCUSDT", "LONG"))

        self.state2.open_position("ETHUSDT", "SHORT", 3000.0, 50.0)
        self.assertIsNotNone(self.state2.get_position("ETHUSDT", "SHORT"))
        self.assertIsNone(self.state1.get_position("ETHUSDT", "SHORT"))

        self.state1.close_position("BTCUSDT", "LONG")
        self.assertIsNone(self.state1.get_position("BTCUSDT", "LONG"))
        self.assertIsNotNone(self.state2.get_position("ETHUSDT", "SHORT"))

    def test_reset_and_active_flags(self):
        self.state1.open_position("SOLUSDT", "LONG", 150.0, 75.0)
        pos = self.state1.get_position("SOLUSDT", "LONG")
        self.assertTrue(pos.is_active)
        self.assertEqual(pos.open_price, 150.0)
        self.assertEqual(pos.size, 75.0)

        self.state1.close_position("SOLUSDT", "LONG")
        self.assertIsNone(self.state1.get_position("SOLUSDT", "LONG"))


class TestStrategyUniverse(unittest.TestCase):
    def setUp(self):
        self.enter_rules = {
            "trend": {
                "is_active": True,
                "timeframe": "5m",
                "sma_fast": 5,
                "sma_slow": 10,
                "confirmation_candles": 2,
                "require_rising": True,
                "trend_positive": True,
                "long_cond": "UP",
                "short_cond": "DOWN"
            }
        }
        self.exit_rules_tp5 = {
            "trend_reversal": {"is_active": False},
            "take_profit_ratio": {"value": 0.05},
            "stop_loss_ratio": {"value": None}
        }
        self.exit_rules_tp2 = {
            "trend_reversal": {"is_active": False},
            "take_profit_ratio": {"value": 0.02},
            "stop_loss_ratio": {"value": None}
        }
        self.exit_rules_sl = {
            "trend_reversal": {"is_active": False},
            "take_profit_ratio": {"value": 0.05},
            "stop_loss_ratio": {"value": 0.02}
        }
        self.slip_fn = lambda s: 0.0005

        self.u1 = StrategyUniverse(
            universe_id="test_u1",
            name="Universe TP 5%",
            description="High TP",
            enter_rules=self.enter_rules,
            exit_rules=self.exit_rules_tp5,
            get_slippage_ratio_fn=self.slip_fn
        )
        self.u2 = StrategyUniverse(
            universe_id="test_u2",
            name="Universe TP 2%",
            description="Tight TP",
            enter_rules=self.enter_rules,
            exit_rules=self.exit_rules_tp2,
            get_slippage_ratio_fn=self.slip_fn
        )
        self.u3 = StrategyUniverse(
            universe_id="test_u3",
            name="Universe SL 2%",
            description="Stop Loss 2%",
            enter_rules=self.enter_rules,
            exit_rules=self.exit_rules_sl,
            get_slippage_ratio_fn=self.slip_fn
        )

    def test_different_tp_behavior(self):
        # Open position in both universes at price 100
        self.u1.state.open_position("BTCUSDT", "LONG", 100.0, 100.0)
        self.u2.state.open_position("BTCUSDT", "LONG", 100.0, 100.0)

        # Price rises to 103 (+3.0%)
        ind = {"trend": "UP"}
        self.u1.process_tick("BTCUSDT", "LONG", 103.0, ind, self.slip_fn, is_paused=False, invest_size=100.0)
        self.u2.process_tick("BTCUSDT", "LONG", 103.0, ind, self.slip_fn, is_paused=False, invest_size=100.0)

        # U2 should have closed by TP 2% (gain > 2% net of fees)
        self.assertIsNone(self.u2.state.get_position("BTCUSDT", "LONG"))
        # U1 should still be open (needs 5%)
        self.assertIsNotNone(self.u1.state.get_position("BTCUSDT", "LONG"))

    def test_stop_loss_trigger(self):
        self.u3.state.open_position("BTCUSDT", "LONG", 100.0, 100.0)
        # Price drops to 97 (-3.0%)
        ind = {"trend": "UP"}
        self.u3.process_tick("BTCUSDT", "LONG", 97.0, ind, self.slip_fn, is_paused=False, invest_size=100.0)
        # U3 position should be closed by Stop Loss 2%
        self.assertIsNone(self.u3.state.get_position("BTCUSDT", "LONG"))

    def test_entry_signal_execution(self):
        ind = {"trend": "UP"}
        self.u1.process_tick("ETHUSDT", "LONG", 2000.0, ind, self.slip_fn, is_paused=False, invest_size=50.0)
        pos = self.u1.state.get_position("ETHUSDT", "LONG")
        self.assertIsNotNone(pos)
        self.assertEqual(pos.open_price, 2000.0)
        self.assertEqual(pos.size, 50.0)


class TestUniverseManager(unittest.TestCase):
    def setUp(self):
        self.universes_cfg = {
            "u1": {
                "name": "Strategy 1",
                "description": "Desc 1",
                "is_active": True,
                "enter_rules": {
                    "trend": {"is_active": True, "timeframe": "5m"},
                    "rsi": {"is_active": True, "timeframe": "5m"}
                },
                "exit_rules": {"take_profit_ratio": {"value": 0.05}}
            },
            "u2": {
                "name": "Strategy 2",
                "description": "Desc 2",
                "is_active": True,
                "enter_rules": {
                    "sr_levels": {"is_active": True, "timeframe": "5m"},
                    "vol_filter": {"is_active": True, "timeframe": "1m"}
                },
                "exit_rules": {"take_profit_ratio": {"value": 0.03}}
            }
        }
        self.mgr = UniverseManager(
            universes_cfg=self.universes_cfg,
            default_enter_rules={},
            default_exit_rules={},
            get_slippage_ratio_fn=lambda s: 0.001
        )

    def test_combined_enter_rules(self):
        combined = self.mgr.get_combined_enter_rules()
        self.assertIn("trend", combined)
        self.assertIn("rsi", combined)
        self.assertIn("sr_levels", combined)
        self.assertIn("vol_filter", combined)

    def test_get_leaderboard(self):
        board = self.mgr.get_leaderboard()
        self.assertEqual(len(board), 2)
        uids = [item["uid"] for item in board]
        self.assertIn("u1", uids)
        self.assertIn("u2", uids)

    def test_inverted_strategies_concurrency(self):
        u6_cfg = {
            "name": "Normal EMA",
            "is_active": True,
            "enter_rules": {
                "ema_cross": {"is_active": True, "long_cond": "CROSS_UP", "short_cond": "CROSS_DOWN"}
            },
            "exit_rules": {}
        }
        u6_anti_cfg = {
            "name": "Reverse EMA",
            "is_active": True,
            "enter_rules": {
                "ema_cross": {"is_active": True, "long_cond": "CROSS_DOWN", "short_cond": "CROSS_UP"}
            },
            "exit_rules": {}
        }
        mgr = UniverseManager(
            universes_cfg={"u6": u6_cfg, "u6_anti": u6_anti_cfg},
            default_enter_rules={},
            default_exit_rules={},
            get_slippage_ratio_fn=lambda s: 0.001
        )
        indicators = {"ema_cross": ["CROSS_UP"]}
        u6 = mgr.get_universe("u6")
        u6_anti = mgr.get_universe("u6_anti")

        # CROSS_UP signal -> u6 should enter LONG, u6_anti should enter SHORT
        self.assertTrue(u6.check_entry("LONG", indicators))
        self.assertFalse(u6.check_entry("SHORT", indicators))

        self.assertFalse(u6_anti.check_entry("LONG", indicators))
        self.assertTrue(u6_anti.check_entry("SHORT", indicators))

    def test_close_all_positions(self):
        u1 = self.mgr.get_universe("u1")
        u2 = self.mgr.get_universe("u2")
        u1.state.open_position("BTCUSDT", "LONG", 50000.0, 100.0)
        u2.state.open_position("ETHUSDT", "SHORT", 3000.0, 100.0)

        closed = self.mgr.close_all_positions({"BTCUSDT": 51000.0, "ETHUSDT": 2900.0}, lambda s: 0.001)
        self.assertEqual(closed, 2)
        self.assertIsNone(u1.state.get_position("BTCUSDT", "LONG"))
        self.assertIsNone(u2.state.get_position("ETHUSDT", "SHORT"))


if __name__ == "__main__":
    unittest.main()
