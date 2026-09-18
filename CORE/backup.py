# ============================================================
# FILE: CORE/backup.py
# ROLE: Periodically zips, verifies and backs up state to Telegram
# ============================================================
import asyncio
import os
import zipfile
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
from aiogram.types import FSInputFile
from c_log import log
from notifier import NotifierManager
from consts import BACKUP_CFG, DATA_DIR


class RuntimeBackupManager:
    """
    Менеджер фонового резервного копирования торгового состояния бота.
    
    Осуществляет дебаунс-сохранение, компрессию в ZIP, верификацию целостности
    архива и отправку файла резервной копии (state.json) через Telegram-бота.
    """

    def __init__(self, notifier: NotifierManager):
        self.notifier = notifier
        self.enabled: bool = bool(BACKUP_CFG.get("enabled", True))
        self.debounce_sec: float = float(BACKUP_CFG.get("debounce_sec", 10))
        self.max_interval_sec: float = float(BACKUP_CFG.get("max_interval_sec", 300))
        self._needs_backup: bool = False
        self._last_backup_time: float = time.time()
        self._is_running: bool = False
        self._total_backups_sent: int = 0
        self._last_backup_filename: Optional[str] = None
        self._last_error: Optional[str] = None

    def mark_changed(self) -> None:
        """Помечает состояние как измененное для следующей итерации бэкапа."""
        self._needs_backup = True

    @property
    def is_running(self) -> bool:
        """Флаг активности цикла бэкапа."""
        return self._is_running

    def get_backup_status(self) -> Dict[str, Any]:
        """
        Возвращает сводный статус менеджера бэкапов для мониторинга и отладки.
        """
        now = time.time()
        return {
            "enabled": self.enabled,
            "is_running": self._is_running,
            "needs_backup": self._needs_backup,
            "debounce_sec": self.debounce_sec,
            "max_interval_sec": self.max_interval_sec,
            "last_backup_time": self._last_backup_time,
            "elapsed_since_last_sec": round(now - self._last_backup_time, 2),
            "total_backups_sent": self._total_backups_sent,
            "last_backup_filename": self._last_backup_filename,
            "last_error": self._last_error,
        }

    @staticmethod
    def estimate_state_size() -> int:
        """Возвращает размер state.json в байтах или 0, если файл не найден."""
        state_file = DATA_DIR / "state.json"
        try:
            if state_file.exists():
                return state_file.stat().st_size
        except Exception:
            pass
        return 0

    @staticmethod
    def verify_zip_integrity(zip_path: Path) -> bool:
        """
        Проверяет целостность созданного ZIP-архива по CRC32.
        Возвращает True, если архив корректен, иначе False.
        """
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                bad_file = zf.testzip()
                return bad_file is None
        except Exception as e:
            log(f"[BACKUP] Ошибка верификации ZIP {zip_path.name}: {e}", level="ERROR")
            return False

    async def start(self) -> None:
        """Запускает непрерывный фоновый цикл создания бэкапов."""
        if not self.enabled:
            return
        self._is_running = True
        log("RuntimeBackupManager started.", level="INFO")
        while self._is_running:
            try:
                now = time.time()
                time_since_last = now - self._last_backup_time

                # Выполняем бэкап, если есть изменения и выдержан дебаунс или макс. интервал
                if self._needs_backup and (
                    time_since_last >= self.debounce_sec or time_since_last >= self.max_interval_sec
                ):
                    await self._create_and_send_backup()
                    self._needs_backup = False
                    self._last_backup_time = time.time()
            except Exception as e:
                self._last_error = str(e)
                log(f"[BACKUP] Error in backup loop: {e}", level="ERROR")
            await asyncio.sleep(1)

    async def _create_and_send_backup(self) -> None:
        """Архивирует state.json и отправляет через подключенный Telegram-бот."""
        state_file = DATA_DIR / "state.json"
        if not state_file.exists():
            return

        date_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        zip_filename = DATA_DIR / f"state_backup_{date_str}.zip"

        try:
            with zipfile.ZipFile(zip_filename, "w", zipfile.ZIP_DEFLATED) as zipf:
                zipf.write(state_file, arcname="state.json")

            if not self.verify_zip_integrity(zip_filename):
                log(f"[BACKUP] Поврежденный архив {zip_filename.name}, отмена отправки.", level="ERROR")
                return

            caption = (
                f"💾 Runtime Backup\n\n"
                f"Свежий слепок data/state.json\n"
                f"Размер: {zip_filename.stat().st_size} байт\n"
                f"Время: {date_str}"
            )
            tg_bot = getattr(self.notifier, "tg_bot", None)
            if tg_bot:
                file_obj = FSInputFile(path=str(zip_filename))
                if hasattr(tg_bot, "send_backup_document"):
                    await tg_bot.send_backup_document(file_obj, caption)
                elif hasattr(tg_bot, "send_document_to_all"):
                    await tg_bot.send_document_to_all(file_obj, caption)
                self._total_backups_sent += 1
                self._last_backup_filename = zip_filename.name
                log(f"[BACKUP] Sent backup {zip_filename.name} to Telegram.", level="INFO")
            else:
                log("[BACKUP] No TG bot available to send backup.", level="WARNING")
        except Exception as e:
            self._last_error = str(e)
            log(f"[BACKUP] Creation/send failed: {e}", level="ERROR")
        finally:
            if zip_filename.exists():
                try:
                    os.remove(zip_filename)
                except Exception as ex:
                    log(f"[BACKUP] Не удалось удалить временный архив {zip_filename.name}: {ex}", level="WARNING")

    def stop(self) -> None:
        """Останавливает фоновый цикл менеджера бэкапов."""
        self._is_running = False
        log("RuntimeBackupManager stopped.", level="INFO")
