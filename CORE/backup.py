# ============================================================
# FILE: CORE/backup.py
# ROLE: Periodically zips and backs up state to Telegram
# ============================================================
import asyncio
import os
import zipfile
import time
from datetime import datetime
from aiogram.types import FSInputFile
from c_log import log
from notifier import NotifierManager
from consts import BACKUP_CFG, DATA_DIR

class RuntimeBackupManager:
    def __init__(self, notifier: NotifierManager):
        self.notifier = notifier
        self.enabled = BACKUP_CFG.get("enabled", True)
        self.debounce_sec = BACKUP_CFG.get("debounce_sec", 10)
        self.max_interval_sec = BACKUP_CFG.get("max_interval_sec", 300)
        self._needs_backup = False
        self._last_backup_time = time.time()
        self._is_running = False

    def mark_changed(self):
        self._needs_backup = True

    async def start(self):
        if not self.enabled: return
        self._is_running = True
        log("RuntimeBackupManager started.", level="INFO")
        while self._is_running:
            try:
                now = time.time()
                time_since_last = now - self._last_backup_time
                
                # Perform backup if needed and either debounced or max interval reached
                if self._needs_backup and (time_since_last >= self.debounce_sec or time_since_last >= self.max_interval_sec):
                    await self._create_and_send_backup()
                    self._needs_backup = False
                    self._last_backup_time = time.time()
            except Exception as e:
                log(f"[BACKUP] Error in backup loop: {e}", level="ERROR")
            await asyncio.sleep(1)

    async def _create_and_send_backup(self):
        state_file = DATA_DIR / "state.json"
        if not state_file.exists(): 
            return
        
        date_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        zip_filename = DATA_DIR / f"state_backup_{date_str}.zip"
        
        try:
            with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
                zipf.write(state_file, arcname="state.json")
                
            caption = "💾 Runtime Backup\n\nСвежий слепок data/state.json"
            if hasattr(self.notifier, "tg_bot") and self.notifier.tg_bot:
                file_obj = FSInputFile(path=str(zip_filename))
                await self.notifier.tg_bot.send_document_to_all(file_obj, caption)
                log(f"[BACKUP] Sent backup {zip_filename.name} to Telegram.", level="INFO")
            else:
                log("[BACKUP] No TG bot available to send backup.", level="WARNING")
        except Exception as e:
            log(f"[BACKUP] Creation/send failed: {e}", level="ERROR")
        finally:
            if zip_filename.exists():
                os.remove(zip_filename)

    def stop(self):
        self._is_running = False
