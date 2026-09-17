# ============================================================
# FILE: tests/test_grid_stress.py
# ROLE: Unit tests for Grid-Stress Hedge logic and CronIntegration
# ============================================================
import unittest
import os
import shutil
import tempfile
import json
from cron_integration import CronIntegration, EntryGridStressRule, ExitGridReliefRule
from CORE.universe import UniverseManager


class TestGridStressIntegration(unittest.TestCase):
    """Тестирование чтения состояния сетки cron3Papper и формирования стресс-сигналов."""

    def setUp(self):
        CronIntegration.clear_cache()
        self.fixtures_dir = os.path.join(os.path.dirname(__file__), "fixtures", "sample_runtime", "runtime")

    def tearDown(self):
        CronIntegration.clear_cache()

    def test_find_runtime_file_fallback(self):
        """Проверка поиска файлов в резервной папке фикстур."""
        fpath = CronIntegration._find_runtime_file("RAYSOLUSDT")
        self.assertIsNotNone(fpath)
        self.assertTrue(os.path.exists(fpath))
        self.assertTrue(fpath.lower().endswith("raysolusdt.json"))

    def test_get_symbol_state(self):
        """Проверка получения базового объема и статуса сетки."""
        state = CronIntegration.get_symbol_state("RAYSOLUSDT")
        self.assertIn("LONG", state)
        self.assertIn("SHORT", state)
        self.assertTrue(state["LONG"]["enabled"])
        self.assertTrue(state["SHORT"]["enabled"])
        self.assertGreater(state["LONG"]["invest_size"], 0.0)

    def test_get_grid_stress_raysol(self):
        """
        В raysolusdt.json:
        - LONG имеет 5 активных уровней (0, 1, 2, 3, 4) -> набрано > 70% объема (Extreme Stress).
        - SHORT имеет 3 активных уровня (0, 1, 2) -> набрано ~ 42% объема.
        """
        stress = CronIntegration.get_grid_stress("RAYSOLUSDT", current_price=1.20)
        self.assertIsNotNone(stress)
        self.assertEqual(stress["status"], "LONG_GRID_EXTREME")
        self.assertEqual(stress["stressed_side"], "LONG")
        self.assertEqual(stress["opposite_side"], "SHORT")
        self.assertTrue(stress["extreme"])

        long_info = stress["LONG"]
        self.assertTrue(long_info["in_position"])
        self.assertEqual(long_info["max_level"], 4)
        self.assertGreater(long_info["volume_ratio"], 0.7)
        self.assertTrue(long_info["stressed"])
        self.assertTrue(long_info["extreme"])

        # При цене 1.20 и средней цене 1.44 просадка лонга должна быть положительной
        self.assertGreater(long_info["drawdown_pct"], 10.0)

    def test_get_grid_stress_cross(self):
        """
        В crossusdt.json:
        - LONG имеет 2 активных уровня (0, 1)
        - SHORT имеет 4 активных уровня (0, 1, 2, 3) -> SHORT в глубоком стрессе.
        """
        stress = CronIntegration.get_grid_stress("CROSSUSDT", current_price=0.50)
        self.assertIsNotNone(stress)
        self.assertEqual(stress["stressed_side"], "SHORT")
        self.assertEqual(stress["opposite_side"], "LONG")

        short_info = stress["SHORT"]
        self.assertTrue(short_info["in_position"])
        self.assertGreaterEqual(short_info["max_level"], 3)
        self.assertTrue(short_info["stressed"])

    def test_get_grid_stress_missing_symbol(self):
        """Отсутствующий символ должен возвращать нейтральный статус без исключений."""
        stress = CronIntegration.get_grid_stress("NONEXISTENT_SYMBOL_XYZ", current_price=10.0)
        self.assertEqual(stress["status"], "NEUTRAL")
        self.assertIsNone(stress["stressed_side"])
        self.assertIsNone(stress["opposite_side"])
        self.assertFalse(stress["LONG"]["in_position"])
        self.assertFalse(stress["SHORT"]["in_position"])

    def test_entry_rule_direction_inversion(self):
        """
        Проверка инверсии направления:
        - Если LONG сетки застрял -> TrendH входит в SHORT.
        - Если SHORT сетки застрял -> TrendH входит в LONG.
        """
        rule = EntryGridStressRule({
            "is_active": True,
            "min_volume_ratio": 0.5,
            "min_filled_level": 3,
            "long_cond": "SHORT_GRID_STRESSED",
            "short_cond": "LONG_GRID_STRESSED"
        })

        # Ситуация 1: застрял LONG сетки
        stress_long_stuck = {
            "status": "LONG_GRID_STRESSED",
            "LONG": {"in_position": True, "volume_ratio": 0.65, "max_level": 3, "stressed": True, "extreme": False},
            "SHORT": {"in_position": False, "volume_ratio": 0.0, "max_level": -1, "stressed": False, "extreme": False}
        }
        # TrendH должен разрешить вход в SHORT
        self.assertTrue(rule.check("SHORT", indicators={"grid_stress": stress_long_stuck}))
        # TrendH НЕ должен входить в LONG
        self.assertFalse(rule.check("LONG", indicators={"grid_stress": stress_long_stuck}))

        # Ситуация 2: застрял SHORT сетки
        stress_short_stuck = {
            "status": "SHORT_GRID_STRESSED",
            "LONG": {"in_position": False, "volume_ratio": 0.0, "max_level": -1, "stressed": False, "extreme": False},
            "SHORT": {"in_position": True, "volume_ratio": 0.60, "max_level": 3, "stressed": True, "extreme": False}
        }
        # TrendH должен разрешить вход в LONG
        self.assertTrue(rule.check("LONG", indicators={"grid_stress": stress_short_stuck}))
        # TrendH НЕ должен входить в SHORT
        self.assertFalse(rule.check("SHORT", indicators={"grid_stress": stress_short_stuck}))

    def test_entry_rule_extreme_only(self):
        """Проверка фильтра extreme_only (Решение 2: только экстремальные уровни 4/5)."""
        rule_extreme = EntryGridStressRule({
            "is_active": True,
            "extreme_only": True,
            "long_cond": "SHORT_GRID_EXTREME",
            "short_cond": "LONG_GRID_EXTREME"
        })

        moderate_stress = {
            "status": "LONG_GRID_STRESSED",
            "LONG": {"in_position": True, "volume_ratio": 0.55, "max_level": 3, "stressed": True, "extreme": False},
            "SHORT": {"in_position": False, "volume_ratio": 0.0, "max_level": -1, "stressed": False, "extreme": False}
        }
        # Обычный стресс не должен вызывать вход
        self.assertFalse(rule_extreme.check("SHORT", indicators={"grid_stress": moderate_stress}))

        extreme_stress = {
            "status": "LONG_GRID_EXTREME",
            "LONG": {"in_position": True, "volume_ratio": 0.80, "max_level": 4, "stressed": True, "extreme": True},
            "SHORT": {"in_position": False, "volume_ratio": 0.0, "max_level": -1, "stressed": False, "extreme": False}
        }
        # Экстремальный стресс вызывает вход в SHORT
        self.assertTrue(rule_extreme.check("SHORT", indicators={"grid_stress": extreme_stress}))

    def test_exit_rule_grid_relief(self):
        """
        Проверка выхода Grid Relief:
        Если TrendH находится в SHORT (хэджируя LONG сетки), выход срабатывает,
        когда LONG сетки закрывается по TP или разгружается ниже порога.
        """
        exit_rule = ExitGridReliefRule({
            "is_active": True,
            "exit_on_position_close": True,
            "max_volume_ratio": 0.2
        })

        # 1. Сетка еще держит большой объем -> не выходим
        stress_active = {
            "LONG": {"in_position": True, "volume_ratio": 0.65}
        }
        self.assertFalse(exit_rule.check("SHORT", indicators={"grid_stress": stress_active}))

        # 2. Сетка закрылась по TP (in_position = False) -> выходим!
        stress_closed = {
            "LONG": {"in_position": False, "volume_ratio": 0.0}
        }
        self.assertTrue(exit_rule.check("SHORT", indicators={"grid_stress": stress_closed}))

        # 3. Сетка частично разгрузилась (volume_ratio <= 0.2) -> выходим!
        stress_relieved = {
            "LONG": {"in_position": True, "volume_ratio": 0.15}
        }
        self.assertTrue(exit_rule.check("SHORT", indicators={"grid_stress": stress_relieved}))

    def test_universes_execution_with_grid_stress(self):
        """Проверка работы UniverseManager со всеми 4 сеточно-стрессовыми стратегиями."""
        from consts import load_config
        cfg_data = load_config()
        mgr = UniverseManager(
            universes_cfg=cfg_data.get("universes", {}),
            default_enter_rules={},
            default_exit_rules={},
            get_slippage_ratio_fn=lambda s: 0.001
        )

        grid_uids = ["u_grid_stress_base", "u_grid_stress_aggr", "u_grid_extreme_breakout", "u_grid_pure_shadow"]
        for uid in grid_uids:
            u = mgr.get_universe(uid)
            self.assertIsNotNone(u, f"Universe {uid} not found")
            self.assertTrue(u.is_active)

        # Симуляция тика с данными RAYSOLUSDT (LONG в глубоком стрессе)
        stress = CronIntegration.get_grid_stress("RAYSOLUSDT", current_price=1.20)
        indicators = {
            "trend": "DOWN",
            "trend_htf": "DOWN",
            "grid_stress": stress,
            "taker_flow": ["TAKER_SELL_DOMINANT"],
            "vol_filter": ["VOLF_PASSED"]
        }

        # u_grid_pure_shadow и u_grid_stress_base должны среагировать на SHORT
        u_pure = mgr.get_universe("u_grid_pure_shadow")
        self.assertTrue(u_pure.check_entry("SHORT", indicators))
        self.assertFalse(u_pure.check_entry("LONG", indicators))

        u_base = mgr.get_universe("u_grid_stress_base")
        self.assertTrue(u_base.check_entry("SHORT", indicators))
        self.assertFalse(u_base.check_entry("LONG", indicators))

        u_extreme = mgr.get_universe("u_grid_extreme_breakout")
        self.assertTrue(u_extreme.check_entry("SHORT", indicators))


if __name__ == "__main__":
    unittest.main()
