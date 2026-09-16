# ============================================================
# FILE: TG/keyboards.py
# ROLE: Telegram UI keyboard markup builder
# ============================================================

from typing import List, Optional, Any
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
        """Подтверждение экстренного закрытия всех виртуальных позиций во всех вселенных."""
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚠️ Да, закрыть все позиции", callback_data="close_all_confirm")],
            [InlineKeyboardButton(text="🔙 Отмена", callback_data="close_all_cancel")]
        ])

    @staticmethod
    def analytics_menu(selected_uid: str = "u1", universes: Optional[List[Any]] = None) -> InlineKeyboardMarkup:
        """
        Меню аналитики торговой активности с селектором вселенных и кнопкой Leaderboard.
        Позволяет переключать вид между параллельными стратегиями.
        """
        univ_rows = []
        if universes:
            row = []
            for idx, u in enumerate(universes, 1):
                uid = u.universe_id if hasattr(u, "universe_id") else (u.get("universe_id", f"u{idx}") if isinstance(u, dict) else f"u{idx}")
                prefix = "🔘 " if uid == selected_uid else ""
                short_label = f"{prefix}У{idx}"
                row.append(InlineKeyboardButton(text=short_label, callback_data=f"analytics_univ_{uid}"))
                if len(row) == 5:
                    univ_rows.append(row)
                    row = []
            if row:
                univ_rows.append(row)

        menu_rows = [
            [
                InlineKeyboardButton(text="🏆 Leaderboard (Все)", callback_data="analytics_leaderboard"),
                InlineKeyboardButton(text="📈 Equity Curve", callback_data=f"analytics_equity_{selected_uid}"),
            ],
            [
                InlineKeyboardButton(text="📄 Trades Ledger", callback_data=f"analytics_ledger_{selected_uid}"),
                InlineKeyboardButton(text="🪙 Coin Ranking", callback_data=f"analytics_ranking_{selected_uid}_profit"),
            ],
            [
                InlineKeyboardButton(text="💰 Set Balance", callback_data=f"analytics_set_balance_{selected_uid}"),
                InlineKeyboardButton(text="🔄 Reset", callback_data=f"analytics_reset_{selected_uid}"),
                InlineKeyboardButton(text="ℹ️ Help", callback_data="analytics_help"),
            ]
        ]
        return InlineKeyboardMarkup(inline_keyboard=univ_rows + menu_rows)

    @staticmethod
    def leaderboard_menu() -> InlineKeyboardMarkup:
        """Клавиатура таблицы лидеров параллельных вселенных."""
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить Leaderboard", callback_data="analytics_leaderboard")],
            [InlineKeyboardButton(text="🔙 Назад в Аналитику", callback_data="analytics_back")]
        ])

    @staticmethod
    def analytics_ranking_menu(selected_uid: str = "u1") -> InlineKeyboardMarkup:
        """Фильтры ранжирования монет по PnL, сделкам и винрейту."""
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="💵 By Profit", callback_data=f"analytics_ranking_{selected_uid}_profit"),
                InlineKeyboardButton(text="📊 By Trades", callback_data=f"analytics_ranking_{selected_uid}_trades"),
                InlineKeyboardButton(text="🎯 By Winrate", callback_data=f"analytics_ranking_{selected_uid}_winrate")
            ],
            [
                InlineKeyboardButton(text="🔙 Back to Analytics", callback_data=f"analytics_univ_{selected_uid}")
            ]
        ])

    @staticmethod
    def confirm_reset_analytics(selected_uid: str = "u1") -> InlineKeyboardMarkup:
        """Подтверждение сброса аналитики выбранной вселенной."""
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚠️ Да, сбросить аналитику", callback_data=f"reset_analytics_confirm_{selected_uid}")],
            [InlineKeyboardButton(text="🔙 Отмена", callback_data=f"analytics_univ_{selected_uid}")]
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
        """Выбор режима направления торговли (HEDGE, MONO, LONG, SHORT)."""
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
        """Меню скачивания логов, конфига и архива бэкапа состояния."""
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📜 Get Logs", callback_data="logs_get_logs")],
            [InlineKeyboardButton(text="📂 Get Config", callback_data="logs_get_cfg")],
            [InlineKeyboardButton(text="💾 Get State Backup", callback_data="logs_get_state")]
        ])
