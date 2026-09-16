# ============================================================
# FILE: TG/keyboards.py
# ROLE: Telegram UI keyboard markup builder
# ============================================================

from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)


class TGKeyboards:
    """Генератор клавиатур для Telegram-бота управления ядром TrendH."""

    @staticmethod
    def main_menu(is_paused: bool = True) -> ReplyKeyboardMarkup:
        """Главное меню управления ботом."""
        keyboard = [
            [KeyboardButton(text="▶️ Start"), KeyboardButton(text="ℹ️ Status"), KeyboardButton(text="⏸️ Stop")],
            [KeyboardButton(text="📊 Analytics"), KeyboardButton(text="📜 Logs")],
            [KeyboardButton(text="⚙️ Settings"), KeyboardButton(text="🚨 Close All")]
        ]
        return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

    @staticmethod
    def confirm_start() -> ReplyKeyboardMarkup:
        """Клавиатура подтверждения запуска торгового цикла."""
        keyboard = [
            [KeyboardButton(text="✅ Confirm Start")],
            [KeyboardButton(text="🔙 Back")]
        ]
        return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

    @staticmethod
    def back_reply() -> ReplyKeyboardMarkup:
        """Универсальная кнопка возврата в текстовом меню."""
        keyboard = [[KeyboardButton(text="🔙 Back")]]
        return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

    @staticmethod
    def confirm_close_all() -> InlineKeyboardMarkup:
        """Подтверждение экстренного закрытия всех виртуальных позиций."""
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚠️ Да, закрыть все позиции", callback_data="close_all_confirm")],
            [InlineKeyboardButton(text="🔙 Отмена", callback_data="close_all_cancel")]
        ])

    @staticmethod
    def analytics_menu() -> InlineKeyboardMarkup:
        """Меню аналитики торговой активности."""
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📈 Equity Curve", callback_data="analytics_equity"),
                InlineKeyboardButton(text="📄 Trades Ledger", callback_data="analytics_ledger")
            ],
            [
                InlineKeyboardButton(text="🏆 Ranking", callback_data="analytics_ranking_profit"),
                InlineKeyboardButton(text="ℹ️ Metrics Help", callback_data="analytics_help")
            ],
            [
                InlineKeyboardButton(text="💰 Set Balance", callback_data="analytics_set_balance"),
                InlineKeyboardButton(text="🔄 Reset Analytics", callback_data="analytics_reset")
            ]
        ])

    @staticmethod
    def analytics_ranking_menu() -> InlineKeyboardMarkup:
        """Фильтры ранжирования монет."""
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="💵 By Profit", callback_data="analytics_ranking_profit"),
                InlineKeyboardButton(text="📊 By Trades", callback_data="analytics_ranking_trades"),
                InlineKeyboardButton(text="🎯 By Winrate", callback_data="analytics_ranking_winrate")
            ],
            [
                InlineKeyboardButton(text="🔙 Back to Analytics", callback_data="analytics_back")
            ]
        ])

    @staticmethod
    def confirm_reset_analytics() -> InlineKeyboardMarkup:
        """Подтверждение сброса аналитики."""
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚠️ Да, сбросить аналитику", callback_data="reset_analytics_confirm")],
            [InlineKeyboardButton(text="🔙 Отмена", callback_data="analytics_back")]
        ])

    @staticmethod
    def settings_menu() -> InlineKeyboardMarkup:
        """Меню настроек стратегии и монет."""
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Strategy Rules", callback_data="settings_rules"),
                InlineKeyboardButton(text="🪙 Active Coins", callback_data="settings_coins")
            ],
            [
                InlineKeyboardButton(text="🔀 Direction Mode", callback_data="settings_direction_mode")
            ]
        ])

    @staticmethod
    def direction_mode_menu(current_mode: str) -> InlineKeyboardMarkup:
        """Выбор режима направления торговли."""
        modes = ["HEDGE", "MONO", "LONG", "SHORT"]
        buttons = []
        for m in modes:
            prefix = "✅ " if m == current_mode else ""
            buttons.append(InlineKeyboardButton(text=f"{prefix}{m}", callback_data=f"set_dir_{m}"))

        return InlineKeyboardMarkup(inline_keyboard=[
            [buttons[0], buttons[1]],
            [buttons[2], buttons[3]],
            [InlineKeyboardButton(text="🔙 Back to Settings", callback_data="settings_back")]
        ])

    @staticmethod
    def logs_menu() -> InlineKeyboardMarkup:
        """Меню скачивания логов и конфига."""
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📜 Get Logs", callback_data="logs_get_logs")],
            [InlineKeyboardButton(text="📂 Get Config", callback_data="logs_get_cfg")],
            [InlineKeyboardButton(text="💾 Get State Backup", callback_data="logs_get_state")]
        ])
