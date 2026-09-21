# ============================================================
# FILE: tests/test_institutional.py
# ROLE: Unit tests for institutional enhancements:
#       Breakeven Ratchet, Dynamic Time-Stop, Grid Fill Velocity,
#       and Level-Based Dynamic Hedge Ratios.
# ============================================================

import unittest
import time
from typing import Dict, Any

from CORE.rules import ExitBreakevenRatchetRule, ExitTimeStopRule, ExitSignalEngine, ExitProfitStagnationRule
from cron_integration import CronIntegration, EntryGridStressRule
from CORE.universe import UniverseManager


class TestInstitutionalRules(unittest.TestCase):
    """Тестирование институциональных правил выхода и фильтрации импульса."""

    def setUp(self):
        self.analytics_cfg = {"taker_fee_ratio": 0.0006}
        self.slip_fn = lambda sym: 0.0005

    def test_breakeven_ratchet_long(self):
        """
        LONG позиция:
        - Вход по цене 100.0.
        - Максимальная цена достигала 103.0 (+3.0% > +2.5% порог триггера).
        - Стоп безусловно подтягивается в 100.0 * (1 + 0.0012) = 100.12.
        - При откате цены до 100.10 -> выход по безубытку.
        - При цене 101.0 -> удержание позиции.
        """
        cfg = {"is_active": True, "trigger_ratio": 0.025, "buffer_ratio": 0.0012}
        rule = ExitBreakevenRatchetRule(cfg, self.analytics_cfg)

        # 1. Цена не достигала триггера (+2.0% < +2.5%) -> нет выхода
        self.assertFalse(rule.check(
            "LONG", open_price=100.0, current_price=100.10, highest_price=102.0
        ))

        # 2. Цена достигала +3.0%, но сейчас выше безубытка (101.5 > 100.12) -> нет выхода
        self.assertFalse(rule.check(
            "LONG", open_price=100.0, current_price=101.5, highest_price=103.0
        ))

        # 3. Цена достигала +3.0%, и откатила к 100.10 (<= 100.12) -> срабатывание выхода
        self.assertTrue(rule.check(
            "LONG", open_price=100.0, current_price=100.10, highest_price=103.0
        ))

    def test_breakeven_ratchet_short(self):
        """
        SHORT позиция:
        - Вход по цене 100.0.
        - Минимальная цена опускалась до 97.0 (+3.0% прибыль > +2.5% триггер).
        - Стоп подтягивается в 100.0 * (1 - 0.0012) = 99.88.
        - При откате цены до 99.90 (>= 99.88) -> выход.
        - При цене 98.5 -> удержание.
        """
        cfg = {"is_active": True, "trigger_ratio": 0.025, "buffer_ratio": 0.0012}
        rule = ExitBreakevenRatchetRule(cfg, self.analytics_cfg)

        # 1. Не достигала триггера (-2.0% прибыль) -> нет выхода
        self.assertFalse(rule.check(
            "SHORT", open_price=100.0, current_price=99.90, lowest_price=98.0
        ))

        # 2. Достигала +3.0% прибыли, держится в плюсе (98.0 <= 99.88) -> нет выхода
        self.assertFalse(rule.check(
            "SHORT", open_price=100.0, current_price=98.0, lowest_price=97.0
        ))

        # 3. Достигала +3.0% прибыли, откатила до 99.90 (>= 99.88) -> выход
        self.assertTrue(rule.check(
            "SHORT", open_price=100.0, current_price=99.90, lowest_price=97.0
        ))

    def test_dynamic_time_stop(self):
        """
        Динамический Time Stop:
        - max_seconds = 600.
        - min_pnl_ratio = 0.005 (+0.5%).
        - Если прошло > 600 сек, и прибыль < +0.5% -> импульс затух, выходим.
        - Если прошло > 600 сек, но прибыль >= +0.5% -> импульс развивается, держим.
        """
        cfg = {"is_active": True, "max_seconds": 600.0, "min_pnl_ratio": 0.005}
        rule = ExitTimeStopRule(cfg)

        now_ms = int(time.time() * 1000)
        open_time_old_ms = now_ms - (700 * 1000)  # 700 сек назад (> 600)
        open_time_fresh_ms = now_ms - (300 * 1000)  # 300 сек назад (< 600)

        # Свежая позиция -> не выходит независимо от PnL
        self.assertFalse(rule.check(
            "LONG", open_time_ms=open_time_fresh_ms, open_price=100.0, current_price=100.2
        ))

        # Старая позиция, но PnL вырос до +1.0% (>= +0.5%) -> держим!
        self.assertFalse(rule.check(
            "LONG", open_time_ms=open_time_old_ms, open_price=100.0, current_price=101.0
        ))

        # Старая позиция, PnL вялый (+0.2% < +0.5%) -> выходим!
        self.assertTrue(rule.check(
            "LONG", open_time_ms=open_time_old_ms, open_price=100.0, current_price=100.2
        ))

    def test_grid_stress_shock_filter(self):
        """
        Проверка фильтрации импульса по скорости набора сетки (require_shock).
        """
        cfg = {
            "is_active": True,
            "min_volume_ratio": 0.40,
            "min_filled_level": 2,
            "require_shock": True,
            "max_fill_duration_sec": 1800.0,
            "long_cond": "SHORT_GRID_STRESSED",
            "short_cond": "LONG_GRID_STRESSED"
        }
        rule = EntryGridStressRule(cfg)

        # Сетка застряла, но набрана медленно (is_shock=False) -> блокировка входа
        ind_slow = {
            "grid_stress": {
                "status": "SHORT_GRID_STRESSED",
                "SHORT": {
                    "in_position": True,
                    "volume_ratio": 0.45,
                    "max_level": 2,
                    "is_shock": False,
                    "fill_duration_sec": 7200.0,  # 2 часа
                    "stressed": True
                }
            }
        }
        self.assertFalse(rule.check("LONG", indicators=ind_slow))

        # Сетка застряла быстро (is_shock=True, fill_duration=600s) -> вход разрешен
        ind_shock = {
            "grid_stress": {
                "status": "SHORT_GRID_STRESSED",
                "SHORT": {
                    "in_position": True,
                    "volume_ratio": 0.45,
                    "max_level": 2,
                    "is_shock": True,
                    "fill_duration_sec": 600.0,
                    "stressed": True
                }
            }
        }
        self.assertTrue(rule.check("LONG", indicators=ind_shock))

    def test_calc_hedge_size_dynamic_map(self):
        """
        Проверка динамического пирамидирования от уровней сетки:
        - Lvl 0, 1 -> 1.0
        - Lvl 2, 3 -> 0.75
        - Lvl 4+   -> 0.50
        """
        hedge_cfg = {
            "0": 1.0,
            "1": 1.0,
            "2": 0.75,
            "3": 0.75,
            "default": 0.5
        }

        # Level 1 -> ratio 1.0
        ratio_lvl1 = CronIntegration.resolve_hedge_ratio(hedge_cfg, max_level=1, active_count=2)
        self.assertAlmostEqual(ratio_lvl1, 1.0)

        # Level 2 -> ratio 0.75
        ratio_lvl2 = CronIntegration.resolve_hedge_ratio(hedge_cfg, max_level=2, active_count=3)
        self.assertAlmostEqual(ratio_lvl2, 0.75)

        # Level 4 -> ratio 0.50
        ratio_lvl4 = CronIntegration.resolve_hedge_ratio(hedge_cfg, max_level=4, active_count=5)
        self.assertAlmostEqual(ratio_lvl4, 0.5)

    def test_all_universes_load(self):
        """Проверка корректной загрузки всех вселенных из cfg.json."""
        import json
        with open("cfg.json", "r", encoding="utf-8") as f:
            cfg = json.load(f)
        manager = UniverseManager(
            universes_cfg=cfg.get("universes", {}),
            default_enter_rules={},
            default_exit_rules={},
            get_slippage_ratio_fn=self.slip_fn
        )
        self.assertIn("u_sq_hvh_ratchet", manager.universes)
        self.assertIn("u_grid_stress_shock", manager.universes)
        self.assertIn("u_delta_harvester", manager.universes)
        self.assertIn("u_delta_sniper", manager.universes)
        self.assertIn("u_shadow_harvester_40", manager.universes)
        self.assertIn("u_shadow_harvester_50", manager.universes)
        self.assertIn("u_shadow_harvester_mid", manager.universes)
        self.assertIn("u_shadow_harvester_wide", manager.universes)
        self.assertIn("u_grid_shadow_be", manager.universes)
        self.assertIn("u_grid_shadow_stagnation", manager.universes)
        self.assertIn("u_symbiosis_harvester", manager.universes)
        self.assertIn("u_delta_sniper_15m", manager.universes)
        self.assertIn("u_hvh_delta_symbiosis", manager.universes)
        self.assertIn("u_sh50_alpha", manager.universes)
        self.assertIn("u_sh50_notop", manager.universes)
        self.assertIn("u_sh40_alpha", manager.universes)
        self.assertIn("u_sh40_notop", manager.universes)
        self.assertIn("u_hvh_symbiosis_alpha", manager.universes)
        self.assertIn("u_hvh_symbiosis_notop", manager.universes)
        self.assertIn("u_symb_harv_alpha", manager.universes)
        self.assertIn("u_symb_harv_notop", manager.universes)
        self.assertIn("u15_4h_rsi1d_std", manager.universes)
        self.assertIn("u15_4h_rsi1d_alpha", manager.universes)
        self.assertIn("u_jem_matrix_harvest", manager.universes)
        self.assertIn("u_jem_symbiotic_quantum", manager.universes)
        self.assertEqual(len(cfg.get("universes", {})), 52)
        self.assertEqual(len(manager.universes), 38)

    def test_grid_net_filter_rule(self):
        """Проверка фильтрации монет по статистике сеточника (Grid Net PnL)."""
        from CORE.symbiosis_rules import EntryGridNetFilterRule
        rule_alpha = EntryGridNetFilterRule({"is_active": True, "mode": "ALPHA_ONLY", "max_grid_net": 0.0})
        rule_notop = EntryGridNetFilterRule({"is_active": True, "mode": "EXCLUDE_TOP_CASH_COWS", "exclude_top_n": 5})

        # PIEVERSEUSDT имеет высокий положительный Grid Net (+36.5$) -> должен блокироваться
        self.assertFalse(rule_alpha.check("LONG", symbol="PIEVERSEUSDT"))
        self.assertFalse(rule_notop.check("LONG", symbol="PIEVERSEUSDT"))

        # GUSDT имеет отрицательный Grid Net (-8.9$) -> должен проходить
        self.assertTrue(rule_alpha.check("LONG", symbol="GUSDT"))
        self.assertTrue(rule_notop.check("LONG", symbol="GUSDT"))

    def test_htf_rsi_filter_rule(self):
        """Проверка дневного/4H фильтра RSI."""
        from CORE.symbiosis_rules import EntryHTFRSIRule
        rule = EntryHTFRSIRule({"is_active": True, "timeframe": "1d", "max_rsi_long": 70.0, "min_rsi_short": 30.0})

        # LONG: при RSI 75 >= 70 блокируется, при 55 < 70 проходит
        self.assertFalse(rule.check("LONG", indicators={"rsi_1d_value": 75.0}, symbol="BTCUSDT"))
        self.assertTrue(rule.check("LONG", indicators={"rsi_1d_value": 55.0}, symbol="BTCUSDT"))

        # SHORT: при RSI 25 <= 30 блокируется, при 45 > 30 проходит
        self.assertFalse(rule.check("SHORT", indicators={"rsi_1d_value": 25.0}, symbol="BTCUSDT"))
        self.assertTrue(rule.check("SHORT", indicators={"rsi_1d_value": 45.0}, symbol="BTCUSDT"))

    def test_profit_stagnation_be_lock(self):
        """Проверка БУ-замка в ExitProfitStagnationRule."""
        cfg = {"is_active": True, "be_trigger_ratio": 0.028, "be_buffer_ratio": 0.003, "min_profit_ratio": 0.05}
        rule = ExitProfitStagnationRule(cfg, self.analytics_cfg)
        self.assertFalse(rule.check("LONG", symbol="BTCUSDT", open_price=100.0, current_price=100.3, highest_price=102.0))
        self.assertTrue(rule.check("LONG", symbol="BTCUSDT", open_price=100.0, current_price=100.25, highest_price=103.0))

    def test_profit_stagnation_exit_timer(self):
        """Проверка выхода по стагнации прибыли при отсутствии нового пика."""
        cfg = {
            "is_active": True, "be_trigger_ratio": 0.028, "be_buffer_ratio": 0.003,
            "min_profit_ratio": 0.05, "stagnation_seconds": 1800.0, "progress_threshold": 0.005
        }
        rule = ExitProfitStagnationRule(cfg, self.analytics_cfg)
        t0 = 10000.0
        self.assertFalse(rule.check("LONG", symbol="SOLUSDT", open_price=100.0, current_price=106.0, highest_price=106.0, current_time=t0))
        self.assertFalse(rule.check("LONG", symbol="SOLUSDT", open_price=100.0, current_price=106.0, highest_price=106.0, current_time=t0 + 1000))
        self.assertTrue(rule.check("LONG", symbol="SOLUSDT", open_price=100.0, current_price=106.0, highest_price=106.0, current_time=t0 + 1900))


if __name__ == "__main__":
    unittest.main()
