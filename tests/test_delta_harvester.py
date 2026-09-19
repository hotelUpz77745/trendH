# ============================================================
# FILE: tests/test_delta_harvester.py
# ROLE: Unit tests for Delta Harvester & Dynamic Trailing Ratchet
# ============================================================
import unittest
from typing import Dict, Any

from CORE.rules import ExitBreakevenRatchetRule, EntryDeltaHarvesterRule
from CORE.universe import StrategyUniverse, UniverseManager
from consts import load_config


class TestDeltaHarvesterAndTrailing(unittest.TestCase):
    """
    Набор тестов для проверки универсальной стратегии Delta Harvester:
    1. Динамический трейлинг прибыли ExitBreakevenRatchetRule (LONG и SHORT).
    2. Гарантия безубытка (стоп никогда не опускается ниже open_price + buffer).
    3. Специализированное правило входа EntryDeltaHarvesterRule.
    4. 1:1 динамическое дельта-хеджирование и сайзинг в StrategyUniverse.
    """

    def setUp(self):
        self.analytics_cfg = {"taker_fee_ratio": 0.0006}  # x2 = 0.0012

    def test_breakeven_ratchet_without_trail(self):
        """Проверка обратной совместимости: классический Breakeven Ratchet без trail_ratio."""
        cfg = {"is_active": True, "trigger_ratio": 0.025, "buffer_ratio": 0.005}
        rule = ExitBreakevenRatchetRule(cfg, self.analytics_cfg)

        # LONG: вход по 100
        # 1. Прибыль +1.5% (пик 101.5, тек 101.0) -> триггер еще не сработал
        self.assertFalse(rule.check("LONG", open_price=100.0, current_price=101.0, highest_price=101.5))

        # 2. Прибыль коснулась +3.0% (пик 103.0), текущая цена 102.0 -> выше BE (100.5)
        self.assertFalse(rule.check("LONG", open_price=100.0, current_price=102.0, highest_price=103.0))

        # 3. Откат к уровню безубытка 100.5 или ниже -> выход!
        self.assertTrue(rule.check("LONG", open_price=100.0, current_price=100.4, highest_price=103.0))

    def test_breakeven_ratchet_with_trail_long(self):
        """Проверка динамического трейлинга для LONG: подтягивание стопа за пиком цены."""
        cfg = {
            "is_active": True,
            "trigger_ratio": 0.025,  # активация при +2.5%
            "trail_ratio": 0.018,    # трейлинг 1.8% от пика
            "buffer_ratio": 0.005    # безубыток +0.5%
        }
        rule = ExitBreakevenRatchetRule(cfg, self.analytics_cfg)

        open_p = 100.0

        # 1. Цена на 101.0 (пик 101.5) -> прирост 1.5% < 2.5% -> нет выхода
        self.assertFalse(rule.check("LONG", open_price=open_p, current_price=101.0, highest_price=101.5))

        # 2. Цена дошла до 105.0 (+5.0% пик). Трейл-стоп: 105.0 * (1 - 0.018) = 103.11.
        # Текущая цена 103.5 -> выше трейла, не выходим
        self.assertFalse(rule.check("LONG", open_price=open_p, current_price=103.5, highest_price=105.0))

        # Текущая цена опустилась до 103.0 (<= 103.11) -> выход по динамическому трейлингу!
        self.assertTrue(rule.check("LONG", open_price=open_p, current_price=103.0, highest_price=105.0))

        # 3. Мега-памп: цена дошла до 120.0 (+20% пик).
        # Трейл-стоп: 120.0 * (1 - 0.018) = 117.84.
        # Текущая 118.0 -> сидим в позиции
        self.assertFalse(rule.check("LONG", open_price=open_p, current_price=118.0, highest_price=120.0))
        # Текущая 117.5 -> забираем +17.5% профита!
        self.assertTrue(rule.check("LONG", open_price=open_p, current_price=117.5, highest_price=120.0))

    def test_breakeven_ratchet_with_trail_short(self):
        """Проверка динамического трейлинга для SHORT: подтягивание стопа за дном цены."""
        cfg = {
            "is_active": True,
            "trigger_ratio": 0.025,  # активация при +2.5%
            "trail_ratio": 0.018,    # трейлинг 1.8% от дна
            "buffer_ratio": 0.005    # безубыток +0.5%
        }
        rule = ExitBreakevenRatchetRule(cfg, self.analytics_cfg)

        open_p = 100.0

        # 1. Цена на 99.0 (дно 98.5) -> прибыль 1.5% < 2.5% -> нет выхода
        self.assertFalse(rule.check("SHORT", open_price=open_p, current_price=99.0, lowest_price=98.5))

        # 2. Цена упала до 90.0 (+10% профита в шорте).
        # Трейл-стоп: 90.0 * (1 + 0.018) = 91.62.
        # Текущая цена 91.0 -> держим
        self.assertFalse(rule.check("SHORT", open_price=open_p, current_price=91.0, lowest_price=90.0))

        # Текущая цена отскочила до 91.8 (>= 91.62) -> выход и фиксация прибыли!
        self.assertTrue(rule.check("SHORT", open_price=open_p, current_price=91.8, lowest_price=90.0))

    def test_trail_never_below_breakeven(self):
        """Гарантия: трейлинг-стоп никогда не опускается ниже уровня безубытка."""
        cfg = {
            "is_active": True,
            "trigger_ratio": 0.025,  # +2.5%
            "trail_ratio": 0.030,    # широкий трейл 3%
            "buffer_ratio": 0.005    # BE уровень = 100.5
        }
        rule = ExitBreakevenRatchetRule(cfg, self.analytics_cfg)
        open_p = 100.0

        # Пик ровно 102.6 (+2.6%). Трейл 102.6 * (1 - 0.03) = 99.522 (в минус).
        # Но BE стоп равен 100.5!
        # Значит при цене 100.4 бот обязан выйти в безубыток, а не ждать 99.522!
        self.assertTrue(rule.check("LONG", open_price=open_p, current_price=100.4, highest_price=102.6))
        self.assertFalse(rule.check("LONG", open_price=open_p, current_price=100.6, highest_price=102.6))

    def test_entry_delta_harvester_rule(self):
        """Проверка специализированного правила входа EntryDeltaHarvesterRule."""
        cfg = {
            "is_active": True,
            "min_volume_ratio": 0.40,
            "min_filled_level": 2
        }
        rule = EntryDeltaHarvesterRule(cfg)

        # 1. Нейтральное состояние -> нет входа
        stress_neutral = {
            "status": "NEUTRAL",
            "SHORT": {"in_position": False, "volume_ratio": 0.0, "max_level": -1},
            "LONG": {"in_position": False, "volume_ratio": 0.0, "max_level": -1}
        }
        self.assertFalse(rule.check("LONG", indicators={"grid_stress": stress_neutral}))

        # 2. Сеточник застрял в SHORT (42.9% объема, level 2) -> вход в LONG
        stress_short_stuck = {
            "status": "SHORT_GRID_STRESSED",
            "SHORT": {
                "in_position": True,
                "volume_ratio": 0.429,
                "max_level": 2,
                "stressed": True,
                "price_stressed": True,
                "avg_entry_price": 0.070,
                "drawdown_pct": 5.2
            },
            "LONG": {"in_position": False}
        }
        self.assertTrue(rule.check("LONG", indicators={"grid_stress": stress_short_stuck}))
        self.assertFalse(rule.check("SHORT", indicators={"grid_stress": stress_short_stuck}))

        # 3. Сеточник застрял в LONG (60.2% объема, level 3) -> вход в SHORT
        stress_long_stuck = {
            "status": "LONG_GRID_STRESSED",
            "LONG": {
                "in_position": True,
                "volume_ratio": 0.602,
                "max_level": 3,
                "stressed": True,
                "price_stressed": True,
                "avg_entry_price": 1.50,
                "drawdown_pct": 7.8
            },
            "SHORT": {"in_position": False}
        }
        self.assertTrue(rule.check("SHORT", indicators={"grid_stress": stress_long_stuck}))
        self.assertFalse(rule.check("LONG", indicators={"grid_stress": stress_long_stuck}))

    def test_u_delta_harvester_universe_configuration(self):
        """Проверка наличия и параметров вселенной u_delta_harvester в cfg.json."""
        full_cfg = load_config()
        universes = full_cfg.get("universes", {})
        self.assertIn("u_delta_harvester", universes)

        u_cfg = universes["u_delta_harvester"]
        self.assertTrue(u_cfg.get("is_active"))
        self.assertEqual(u_cfg.get("inactive_grid_mode"), "SKIP")
        self.assertEqual(u_cfg.get("hedge_ratio"), 1.0)

        # Проверка правил выхода
        exit_rules = u_cfg.get("exit_rules", {})
        self.assertIn("breakeven_ratchet", exit_rules)
        self.assertIn("grid_relief", exit_rules)
        self.assertEqual(exit_rules.get("stop_loss_ratio", {}).get("value"), 0.07)
        self.assertIsNone(exit_rules.get("take_profit_ratio", {}).get("value"))

        be = exit_rules["breakeven_ratchet"]
        self.assertTrue(be.get("is_active"))
        self.assertEqual(be.get("trigger_ratio"), 0.025)
        self.assertEqual(be.get("trail_ratio"), 0.018)

    def test_universe_dynamic_delta_sizing(self):
        """Проверка 1:1 дельта-хеджирования: размер ордера равен объему застрявшей сетки."""
        u = StrategyUniverse(
            universe_id="u_delta_harvester",
            name="Delta Harvester Test",
            description="Test Universe",
            enter_rules={"delta_harvester": {"is_active": True}},
            exit_rules={},
            get_slippage_ratio_fn=lambda sym: 0.0005,
            is_active=True,
            inactive_grid_mode="SKIP",
            hedge_ratio=1.0
        )

        cron_state = {
            "LONG": {"has_active": False, "accum_usd": 0.0},
            "SHORT": {
                "has_active": True,
                "accum_usd": 156.40,
                "raw_grid": {"0": {"is_active": True}, "1": {"is_active": True}, "2": {"is_active": True}}
            }
        }

        # Вычисляем хедж для LONG стороны против застрявшего SHORT:
        opp_side = "SHORT"
        opp_accum = cron_state[opp_side]["accum_usd"]
        eff_ratio = u.get_dynamic_hedge_ratio(max_level=2, active_count=3)
        eff_size = round(opp_accum * eff_ratio, 2)

        self.assertEqual(eff_ratio, 1.0)
        self.assertEqual(eff_size, 156.40)


if __name__ == "__main__":
    unittest.main()
