# ============================================================
# FILE: tests/test_portfolio_selector.py
# ROLE: Unit tests for Multi-Mode Portfolio Selector Service
# PROJECT: TrendH_Papper & Hron3 Symbiosis
# ============================================================

import os
import json
import tempfile
import unittest
from CORE.portfolio_selector import (
    PortfolioSelector,
    CoinMetrics,
    PortfolioResult,
)


class TestPortfolioSelector(unittest.TestCase):
    """Unit tests for the PortfolioSelector service."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cron_analytics_path = os.path.join(self.temp_dir.name, "cron_analytics.json")
        self.trendh_analytics_dir = os.path.join(self.temp_dir.name, "trendh_analytics")
        os.makedirs(self.trendh_analytics_dir, exist_ok=True)

        # Mock Cron Analytics
        cron_data = {
            "per_coin": {
                "CROSSUSDT": {
                    "net_profit_usdt": 26.58,
                    "realized_pnl_net_usdt": 28.78,
                    "risk_reward_ratio": 0.81,
                    "DRME": 0.042,
                    "MDME": 0.034,
                    "trades": 60,
                },
                "MIRAUSDT": {
                    "net_profit_usdt": 10.88,
                    "realized_pnl_net_usdt": 14.43,
                    "risk_reward_ratio": 0.38,
                    "DRME": 0.021,
                    "MDME": 0.015,
                    "trades": 35,
                },
                "GUSDT": {
                    "net_profit_usdt": -12.87,
                    "realized_pnl_net_usdt": 114.50,
                    "risk_reward_ratio": 2.50,
                    "DRME": 0.154,
                    "MDME": 0.085,
                    "trades": 120,
                },
                "ZAMAUSDT": {
                    "net_profit_usdt": -50.58,
                    "realized_pnl_net_usdt": 32.95,
                    "risk_reward_ratio": 2.80,
                    "DRME": 0.046,
                    "MDME": 0.090,
                    "trades": 90,
                },
                "PIEVERSEUSDT": {
                    "net_profit_usdt": 28.82,
                    "realized_pnl_net_usdt": 35.34,
                    "risk_reward_ratio": 1.80,
                    "DRME": 0.052,
                    "MDME": 0.070,
                    "trades": 80,
                },
                "LOWLIQUSDT": {
                    "net_profit_usdt": 1.20,
                    "realized_pnl_net_usdt": 2.00,
                    "risk_reward_ratio": 0.50,
                    "DRME": 0.010,
                    "MDME": 0.010,
                    "trades": 3,
                },
            }
        }
        with open(self.cron_analytics_path, "w", encoding="utf-8") as f:
            json.dump(cron_data, f)

        # Mock TrendH Strategy 1: Shadow Harvester 50
        th_data_1 = {
            "per_coin": {
                "GUSDT": {
                    "net_profit_usdt": 25.00,
                    "realized_pnl_net_usdt": 25.00,
                    "winrate_pct": 65.0,
                    "win_count": 65,
                    "trades": 100,
                },
                "ZAMAUSDT": {
                    "net_profit_usdt": 5.00,
                    "realized_pnl_net_usdt": 5.00,
                    "winrate_pct": 70.0,
                    "win_count": 14,
                    "trades": 20,
                },
                "PIEVERSEUSDT": {
                    "net_profit_usdt": -18.43,
                    "realized_pnl_net_usdt": -18.43,
                    "winrate_pct": 33.33,
                    "win_count": 2,
                    "trades": 6,
                },
            }
        }
        th_path_1 = os.path.join(
            self.trendh_analytics_dir, "analytics_u_shadow_harvester_50.json"
        )
        with open(th_path_1, "w", encoding="utf-8") as f:
            json.dump(th_data_1, f)

        # Mock TrendH Strategy 2: Delta Harvester (Multi-strategy aggregation)
        th_data_2 = {
            "per_coin": {
                "GUSDT": {
                    "net_profit_usdt": 14.70,
                    "realized_pnl_net_usdt": 14.70,
                    "winrate_pct": 60.0,
                    "win_count": 6,
                    "trades": 10,
                },
                "ZAMAUSDT": {
                    "net_profit_usdt": 4.58,
                    "realized_pnl_net_usdt": 4.58,
                    "winrate_pct": 80.0,
                    "win_count": 4,
                    "trades": 5,
                },
            }
        }
        th_path_2 = os.path.join(
            self.trendh_analytics_dir, "analytics_u_delta_harvester.json"
        )
        with open(th_path_2, "w", encoding="utf-8") as f:
            json.dump(th_data_2, f)

        self.selector = PortfolioSelector(
            cron_analytics_path=self.cron_analytics_path,
            trendh_analytics_dir=self.trendh_analytics_dir,
            trendh_target_strategies=["u_shadow_harvester_50", "u_delta_harvester"],
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_multi_strategy_aggregation(self):
        """Test that TrendH metrics properly aggregate across multiple target strategies."""
        data_map = self.selector.load_data()
        self.assertIn("GUSDT", data_map)
        gusdt = data_map["GUSDT"]

        # 25.0 + 14.70 = 39.70 TrendH net
        self.assertAlmostEqual(gusdt.trendh_net, 39.70, places=2)
        # Trades: 100 + 10 = 110, Wins: 65 + 6 = 71 -> WR: 64.55%
        self.assertEqual(gusdt.trendh_trades, 110)
        self.assertAlmostEqual(gusdt.trendh_winrate, 64.55, places=1)
        # Combined net: -12.87 (grid) + 39.70 (trendh) = 26.83
        self.assertAlmostEqual(gusdt.combined_net, 26.83, places=2)

    def test_for_grid_only_mode_selection(self):
        """FOR_GRID_ONLY must select pure cash cows based solely on grid metrics."""
        result = self.selector.select_portfolio(n_coins=2, mode="FOR_GRID_ONLY")
        self.assertEqual(result.mode, "FOR_GRID_ONLY")
        self.assertEqual(len(result.coins), 2)

        symbols = [c.symbol for c in result.coins]
        self.assertIn("CROSSUSDT", symbols)
        self.assertIn("MIRAUSDT", symbols)
        # GUSDT has negative grid net (-12.87$) -> Disqualified in pure grid mode
        self.assertNotIn("GUSDT", symbols)

    def test_for_gride_firstable_mode_selection(self):
        """FOR_GRIDE_FIRSTABLE must select Cash Cows (CROSS, MIRA) and exclude PIEVERSE (chop trap)."""
        result = self.selector.select_portfolio(n_coins=2, mode="FOR_GRIDE_FIRSTABLE")
        self.assertEqual(result.mode, "FOR_GRIDE_FIRSTABLE")
        self.assertEqual(len(result.coins), 2)

        symbols = [c.symbol for c in result.coins]
        self.assertIn("CROSSUSDT", symbols)
        self.assertIn("MIRAUSDT", symbols)
        self.assertNotIn("PIEVERSEUSDT", symbols)

    def test_for_trendh_firstable_excludes_zama(self):
        """FOR_TRENDH_FIRSTABLE must exclude ZAMA (negative combined net: -41$) and select GUSDT."""
        result = self.selector.select_portfolio(n_coins=2, mode="FOR_TRENDH_FIRSTABLE")
        self.assertEqual(result.mode, "FOR_TRENDH_FIRSTABLE")

        symbols = [c.symbol for c in result.coins]
        # GUSDT has positive combined net (+26.83$) -> Selected
        self.assertIn("GUSDT", symbols)
        # ZAMAUSDT has negative combined net (-50.58 + 9.58 = -41.00$) -> MUST BE EXCLUDED!
        self.assertNotIn("ZAMAUSDT", symbols)
        # PIEVERSEUSDT has negative TrendH net (-18.43$) -> MUST BE EXCLUDED!
        self.assertNotIn("PIEVERSEUSDT", symbols)

    def test_for_trendh_only_mode(self):
        """FOR_TRENDH_ONLY must prioritize TrendH net and winrate."""
        result = self.selector.select_portfolio(n_coins=2, mode="FOR_TRENDH_ONLY")
        symbols = [c.symbol for c in result.coins]
        self.assertIn("GUSDT", symbols)

    def test_format_report_output(self):
        """Test that format_report produces clean, readable ASCII output with Comb Net."""
        result = self.selector.select_portfolio(n_coins=2, mode="FOR_TRENDH_FIRSTABLE")
        report = self.selector.format_report(result)
        self.assertIn("PORTFOLIO SELECTION RESULT", report)
        self.assertIn("Comb Net", report)
        self.assertIn("GUSDT", report)


if __name__ == "__main__":
    unittest.main()
