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
        from consts import cfg
        self._orig_data_sources = dict(cfg.get("data_sources", {}))
        cfg["data_sources"]["runtime_path"] = self.fixtures_dir

    def tearDown(self):
        CronIntegration.clear_cache()
        from consts import cfg
        cfg["data_sources"] = self._orig_data_sources

    def test_find_runtime_file_fallback(self):
        """Проверка поиска файлов в резервной папке фикстур."""
        from consts import cfg
        cfg["data_sources"]["runtime_path"] = None
        fpath = CronIntegration._find_runtime_file("RAYSOLUSDT")
        self.assertIsNotNone(fpath)
        self.assertTrue(os.path.exists(fpath))
        self.assertTrue(fpath.lower().endswith("raysolusdt.json"))
        cfg["data_sources"]["runtime_path"] = self.fixtures_dir

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

        grid_uids = ["u_grid_stress_base", "u_grid_stress_aggr", "u_grid_pure_shadow"]
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
        if u_extreme and u_extreme.is_active:
            self.assertTrue(u_extreme.check_entry("SHORT", indicators))

    def test_empty_hardcoded_symbols_and_null_size(self):
        """
        Проверка целевых условий:
        - hardcoded_symbols = [] -> парсит монеты из symbols_path (app.json)
        - hardcoded_size = null -> размер рассчитывается динамически от набранной сетки
        """
        from consts import cfg
        orig_syms = cfg.get("data_sources", {}).get("hardcoded_symbols")
        orig_size = cfg.get("data_sources", {}).get("hardcoded_size")
        try:
            cfg["data_sources"]["hardcoded_symbols"] = []
            cfg["data_sources"]["hardcoded_size"] = None
            cfg["data_sources"]["runtime_path"] = self.fixtures_dir

            # 1. Загрузка символов из app.json
            syms = CronIntegration.get_symbols()
            self.assertGreaterEqual(len(syms), 1)
            self.assertIn("RAYSOLUSDT", syms)

            # 2. Динамический расчет размера от сетки RAYSOLUSDT (в фикстуре)
            state = CronIntegration.get_symbol_state("RAYSOLUSDT")
            # Для SHORT (хэдж застрявшего лонга cron3 на ~316.5$, уровень 4 -> default 50%): 50% объема = 158.26$
            self.assertAlmostEqual(state["SHORT"]["invest_size"], 158.26, delta=1.0)
            # Для LONG (хэдж шорта cron3 на ~171.6$, уровень 2 -> 75%): 75% объема = 128.70$
            self.assertAlmostEqual(state["LONG"]["invest_size"], 128.70, delta=1.0)

            # 3. Обратная совместимость с фиксированным числом (float = 0.5)
            orig_hedge = cfg["data_sources"].get("default_hedge_ratio")
            try:
                cfg["data_sources"]["default_hedge_ratio"] = 0.5
                state_fixed = CronIntegration.get_symbol_state("RAYSOLUSDT")
                self.assertAlmostEqual(state_fixed["LONG"]["invest_size"], 85.8, delta=1.0)
            finally:
                cfg["data_sources"]["default_hedge_ratio"] = orig_hedge
        finally:
            cfg["data_sources"]["hardcoded_symbols"] = orig_syms
            cfg["data_sources"]["hardcoded_size"] = orig_size

    def test_inactive_grid_mode_options(self):
        """
        Проверка двух режимов при неактивной сетке (is_active=False на всех уровнях):
        1. inactive_grid_mode = 'SKIP' -> invest_size = 0.0, сигнал пропускается.
        2. inactive_grid_mode = 'TAKE_LEVEL_0' -> invest_size = base_order_usd (уровень 0).
        """
        from consts import cfg
        # Создаем временный файл монеты с полностью неактивной сеткой
        inactive_data = {
            "LONG": {
                "enable": True,
                "invest_size": 400,
                "grid": {
                    "0": {"volume": 12.96, "is_active": False},
                    "1": {"volume": 14.26, "is_active": False}
                }
            },
            "SHORT": {
                "enable": True,
                "invest_size": 400,
                "grid": {
                    "0": {"volume": 12.96, "is_active": False},
                    "1": {"volume": 14.26, "is_active": False}
                }
            }
        }
        test_file = os.path.join(self.fixtures_dir, "testinactivesymusdt.json")
        try:
            with open(test_file, "w", encoding="utf-8") as f:
                json.dump(inactive_data, f)

            orig_mode = cfg.get("data_sources", {}).get("inactive_grid_mode")
            orig_size = cfg.get("data_sources", {}).get("hardcoded_size")
            cfg["data_sources"]["hardcoded_size"] = None

            # 1. Тест режима 'SKIP'
            cfg["data_sources"]["inactive_grid_mode"] = "SKIP"
            state_skip = CronIntegration.get_symbol_state("TESTINACTIVESYMUSDT")
            self.assertEqual(state_skip["LONG"]["invest_size"], 0.0)
            self.assertEqual(state_skip["SHORT"]["invest_size"], 0.0)

            # 2. Тест режима 'TAKE_LEVEL_0' (дефолт)
            cfg["data_sources"]["inactive_grid_mode"] = "TAKE_LEVEL_0"
            state_take = CronIntegration.get_symbol_state("TESTINACTIVESYMUSDT")
            self.assertEqual(state_take["LONG"]["invest_size"], 51.84)
            self.assertEqual(state_take["SHORT"]["invest_size"], 51.84)

            # Восстанавливаем оригинальные значения
            cfg["data_sources"]["inactive_grid_mode"] = orig_mode
            cfg["data_sources"]["hardcoded_size"] = orig_size
        finally:
            if os.path.exists(test_file):
                os.remove(test_file)

    def test_dynamic_hedge_ratio_levels(self):
        """
        Проверка карты динамического хеджирования:
        - уровень 0/1: 1.0 (100%)
        - уровни 2-3: 0.75 (75%)
        - уровни выше 3: 0.5 (50%)
        """
        hedge_map = {"0": 1.0, "1": 1.0, "2": 0.75, "3": 0.75, "default": 0.5}
        self.assertEqual(CronIntegration.resolve_hedge_ratio(hedge_map, max_level=0, active_count=1), 1.0)
        self.assertEqual(CronIntegration.resolve_hedge_ratio(hedge_map, max_level=1, active_count=2), 1.0)
        self.assertEqual(CronIntegration.resolve_hedge_ratio(hedge_map, max_level=2, active_count=3), 0.75)
        self.assertEqual(CronIntegration.resolve_hedge_ratio(hedge_map, max_level=3, active_count=4), 0.75)
        self.assertEqual(CronIntegration.resolve_hedge_ratio(hedge_map, max_level=4, active_count=5), 0.5)
        self.assertEqual(CronIntegration.resolve_hedge_ratio(hedge_map, max_level=5, active_count=6), 0.5)
        self.assertEqual(CronIntegration.resolve_hedge_ratio(0.85, max_level=2), 0.85)


if __name__ == "__main__":
    unittest.main()

