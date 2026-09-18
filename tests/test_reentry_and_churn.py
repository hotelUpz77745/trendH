# ============================================================
# FILE: tests/test_reentry_and_churn.py
# ROLE: Unit tests for Chandelier Exit trade anchoring,
#       re-entry cooldown protection, and exit reason auditing.
# ============================================================

import unittest
import time
from typing import Dict, Any, List

from CORE.models import PositionState
from CORE.universe import StrategyUniverse
from CORE.indicators.squeeze_flow import ChandelierTrailingCalculator, ExitChandelierRule
from CORE.rules import (
    ExitSignalEngine, ExitTakeProfitRule, ExitStopLossRule,
    ExitTrendReversalRule, ExitTimeStopRule
)


class TestChandelierTrailingAnchoring(unittest.TestCase):
    """
    Тестирование исправления Chandelier Exit:
    Трейлинг-стоп должен привязываться к жизни сделки (open_price + цены с момента входа),
    а не выбивать позицию сразу на входе из-за старых исторических свечей.
    """

    def setUp(self):
        # 20 свечей по 5m, среди которых на 10-й свече был исторический шпиль вверх (110.0)
        # при нормальном диапазоне 99-102.
        self.candles = [
            {"high": 110.0 if i == 10 else 102.0, "low": 98.0, "close": 100.0, "ts": (1000 + i * 300) * 1000}
            for i in range(20)
        ]
        self.cfg = {"is_active": True, "length": 15, "atr_mult": 2.0}
        self.calc = ChandelierTrailingCalculator(self.cfg)
        self.rule = ExitChandelierRule(self.cfg)

    def test_no_immediate_exit_on_long_entry(self):
        """Вход в LONG по 100.0 не должен выбиваться сразу из-за старого шпиля 110.0."""
        # Ранее: highest_high = 110.0, ATR ~ 4.0, stop = 110 - 8 = 102.
        # Цена 100 <= 102 -> старый код ошибочно давал True (мгновенный выход!).
        # Новый код: привязка к сделке (open_price=100.0) -> stop = 100 - 8 = 92.0.
        # 100.0 <= 92.0 -> False (сделка держится!).
        should_exit = self.calc.should_exit(
            side="LONG",
            candles=self.candles,
            current_price=100.0,
            open_price=100.0,
            open_time_ms=self.candles[-1]["ts"]
        )
        self.assertFalse(should_exit, "Позиция LONG не должна закрываться немедленно на цене входа!")

    def test_no_immediate_exit_on_short_entry(self):
        """Вход в SHORT по 100.0 не должен выбиваться сразу из-за старого дна."""
        candles_with_dip = [
            {"high": 102.0, "low": 85.0 if i == 5 else 98.0, "close": 100.0, "ts": (1000 + i * 300) * 1000}
            for i in range(20)
        ]
        should_exit = self.calc.should_exit(
            side="SHORT",
            candles=candles_with_dip,
            current_price=100.0,
            open_price=100.0,
            open_time_ms=candles_with_dip[-1]["ts"]
        )
        self.assertFalse(should_exit, "Позиция SHORT не должна закрываться немедленно на цене входа!")

    def test_long_trailing_stop_ratchet_up(self):
        """При росте цены в плюс трейлинг подтягивается вверх и фиксирует прибыль при откате."""
        open_time = self.candles[15]["ts"]
        # Сделка вошла по 100.0, затем цена выросла до 115.0
        # Опорная вершина = 115.0. При ATR ~ 4.0 и mult=2.0 -> стоп = 115 - 8 = 107.0.
        # При откате до 106.0 (< 107.0) трейлинг должен сработать и зафиксировать прибыль.
        should_exit_at_peak = self.calc.should_exit(
            side="LONG",
            candles=self.candles,
            current_price=115.0,
            open_price=100.0,
            open_time_ms=open_time,
            highest_price=115.0
        )
        self.assertFalse(should_exit_at_peak, "На самом пике стоп не должен срабатывать")

        should_exit_on_pullback = self.calc.should_exit(
            side="LONG",
            candles=self.candles,
            current_price=105.0,
            open_price=100.0,
            open_time_ms=open_time,
            highest_price=115.0
        )
        self.assertTrue(should_exit_on_pullback, "При откате ниже трейлинг-стопа Chandelier Exit должен сработать!")

    def test_rule_check_kwargs_forwarding(self):
        """ExitChandelierRule.check корректно передает kwargs в калькулятор."""
        open_time = self.candles[-1]["ts"]
        res = self.rule.check(
            side="LONG",
            current_price=100.0,
            candles=self.candles,
            open_price=100.0,
            open_time_ms=open_time,
            highest_price=100.0
        )
        self.assertFalse(res)


class TestReentryCooldown(unittest.TestCase):
    """
    Тестирование защиты от моментального перезахода (re-entry cooldown).
    После закрытия позиции бот не должен перезаходить на следующем тике.
    """

    def setUp(self):
        self.enter_rules = {
            "trend": {
                "is_active": True, "timeframe": "5m", "sma_fast": 5, "sma_slow": 10,
                "confirmation_candles": 2, "require_rising": True, "trend_positive": True,
                "long_cond": "UP", "short_cond": "DOWN"
            }
        }
        self.exit_rules = {
            "take_profit_ratio": {"value": 0.02},
            "stop_loss_ratio": {"value": 0.02}
        }
        self.slip_fn = lambda s: 0.0005
        self.univ = StrategyUniverse(
            universe_id="test_cooldown",
            name="Cooldown Test",
            description="Test Universe",
            enter_rules=self.enter_rules,
            exit_rules=self.exit_rules,
            get_slippage_ratio_fn=self.slip_fn
        )
        self.univ.reentry_cooldown_sec = 60.0

    def test_cooldown_blocks_immediate_reentry(self):
        """После выхода из позиции вход на следующем тике блокируется кулдауном."""
        # 1. Открываем позицию
        self.univ.state.open_position("BTCUSDT", "LONG", 100.0, 100.0)
        self.assertIsNotNone(self.univ.state.get_position("BTCUSDT", "LONG"))

        # 2. Выходим по TP (+3%)
        ind = {"trend": "UP"}
        self.univ.process_tick("BTCUSDT", "LONG", 103.5, ind, self.slip_fn, is_paused=False, invest_size=100.0)
        self.assertIsNone(self.univ.state.get_position("BTCUSDT", "LONG"))

        # Время выхода зафиксировано
        self.assertIn("BTCUSDT", self.univ.last_exit_time)
        self.assertIn("LONG", self.univ.last_exit_time["BTCUSDT"])

        # 3. Следующий тик через 0.1 секунды с тем же активным сигналом UP
        self.univ.process_tick("BTCUSDT", "LONG", 103.5, ind, self.slip_fn, is_paused=False, invest_size=100.0)
        # Позиция НЕ должна открыться, так как действует кулдаун 60 сек!
        self.assertIsNone(self.univ.state.get_position("BTCUSDT", "LONG"), "Кулдаун должен заблокировать повторный вход!")

    def test_cooldown_allows_entry_after_expiration(self):
        """После истечения кулдауна вход снова разрешен."""
        # Имитируем, что выход был 65 секунд назад
        self.univ.last_exit_time.setdefault("BTCUSDT", {})["LONG"] = time.time() - 65.0
        ind = {"trend": "UP"}
        self.univ.process_tick("BTCUSDT", "LONG", 100.0, ind, self.slip_fn, is_paused=False, invest_size=100.0)
        self.assertIsNotNone(self.univ.state.get_position("BTCUSDT", "LONG"), "Вход должен быть разрешен после истечения кулдауна")

    def test_independent_cooldown_per_symbol_and_side(self):
        """Кулдаун по BTCUSDT LONG не должен блокировать ETHUSDT или BTCUSDT SHORT."""
        self.univ.last_exit_time.setdefault("BTCUSDT", {})["LONG"] = time.time()
        ind = {"trend": "UP"}

        # ETHUSDT LONG должен открыться без препятствий
        self.univ.process_tick("ETHUSDT", "LONG", 2000.0, ind, self.slip_fn, is_paused=False, invest_size=100.0)
        self.assertIsNotNone(self.univ.state.get_position("ETHUSDT", "LONG"))


class TestExitReasonTracking(unittest.TestCase):
    """Тестирование фиксации точной причины выхода в ExitSignalEngine."""

    def test_exit_engine_records_reason(self):
        exit_rules = {
            "take_profit_ratio": {"value": 0.05},
            "stop_loss_ratio": {"value": 0.02}
        }
        engine = ExitSignalEngine(exit_rules, {"taker_fee_ratio": 0.0006}, lambda s: 0.0005)

        # 1. Проверка Take Profit (+6%)
        res_tp = engine.check_signal("LONG", symbol="BTCUSDT", trend="UP", open_price=100.0, current_price=107.0)
        self.assertTrue(res_tp)
        self.assertEqual(engine.last_exit_reason, "ExitTakeProfitRule")

        # 2. Проверка Stop Loss (-4%)
        res_sl = engine.check_signal("LONG", symbol="BTCUSDT", trend="UP", open_price=100.0, current_price=95.0)
        self.assertTrue(res_sl)
        self.assertEqual(engine.last_exit_reason, "ExitStopLossRule")


if __name__ == "__main__":
    unittest.main()
