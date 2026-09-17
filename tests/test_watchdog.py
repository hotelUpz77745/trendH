# ============================================================
# FILE: tests/test_watchdog.py
# ROLE: Unit tests for WatchdogTGAdapter and LoopWatchdog
# ============================================================

import asyncio
import time
import contextlib
import unittest
from unittest.mock import patch, MagicMock, AsyncMock

from CORE.watchdog import WatchdogTGAdapter, LoopWatchdog


class MockResponse:
    def __init__(self, data: dict, status: int = 200):
        self._data = data
        self.status = status

    async def json(self):
        return self._data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class TestWatchdog(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.mock_adapter = WatchdogTGAdapter(token="TEST_TOKEN", chat_ids=[123456789])

    def test_adapter_chat_ids(self):
        """Проверка получения списка chat_id администраторов."""
        adapter = WatchdogTGAdapter(token="TEST", chat_ids=[111, 222])
        self.assertEqual(adapter._get_chat_ids(), [111, 222])

    def test_adapter_empty_token(self):
        """Проверка безопасного поведения при отсутствии токена."""
        adapter = WatchdogTGAdapter(token="")
        self.assertEqual(adapter.token, "")

    @patch("aiohttp.ClientSession.post")
    async def test_send_alert(self, mock_post):
        """Проверка отправки экстренного алерта в Telegram."""
        mock_post.return_value = MockResponse({"ok": True})
        adapter = WatchdogTGAdapter(token="TEST_TOKEN", chat_ids=[123456])

        with patch("CORE.watchdog.TG_ENABLED", True):
            await adapter.send_alert("🚨 Тестовый алерт")

        self.assertTrue(mock_post.called)
        call_args = mock_post.call_args
        self.assertIn("sendMessage", call_args[0][0])
        payload = call_args[1]["json"]
        self.assertEqual(payload["chat_id"], 123456)
        self.assertEqual(payload["text"], "🚨 Тестовый алерт")

    @patch("aiohttp.ClientSession.post")
    async def test_heartbeat_first_send(self, mock_post):
        """Проверка первичной отправки Heartbeat (создание нового сообщения)."""
        mock_post.return_value = MockResponse({"ok": True, "result": {"message_id": 999}})
        adapter = WatchdogTGAdapter(token="TEST_TOKEN", chat_ids=[123456])

        with patch("CORE.watchdog.TG_ENABLED", True):
            await adapter.send_or_update_heartbeat(server_name="TestServer")

        self.assertEqual(adapter._heartbeat_msg_id, 999)
        self.assertGreater(adapter._heartbeat_msg_time, 0.0)

    @patch("aiohttp.ClientSession.post")
    async def test_heartbeat_edit_message(self, mock_post):
        """Проверка редактирования существующего сообщения Heartbeat (без спама в чат)."""
        mock_post.return_value = MockResponse({"ok": True})
        adapter = WatchdogTGAdapter(token="TEST_TOKEN", chat_ids=[123456])
        adapter._heartbeat_msg_id = 999
        adapter._heartbeat_msg_time = time.time()  # Свежее сообщение

        with patch("CORE.watchdog.TG_ENABLED", True):
            await adapter.send_or_update_heartbeat(server_name="TestServer", autodelete_sec=180)

        call_args = mock_post.call_args
        self.assertIn("editMessageText", call_args[0][0])
        self.assertEqual(call_args[1]["json"]["message_id"], 999)

    @patch("aiohttp.ClientSession.post")
    async def test_heartbeat_autodelete(self, mock_post):
        """Проверка автоудаления устаревшего Heartbeat сообщения."""
        mock_post.return_value = MockResponse({"ok": True, "result": {"message_id": 1001}})
        adapter = WatchdogTGAdapter(token="TEST_TOKEN", chat_ids=[123456])
        adapter._heartbeat_msg_id = 888
        adapter._heartbeat_msg_time = time.time() - 300.0  # 300 сек назад (> 180с)

        with patch("CORE.watchdog.TG_ENABLED", True):
            await adapter.send_or_update_heartbeat(server_name="TestServer", autodelete_sec=180)

        # Должен быть вызов deleteMessage для старого 888 и sendMessage для нового 1001
        self.assertEqual(adapter._heartbeat_msg_id, 1001)

    async def test_loop_watchdog_hang_detection(self):
        """Проверка детекции зависания главного цикла и отправки тревоги."""
        mock_adapter = MagicMock()
        mock_adapter.send_alert = AsyncMock()
        mock_adapter.send_or_update_heartbeat = AsyncMock()

        watchdog = LoopWatchdog(
            server_name="TestBot",
            tg_adapter=mock_adapter
        )
        watchdog.timeout_sec = 0.3
        watchdog.check_interval_sec = 0.05
        watchdog.heartbeat_interval_sec = 100.0

        task = asyncio.create_task(watchdog.start())
        await asyncio.sleep(0.02)
        watchdog.last_tick = time.time() - 10.0  # Симулируем давний тик

        # Ждем срабатывания проверки зависания
        await asyncio.sleep(0.1)
        self.assertTrue(watchdog._alert_sent)
        self.assertTrue(mock_adapter.send_alert.called)

        # Симулируем восстановление цикла
        watchdog.tick()
        await asyncio.sleep(0.1)
        self.assertFalse(watchdog._alert_sent)

        watchdog.stop()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def test_loop_watchdog_tick_throughput(self):
        """Проверка подсчета итераций и пропускной способности главного цикла."""
        watchdog = LoopWatchdog(server_name="TestBot")
        self.assertEqual(watchdog._tick_count, 0)

        for _ in range(50):
            watchdog.tick()

        self.assertEqual(watchdog._tick_count, 50)
        self.assertGreater(watchdog.last_tick, 0.0)

    async def test_watchdog_stop_lifecycle(self):
        """Проверка корректной остановки рабочего цикла Watchdog."""
        watchdog = LoopWatchdog(server_name="TestBot")
        watchdog.check_interval_sec = 0.01
        task = asyncio.create_task(watchdog.start())
        await asyncio.sleep(0.05)
        self.assertTrue(watchdog._is_running)

        watchdog.stop()
        await task
        self.assertFalse(watchdog._is_running)

    @patch("aiohttp.ClientSession.post")
    async def test_heartbeat_message_content(self, mock_post):
        """Проверка содержимого и форматирования HTML-сообщения пульса."""
        mock_post.return_value = MockResponse({"ok": True, "result": {"message_id": 777}})
        adapter = WatchdogTGAdapter(token="TEST_TOKEN", chat_ids=[123456])

        with patch("CORE.watchdog.TG_ENABLED", True):
            await adapter.send_or_update_heartbeat(server_name="TrendH_Special")

        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        self.assertIn("TrendH_Special", payload["text"])
        self.assertIn("running smoothly", payload["text"])
        self.assertIn("UTC", payload["text"])


if __name__ == "__main__":
    unittest.main()
