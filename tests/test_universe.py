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

    def test_anti_trend_rsi_strategy(self):
        u1_cfg = {
            "name": "Normal Trend RSI",
            "is_active": True,
            "enter_rules": {
                "trend": {"is_active": True, "long_cond": "UP", "short_cond": "DOWN"},
                "trend_htf": {"is_active": True, "long_cond": "UP", "short_cond": "DOWN"},
                "rsi": {
                    "is_active": True,
                    "conditions": {"ENTER_LONG": "50 < x <= 60", "ENTER_SHORT": "40 <= x < 50"}
                }
            },
            "exit_rules": {}
        }
        u1_anti_cfg = {
            "name": "Anti Trend RSI",
            "is_active": True,
            "enter_rules": {
                "trend": {"is_active": True, "long_cond": "DOWN", "short_cond": "UP"},
                "trend_htf": {"is_active": True, "long_cond": "DOWN", "short_cond": "UP"},
                "rsi": {
                    "is_active": True,
                    "conditions": {"ENTER_LONG": "40 <= x < 50", "ENTER_SHORT": "50 < x <= 60"}
                }
            },
            "exit_rules": {}
        }
        mgr = UniverseManager(
            universes_cfg={"u1": u1_cfg, "u1_anti": u1_anti_cfg},
            default_enter_rules={},
            default_exit_rules={},
            get_slippage_ratio_fn=lambda s: 0.001
        )
        u1 = mgr.get_universe("u1")
        u1_anti = mgr.get_universe("u1_anti")

        # Market case 1: UP trend, HTF UP, RSI 55 (Classic LONG)
        ind_up = {"trend": "UP", "trend_htf": "UP", "rsi_value": 55.0}
        self.assertTrue(u1.check_entry("LONG", ind_up))
        self.assertFalse(u1.check_entry("SHORT", ind_up))
        # In u1_anti: Should enter SHORT!
        self.assertFalse(u1_anti.check_entry("LONG", ind_up))
        self.assertTrue(u1_anti.check_entry("SHORT", ind_up))

        # Market case 2: DOWN trend, HTF DOWN, RSI 45 (Classic SHORT)
        ind_down = {"trend": "DOWN", "trend_htf": "DOWN", "rsi_value": 45.0}
        self.assertFalse(u1.check_entry("LONG", ind_down))
        self.assertTrue(u1.check_entry("SHORT", ind_down))
        # In u1_anti: Should enter LONG!
        self.assertTrue(u1_anti.check_entry("LONG", ind_down))
        self.assertFalse(u1_anti.check_entry("SHORT", ind_down))

    def test_live_balance_with_unrealized_pnl(self):
        from TG.handlers_analytics import _format_analytics_text
        class MockBotCore:
            def __init__(self, mgr):
                self.universe_manager = mgr
                self.current_prices = {"BTCUSDT": 55000.0}

        u1 = self.mgr.get_universe("u1")
        u1.state.open_position("BTCUSDT", "LONG", price=50000.0, size=100.0)
        bot_core = MockBotCore(self.mgr)

        # Start balance = 1000, unrealized pnl = (55000 - 50000) / 50000 * 100 = +10 USDT
        data = {
            "start_balance_usdt": 1000.0,
            "cur_balance_usdt": 1000.0,
            "realized_pnl_usdt": 0.0,
            "net_profit_usdt": 0.0,
            "total_trades": 0
        }
        text = _format_analytics_text(data, bot_core=bot_core, universe_id="u1")
        self.assertIn("• Стартовый баланс: <code>1000.00 USDT</code>", text)
        self.assertIn("• Текущий баланс: <code>1010.00 USDT</code>", text)
        self.assertIn("• Чистый профит: <b>+10.0000 USDT</b>", text)
        self.assertIn("• Нереализованный PnL: <code>+10.0000 USDT</code>", text)

    def test_u15_anti_breakout_taker_flow_mirroring(self):
        from consts import load_config
        cfg_data = load_config()
        u_cfg = cfg_data.get("universes", {})
        self.assertIn("u15", u_cfg)
        self.assertIn("u15_anti", u_cfg)

        mgr = UniverseManager(
            universes_cfg={"u15": u_cfg["u15"], "u15_anti": u_cfg["u15_anti"]},
            default_enter_rules={},
            default_exit_rules={},
            get_slippage_ratio_fn=lambda s: 0.001
        )
        u15 = mgr.get_universe("u15")
        u15_anti = mgr.get_universe("u15_anti")

        # Market case: HTF UP, LuxAlgo Breakout LONG, Taker Buy Dominant (u15 enters LONG)
        ind_long = {
            "trend_htf": "UP",
            "sr_levels": ["BREAKOUT_LONG"],
            "taker_flow": ["TAKER_BUY_DOMINANT"]
        }
        self.assertTrue(u15.check_entry("LONG", ind_long))
        self.assertFalse(u15.check_entry("SHORT", ind_long))
        # In u15_anti: Must NOT enter LONG, must enter SHORT!
        self.assertFalse(u15_anti.check_entry("LONG", ind_long))
        self.assertTrue(u15_anti.check_entry("SHORT", ind_long))

        # Market case: HTF DOWN, LuxAlgo Breakout SHORT, Taker Sell Dominant (u15 enters SHORT)
        ind_short = {
            "trend_htf": "DOWN",
            "sr_levels": ["BREAKOUT_SHORT"],
            "taker_flow": ["TAKER_SELL_DOMINANT"]
        }
        self.assertFalse(u15.check_entry("LONG", ind_short))
        self.assertTrue(u15.check_entry("SHORT", ind_short))
        # In u15_anti: Must enter LONG, must NOT enter SHORT!
        self.assertTrue(u15_anti.check_entry("LONG", ind_short))
        self.assertFalse(u15_anti.check_entry("SHORT", ind_short))

    def test_all_anti_universes_mirroring(self):
        from consts import load_config
        cfg_data = load_config()
        u_cfg = cfg_data.get("universes", {})
        mgr = UniverseManager(
            universes_cfg=u_cfg,
            default_enter_rules={},
            default_exit_rules={},
            get_slippage_ratio_fn=lambda s: 0.001
        )
        self.assertEqual(len(mgr.universes), 12)
        expected_uids = [
            "u15", "u15_cons", "u15_aggr", "u15_scalp",
            "u15_anti", "u15_anti_fade", "u15_anti_tight", "u15_anti_scalp",
            "u3_anti", "u3_anti_climax", "u3_anti_aggr", "u3_anti_trend"
        ]
        for uid in expected_uids:
            self.assertIsNotNone(mgr.get_universe(uid), f"Universe {uid} not found")

        # u15 vs u15_anti: TP=0.045, SL=0.02 -> u15_anti TP=0.02, SL=0.045
        u15 = mgr.get_universe("u15")
        u15_anti = mgr.get_universe("u15_anti")
        self.assertEqual(u15.exit_rules["take_profit_ratio"]["value"], 0.045)
        self.assertEqual(u15.exit_rules["stop_loss_ratio"]["value"], 0.02)
        self.assertEqual(u15_anti.exit_rules["take_profit_ratio"]["value"], 0.02)
        self.assertEqual(u15_anti.exit_rules["stop_loss_ratio"]["value"], 0.045)

        # u3_anti: TP=0.02, SL=0.04
        u3_anti = mgr.get_universe("u3_anti")
        self.assertEqual(u3_anti.exit_rules["take_profit_ratio"]["value"], 0.02)
        self.assertEqual(u3_anti.exit_rules["stop_loss_ratio"]["value"], 0.04)


if __name__ == "__main__":
    unittest.main()
