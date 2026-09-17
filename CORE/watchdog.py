# ============================================================
# FILE: CORE/watchdog.py
# ROLE: Background loop supervisor, hang detection & TG heartbeat
# ============================================================

import asyncio
import os
import time
import datetime
from typing import List, Optional
import aiohttp

from consts import (
    TG_TOKEN,
    TG_ENABLED,
    TG_ALLOWED_USERS,
    WATCHDOG_CFG
)
from c_log import log


class WatchdogTGAdapter:
    """
    Адаптер для отправки критических алертов и ритмичного Heartbeat в Telegram.
    Использует прямое асинхронное подключение через aiohttp к Telegram Bot API.
    """

    def __init__(self, token: Optional[str] = None, chat_ids: Optional[List[int | str]] = None):
        if token is not None:
            self.token = token
        else:
            self.token = os.getenv("TG_BOT_TOKEN") or os.getenv("TG_TOKEN") or TG_TOKEN or ""
        self._chat_ids = chat_ids
        self._heartbeat_msg_id: Optional[int] = None
        self._heartbeat_msg_time: float = 0.0

    def _get_chat_ids(self) -> List[int | str]:
        if self._chat_ids:
            return self._chat_ids

        chat_ids: List[int | str] = []
        try:
            if TG_ALLOWED_USERS:
                chat_ids.extend(TG_ALLOWED_USERS)
        except Exception:
            pass

        admin_env = os.getenv("TG_ADMIN_ID")
        if admin_env and admin_env not in chat_ids:
            chat_ids.append(admin_env)

        return chat_ids

    async def send_alert(self, msg: str) -> None:
        """Отправляет экстренный алерт всем администраторам."""
        if not TG_ENABLED or not self.token:
            return

        chat_ids = self._get_chat_ids()
        if not chat_ids:
            return

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        timeout = aiohttp.ClientTimeout(total=8)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                for chat_id in chat_ids:
                    try:
                        payload = {"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}
                        async with session.post(url, json=payload):
                            pass
                    except Exception as ex:
                        log(f"[WATCHDOG] Ошибка отправки алерта {chat_id}: {ex}", level="ERROR")
        except Exception as e:
            log(f"[WATCHDOG] Сбой сессии отправки алерта: {e}", level="ERROR")

    async def send_or_update_heartbeat(
        self,
        server_name: str = "TrendH_Papper",
        autodelete_sec: int = 180
    ) -> None:
        """
        Отстукивает пульс работы в Telegram.
        Редактирует текущее сообщение или пересоздает его с автоочисткой старого.
        """
        if not TG_ENABLED or not self.token:
            return

        chat_ids = self._get_chat_ids()
        if not chat_ids:
            return

        chat_id = chat_ids[0]
        now = time.time()

        try:
            utc_now = datetime.datetime.now(datetime.timezone.utc)
            date_str = utc_now.strftime("%Y-%m-%d")
            time_utc_str = utc_now.strftime("%H:%M:%S UTC")

            msg = (
                f"🟢 <b>{date_str}</b>\n\n"
                f"Server: <b>{server_name}</b> is running smoothly.\n\n"
                f"🕒 {time_utc_str}"
            )

            timeout = aiohttp.ClientTimeout(total=8)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # 1. Если сообщение старше autodelete_sec — удаляем его для чистоты чата
                if self._heartbeat_msg_id and (now - self._heartbeat_msg_time) >= autodelete_sec:
                    delete_url = f"https://api.telegram.org/bot{self.token}/deleteMessage"
                    payload = {"chat_id": chat_id, "message_id": self._heartbeat_msg_id}
                    try:
                        async with session.post(delete_url, json=payload):
                            pass
                    except Exception:
                        pass
                    self._heartbeat_msg_id = None
                    self._heartbeat_msg_time = 0.0

                # 2. Если есть живой message_id — редактируем его
                if self._heartbeat_msg_id:
                    edit_url = f"https://api.telegram.org/bot{self.token}/editMessageText"
                    payload = {
                        "chat_id": chat_id,
                        "message_id": self._heartbeat_msg_id,
                        "text": msg,
                        "parse_mode": "HTML"
                    }
                    async with session.post(edit_url, json=payload) as resp:
                        res = await resp.json()
                        if not res.get("ok"):
                            self._heartbeat_msg_id = None

                # 3. Если сообщения нет или edit не прошел — отправляем новое
                if not self._heartbeat_msg_id:
                    send_url = f"https://api.telegram.org/bot{self.token}/sendMessage"
                    payload = {"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}
                    async with session.post(send_url, json=payload) as resp:
                        res = await resp.json()
                        if res.get("ok"):
                            self._heartbeat_msg_id = res["result"]["message_id"]
                            self._heartbeat_msg_time = now

        except Exception as e:
            log(f"[WATCHDOG] Ошибка обновления Heartbeat: {e}", level="WARNING")


class LoopWatchdog:
    """
    Фоновый контроллер состояния главного цикла TrendH.
    Отслеживает зависания, измеряет пропускную способность и отстукивает ритм в TG.
    """

    def __init__(
        self,
        notifier=None,
        server_name: str = "TrendH_Papper",
        tg_adapter: Optional[WatchdogTGAdapter] = None
    ):
        self.notifier = notifier
        self.server_name = server_name
        self.timeout_sec: int = int(WATCHDOG_CFG.get("timeout_sec", 60))
        self.check_interval_sec: int = int(WATCHDOG_CFG.get("check_interval_sec", 1))
        self.heartbeat_interval_sec: int = int(WATCHDOG_CFG.get("heartbeat_interval_sec", 60))
        self.heartbeat_autodelete_sec: int = int(WATCHDOG_CFG.get("heartbeat_autodelete_sec", 180))

        self.tg_adapter = tg_adapter or WatchdogTGAdapter()
        self.last_tick: float = time.time()
        self._tick_count: int = 0
        self._is_running: bool = False
        self._alert_sent: bool = False

        self._last_report_time: float = time.time()
        self._last_report_ticks: int = 0
        self._last_heartbeat_time: float = 0.0

    def tick(self) -> None:
        """Регистрирует активный проход главного цикла."""
        self.last_tick = time.time()
        self._tick_count += 1

    async def start(self) -> None:
        """Основной рабочий цикл мониторинга и отстукивания ритма."""
        self._is_running = True
        self.last_tick = time.time()
        self._last_report_time = time.time()
        self._last_report_ticks = self._tick_count
        log(
            f"[WATCHDOG] Запущен. Timeout={self.timeout_sec}s, Heartbeat={self.heartbeat_interval_sec}s",
            level="INFO"
        )

        while self._is_running:
            now = time.time()
            diff = now - self.last_tick

            # 1. Проверка на зависание (Watchdog Alert)
            if diff > self.timeout_sec:
                if not self._alert_sent:
                    msg = (
                        f"🚨 <b>ВНИМАНИЕ! Сервер {self.server_name} завис!</b>\n"
                        f"Главный цикл не отвечает уже {int(diff)} секунд!"
                    )
                    log(f"[WATCHDOG] ВНИМАНИЕ! Сервер {self.server_name} завис на {int(diff)} сек!", level="ERROR")
                    asyncio.create_task(self.tg_adapter.send_alert(msg))
                    self._alert_sent = True
            else:
                if self._alert_sent:
                    msg = (
                        f"✅ <b>Сервер {self.server_name} отвис!</b>\n"
                        f"Главный цикл снова работает в штатном режиме."
                    )
                    log(f"[WATCHDOG] Сервер {self.server_name} возобновил работу в штатном режиме.", level="INFO")
                    asyncio.create_task(self.tg_adapter.send_alert(msg))
                    self._alert_sent = False

            # 2. Периодический отчет о пропускной способности цикла (раз в 3600с)
            time_since_report = now - self._last_report_time
            if time_since_report >= 3600.0:
                ticks_passed = self._tick_count - self._last_report_ticks
                if ticks_passed > 0:
                    avg_iter = time_since_report / ticks_passed
                    log(
                        f"[WATCHDOG] Производительность: {ticks_passed} итераций за {time_since_report:.1f}s. "
                        f"Средний цикл: {avg_iter:.3f}s",
                        level="INFO"
                    )
                self._last_report_time = now
                self._last_report_ticks = self._tick_count

            # 3. Отстукивание ритма (Heartbeat в Telegram)
            if now - self._last_heartbeat_time >= self.heartbeat_interval_sec:
                self._last_heartbeat_time = now
                asyncio.create_task(
                    self.tg_adapter.send_or_update_heartbeat(
                        server_name=self.server_name,
                        autodelete_sec=self.heartbeat_autodelete_sec
                    )
                )

            await asyncio.sleep(self.check_interval_sec)

    def stop(self) -> None:
        """Останавливает мониторинг."""
        self._is_running = False
