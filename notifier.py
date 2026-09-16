# ============================================================
# FILE: notifier.py
# ROLE: Менеджер уведомлений по просадке и профициту
# ============================================================
import asyncio
import os
import aiohttp
from consts import DATA_DIR, ANALYTICS_DIR, TG_ALLOWED_USERS, TG_TOKEN, cfg
from utils import Utils
from c_log import log

class NotifierManager:
    def __init__(self):
        self.is_running = False
        self.neg_flag = False
        self.pos_flag = False
        self._task = None
        self.last_neg_threshold = None
        self.last_pos_threshold = None

    async def start(self):
        self.is_running = True
        self._task = asyncio.create_task(self._loop())
        log("[NOTIFIER] Started.", level="INFO")

    async def stop(self):
        self.is_running = False
        if self._task:
            self._task.cancel()
        log("[NOTIFIER] Stopped.", level="INFO")

    async def _loop(self):
        while self.is_running:
            try:
                await self.check_thresholds()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log(f"[NOTIFIER] Error in loop: {e}", level="ERROR")
            await asyncio.sleep(15)

    def _get_chat_ids(self):
        chat_ids = []
        try:
            if TG_ALLOWED_USERS:
                chat_ids.extend(TG_ALLOWED_USERS)
        except Exception:
            pass
        return chat_ids

    async def check_thresholds(self):
        # Читаем конфиг на лету, чтобы реагировать на изменения через Telegram
        app_cfg = Utils.read_json_file(DATA_DIR / "app.json")
        notif_cfg = app_cfg.get("notifications", {})
        if not notif_cfg.get("enabled", False):
            return

        neg_threshold = float(notif_cfg.get("negative_threshold", -100.0))
        pos_threshold = float(notif_cfg.get("positive_threshold", 100.0))

        # Если пороги изменились с прошлого тика - сбрасываем флаги
        if self.last_neg_threshold is not None and self.last_neg_threshold != neg_threshold:
            self.neg_flag = False
            log(f"[NOTIFIER] Negative threshold changed to {neg_threshold}. Resetting neg_flag.", level="INFO")
        if self.last_pos_threshold is not None and self.last_pos_threshold != pos_threshold:
            self.pos_flag = False
            log(f"[NOTIFIER] Positive threshold changed to {pos_threshold}. Resetting pos_flag.", level="INFO")
            
        self.last_neg_threshold = neg_threshold
        self.last_pos_threshold = pos_threshold

        # Читаем текущий профит из аналитики
        analytics_data = Utils.read_json_file(ANALYTICS_DIR / "analytics.json")
        if not analytics_data:
            return
        net_profit = float(analytics_data.get("net_profit_usdt", 0.0))

        # Логика NEGATIVE
        if net_profit <= neg_threshold and not self.neg_flag:
            self.neg_flag = True
            msg = f"⚠️ <b>ВНИМАНИЕ! ПРОСАДКА!</b>\nПрофит опустился до: <b>{net_profit} USDT</b>\nПорог: {neg_threshold} USDT"
            log(f"[NOTIFIER] Negative threshold reached: {net_profit} <= {neg_threshold}", level="INFO")
            await self.send_alert(msg)
        elif self.neg_flag and net_profit >= 0:
            self.neg_flag = False
            msg = f"✅ <b>ПРОСАДКА ВОССТАНОВЛЕНА.</b>\nТекущий профит: <b>{net_profit} USDT</b>\nФлаг тревоги снят."
            log(f"[NOTIFIER] Negative drawdown recovered: {net_profit} >= 0", level="INFO")
            await self.send_alert(msg)

        # Логика POSITIVE
        if net_profit >= pos_threshold and not self.pos_flag:
            self.pos_flag = True
            msg = f"🎉 <b>ОТЛИЧНО! ДОСТИГНУТ ПРОФИЦИТ!</b>\nПрофит: <b>{net_profit} USDT</b>\nПорог: {pos_threshold} USDT"
            log(f"[NOTIFIER] Positive threshold reached: {net_profit} >= {pos_threshold}", level="INFO")
            await self.send_alert(msg)
        elif self.pos_flag and net_profit <= 0:
            self.pos_flag = False
            msg = f"📉 <b>ПРОФИЦИТ ОПУСТИЛСЯ НИЖЕ НУЛЯ.</b>\nТекущий профит: <b>{net_profit} USDT</b>\nФлаг позитивного порога снят."
            log(f"[NOTIFIER] Positive profit lost: {net_profit} <= 0", level="INFO")
            await self.send_alert(msg)

    async def send_alert(self, text: str):
        tg_cfg = cfg.get("telegram", {})
        if not tg_cfg.get("enabled", False):
            return
            
        token = TG_TOKEN
        if not token:
            return
            
        chat_ids = self._get_chat_ids()
        if not chat_ids:
            return
            
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        
        async with aiohttp.ClientSession() as session:
            for uid in chat_ids:
                try:
                    payload = {"chat_id": uid, "text": text, "parse_mode": "HTML"}
                    async with session.post(url, json=payload, timeout=5) as response:
                        if response.status != 200:
                            err_text = await response.text()
                            log(f"[NOTIFIER] Failed to send TG alert to {uid}: {err_text}", level="ERROR")
                except Exception as e:
                    log(f"[NOTIFIER] Error sending TG alert to {uid}: {e}", level="ERROR")

    def reset_flags(self):
        self.neg_flag = False
        self.pos_flag = False
        log("[NOTIFIER] Notification flags manually reset.", level="INFO")
