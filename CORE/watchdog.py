# ============================================================
# FILE: CORE/watchdog.py
# ROLE: Monitors main loop for hangs
# ============================================================
import asyncio
import time
from c_log import log
from consts import WATCHDOG_CFG

class LoopWatchdog:
    def __init__(self, notifier):
        self.notifier = notifier
        self.timeout_sec = WATCHDOG_CFG.get("timeout_sec", 60)
        self.check_interval_sec = WATCHDOG_CFG.get("check_interval_sec", 1)
        self.last_tick = time.time()
        self._is_running = False

    def tick(self):
        self.last_tick = time.time()

    async def start(self):
        self._is_running = True
        log(f"Watchdog started. Timeout={self.timeout_sec}s", level="INFO")
        while self._is_running:
            try:
                now = time.time()
                if now - self.last_tick > self.timeout_sec:
                    msg = f"ВНИМАНИЕ! Главный цикл не отвечает более {self.timeout_sec} секунд!"
                    log(msg, level="ERROR")
                    if hasattr(self.notifier, "tg_bot") and self.notifier.tg_bot:
                        await self.notifier.tg_bot.send_message_to_all(msg)
                    else:
                        await self.notifier.send_alert(msg)
                    
                    self.last_tick = time.time() # Reset to avoid spam
            except Exception as e:
                log(f"Watchdog error: {e}", level="ERROR")
            await asyncio.sleep(self.check_interval_sec)

    def stop(self):
        self._is_running = False
