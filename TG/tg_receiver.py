# ============================================================
# FILE: TG/tg_receiver.py
# ROLE: Telegram bot receiver orchestrator for TrendH_Papper
# ============================================================

import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, CallbackQuery, ErrorEvent

from c_log import UnifiedLogger
from consts import TG_TOKEN, TG_ALLOWED_USERS
from TG.handlers_control import control_router, setup_control_handlers
from TG.handlers_analytics import analytics_router, setup_analytics_handlers
from TG.handlers_settings import settings_router, setup_settings_handlers

logger = UnifiedLogger("TGReceiver")


class TelegramReceiver:
    """Оркестратор Telegram-бота управления ядром TrendH."""

    def __init__(self, bot_core, token: str = None):
        self.bot_core = bot_core
        self._is_running = False
        self.token = token or TG_TOKEN

        if not self.token:
            logger.warning("TG_TOKEN не задан в .env. TelegramReceiver инициализирован в неактивном режиме.")
            self.bot = None
            self.dp = None
            return

        self.bot = Bot(token=self.token)
        self.dp = Dispatcher(storage=MemoryStorage())

        self._setup_middleware()
        self._setup_error_handling()
        self._register_subrouters()

    def _setup_middleware(self):
        """Регистрация middleware авторизации пользователей по белому списку."""
        @self.dp.message.outer_middleware()
        async def auth_message_middleware(handler, event: Message, data: dict):
            user_id = event.from_user.id if event.from_user else None
            if TG_ALLOWED_USERS and user_id not in TG_ALLOWED_USERS:
                logger.warning(f"[TG Auth] Неавторизованный доступ (message) от ID: {user_id}")
                await event.answer("⛔ <b>Доступ запрещен.</b> Обратитесь к администратору.", parse_mode="HTML")
                return
            return await handler(event, data)

        @self.dp.callback_query.outer_middleware()
        async def auth_callback_middleware(handler, event: CallbackQuery, data: dict):
            user_id = event.from_user.id if event.from_user else None
            if TG_ALLOWED_USERS and user_id not in TG_ALLOWED_USERS:
                logger.warning(f"[TG Auth] Неавторизованный доступ (callback) от ID: {user_id}")
                await event.answer("⛔ Доступ запрещен.", show_alert=True)
                return
            return await handler(event, data)

    def _setup_error_handling(self):
        """Глобальный обработчик ошибок Telegram-бота."""
        @self.dp.errors()
        async def error_handler(event: ErrorEvent):
            logger.error(f"[TG Error] Необработанное исключение: {event.exception}")
            try:
                if event.update.message:
                    await event.update.message.answer("❌ Произошла внутренняя ошибка при обработке команды.")
                elif event.update.callback_query:
                    await event.update.callback_query.answer("❌ Внутренняя ошибка.", show_alert=True)
            except Exception:
                pass
            return True

    def _register_subrouters(self):
        """Подключение модульных роутеров команд, аналитики и настроек."""
        setup_control_handlers(control_router, self.bot_core)
        setup_analytics_handlers(analytics_router, self.bot_core)
        setup_settings_handlers(settings_router, self.bot_core)

        self.dp.include_router(control_router)
        self.dp.include_router(analytics_router)
        self.dp.include_router(settings_router)

    async def start(self):
        """Запуск long-polling прослушивания Telegram."""
        if not TG_TOKEN:
            logger.warning("TG_TOKEN не задан. TelegramReceiver не будет запущен.")
            return

        logger.info("Запуск Telegram Receiver...")
        self._is_running = True
        try:
            await self.dp.start_polling(self.bot)
        except asyncio.CancelledError:
            logger.info("Telegram Receiver остановлен по CancelledError.")
        finally:
            await self.stop()

    async def stop(self):
        """Корректное завершение сессии бота."""
        if self._is_running:
            self._is_running = False
            logger.info("Остановка сессии Telegram бота...")
            try:
                await self.bot.session.close()
            except Exception as e:
                logger.warning(f"Ошибка при закрытии сессии бота: {e}")
