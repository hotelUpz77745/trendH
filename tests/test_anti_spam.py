# ============================================================
# FILE: tests/test_anti_spam.py
# ROLE: Unit tests for LogAntiSpammer and UnifiedLogger anti-spam
# ============================================================
import unittest
import time
from c_log import LogAntiSpammer, UnifiedLogger, log


class TestLogAntiSpammer(unittest.TestCase):
    def setUp(self):
        self.spammer = LogAntiSpammer()

    def test_first_message_allowed(self):
        """Первое сообщение любого уровня должно проходить немедленно."""
        allowed, msg = self.spammer.process("Test initial error", level="ERROR")
        self.assertTrue(allowed)
        self.assertEqual(msg, "Test initial error")

        allowed_info, msg_info = self.spammer.process("Test initial info", level="INFO")
        self.assertTrue(allowed_info)
        self.assertEqual(msg_info, "Test initial info")

    def test_suppression_within_window(self):
        """Повторные идентичные сообщения в пределах окна должны подавляться."""
        # Первое пропускается
        allowed1, _ = self.spammer.process("Connection timeout: binance.com", level="ERROR", throttle_sec=1.0)
        self.assertTrue(allowed1)

        # Второе и третье в течение окна подавляются
        allowed2, _ = self.spammer.process("Connection timeout: binance.com", level="ERROR", throttle_sec=1.0)
        self.assertFalse(allowed2)

        allowed3, _ = self.spammer.process("Connection timeout: binance.com", level="ERROR", throttle_sec=1.0)
        self.assertFalse(allowed3)

    def test_summary_emission_after_window(self):
        """После истечения окна выводится сводка с числом повторов."""
        # 1-й вызов
        self.spammer.process("Rate limit warning", level="WARNING", throttle_sec=0.1)

        # 3 подавленных вызова
        self.spammer.process("Rate limit warning", level="WARNING", throttle_sec=0.1)
        self.spammer.process("Rate limit warning", level="WARNING", throttle_sec=0.1)
        self.spammer.process("Rate limit warning", level="WARNING", throttle_sec=0.1)

        # Ждем истечения окна
        time.sleep(0.12)

        allowed, final_msg = self.spammer.process("Rate limit warning", level="WARNING", throttle_sec=0.1)
        self.assertTrue(allowed)
        self.assertIn("[Повторено 3 раз", final_msg)
        self.assertIn("Rate limit warning", final_msg)

    def test_critical_markers_never_throttled(self):
        """Критические торговые события никогда не должны глушиться."""
        critical_samples = [
            "[SIGNAL ENTRY] [u1][BTCUSDT][LONG] Trend: UP, RSI: 55",
            "[SIGNAL EXIT] [u1][BTCUSDT][LONG] Выход! PnL: +1.5%",
            "[POSITION OPEN] [u1][BTCUSDT][LONG] Цена: 60000, Размер: 50$",
            "[CLOSE ALL] Экстренное закрытие позиций",
            "Close All: Успешно закрыто 5 позиций",
            "[WATCHDOG] ВНИМАНИЕ! Сервер завис!",
            "[WATCHDOG] Сервер возобновил работу",
        ]

        for sample in critical_samples:
            # 5 быстрых повторов подряд
            for _ in range(5):
                allowed, msg = self.spammer.process(sample, level="INFO", throttle_sec=10.0)
                self.assertTrue(allowed, f"Critical event suppressed: {sample}")
                self.assertEqual(msg, sample)

    def test_custom_throttle_key(self):
        """throttle_key группирует сообщения независимо от динамического текста."""
        allowed1, _ = self.spammer.process("Coin ADA err: code 1", level="ERROR", throttle_sec=1.0, throttle_key="err_coin")
        self.assertTrue(allowed1)

        # Другой текст, но тот же throttle_key
        allowed2, _ = self.spammer.process("Coin SOL err: code 2", level="ERROR", throttle_sec=1.0, throttle_key="err_coin")
        self.assertFalse(allowed2)

        # Другой throttle_key пропускается
        allowed3, _ = self.spammer.process("Coin BTC err: code 3", level="ERROR", throttle_sec=1.0, throttle_key="err_btc")
        self.assertTrue(allowed3)

    def test_default_level_throttles(self):
        """Проверка дефолтных интервалов троттлинга по уровням логов."""
        self.assertGreaterEqual(self.spammer.DEFAULT_THROTTLES["ERROR"], 5.0)
        self.assertGreaterEqual(self.spammer.DEFAULT_THROTTLES["WARNING"], 10.0)
        self.assertGreaterEqual(self.spammer.DEFAULT_THROTTLES["INFO"], 3.0)
        self.assertGreaterEqual(self.spammer.DEFAULT_THROTTLES["DEBUG"], 2.0)

    def test_stale_records_cleaning(self):
        """Проверка очистки устаревших записей при превышении лимита вызовов."""
        now = time.time()
        # Имитируем старую запись
        self.spammer._records["ERROR:old_key"] = {
            "last_time": now - 400.0,
            "count": 0,
            "first_suppressed": 0.0
        }
        self.spammer._records["ERROR:fresh_key"] = {
            "last_time": now - 10.0,
            "count": 0,
            "first_suppressed": 0.0
        }

        # Вызываем очистку
        self.spammer._counter = 149
        self.spammer._clean_stale(now)

        self.assertNotIn("ERROR:old_key", self.spammer._records)
        self.assertIn("ERROR:fresh_key", self.spammer._records)


class TestUnifiedLoggerIntegration(unittest.TestCase):
    def setUp(self):
        self.logger = UnifiedLogger("TEST_LOGGER")

    def test_logger_has_anti_spammer(self):
        """UnifiedLogger должен содержать экземпляр LogAntiSpammer."""
        self.assertIsInstance(self.logger.anti_spammer, LogAntiSpammer)

    def test_logger_methods_no_crash(self):
        """Методы debug, info, warning, error, exception должны безопасно вызываться с троттлингом."""
        with unittest.mock.patch.object(self.logger._logger.logger, 'callHandlers'):
            self.logger.info("Test info 1", throttle_sec=0.1)
            self.logger.info("Test info 1", throttle_sec=0.1)  # Подавляется без падения
            self.logger.warning("Test warning 1", throttle_sec=0.1)
            self.logger.error("Test error 1", throttle_sec=0.1)
            self.logger.debug("Test debug 1", throttle_sec=0.1)

            try:
                raise ValueError("Test internal error")
            except ValueError as ex:
                self.logger.exception("Caught exception test", exc=ex, throttle_sec=0.1)

    def test_global_log_helper(self):
        """Глобальная функция log() должна корректно маршрутизировать троттлинг."""
        from c_log import _global_logger
        with unittest.mock.patch.object(_global_logger._logger.logger, 'callHandlers'):
            log("Global info test 1", level="INFO", throttle_sec=0.1)
            log("Global info test 1", level="INFO", throttle_sec=0.1)
            log("Global error test 1", level="ERROR", throttle_sec=0.1)
            log("Global warning test 1", level="WARNING", throttle_sec=0.1)
            log("Global debug test 1", level="DEBUG", throttle_sec=0.1)

            try:
                raise RuntimeError("Simulation error")
            except RuntimeError as ex:
                log("Global exception test", level="ERROR", exc=ex, throttle_sec=0.1)


if __name__ == "__main__":
    unittest.main()
