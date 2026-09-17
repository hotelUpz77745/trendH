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
    def analytics_menu(selected_uid: str = "u15", universes: Optional[List[Any]] = None) -> InlineKeyboardMarkup:
        """
        Меню аналитики торговой активности для выбранной стратегии.
        Включает кнопку быстрого выбора стратегии и действия по выбранной стратегии.
        """
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text=f"🎯 Стратегия: [{selected_uid.upper()}] (Сменить)", callback_data=f"analytics_select_strat:{selected_uid}")
            ],
            [
                InlineKeyboardButton(text="🏆 Leaderboard (Все)", callback_data="analytics_leaderboard"),
                InlineKeyboardButton(text="📈 Equity Curve", callback_data=f"analytics_equity:{selected_uid}"),
            ],
            [
                InlineKeyboardButton(text="📄 Trades Ledger", callback_data=f"analytics_ledger:{selected_uid}"),
                InlineKeyboardButton(text="🪙 Coin Ranking", callback_data=f"analytics_ranking:{selected_uid}:profit"),
            ],
            [
                InlineKeyboardButton(text="💰 Set Balance", callback_data=f"analytics_set_balance_{selected_uid}"),
                InlineKeyboardButton(text="🗑 Сброс", callback_data=f"analytics_reset:{selected_uid}"),
                InlineKeyboardButton(text="ℹ️ Help", callback_data="analytics_help"),
            ]
        ])

    @staticmethod
    def strategy_select_menu(universes: List[Any], selected_uid: str = "u15") -> InlineKeyboardMarkup:
        """Клавиатура выбора стратегии из списка, упорядоченного по результативности."""
        buttons = []
        row = []
        for idx, u in enumerate(universes, 1):
            uid = u["uid"] if isinstance(u, dict) else (getattr(u, "universe_id", None) or getattr(u, "uid", str(u)))
            is_active = (uid == selected_uid)
            prefix = "🔘 " if is_active else ""
            medal = "🥇" if idx == 1 else ("🥈" if idx == 2 else ("🥉" if idx == 3 else f"{idx}."))
            is_skip = uid.endswith("_skip") or "skip" in uid.lower()
            skip_badge = " ⚡" if is_skip else ""
            label = f"{prefix}{medal} {uid.upper()}{skip_badge}"
            row.append(InlineKeyboardButton(text=label, callback_data=f"analytics_univ_{uid}"))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        buttons.append([InlineKeyboardButton(text="🔙 Назад в Аналитику", callback_data=f"analytics_univ_{selected_uid}")])
        return InlineKeyboardMarkup(inline_keyboard=buttons)

    @staticmethod
    def leaderboard_menu() -> InlineKeyboardMarkup:
        """Клавиатура таблицы лидеров параллельных вселенных."""
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить Leaderboard", callback_data="analytics_leaderboard")],
            [InlineKeyboardButton(text="🔙 Назад в Аналитику", callback_data="analytics_back")]
        ])

    @staticmethod
    def analytics_ranking_menu(selected_uid: str = "u15") -> InlineKeyboardMarkup:
        """Фильтры ранжирования монет по PnL, сделкам и винрейту."""
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="💵 By Profit", callback_data=f"analytics_ranking:{selected_uid}:profit"),
                InlineKeyboardButton(text="📊 By Trades", callback_data=f"analytics_ranking:{selected_uid}:trades"),
                InlineKeyboardButton(text="🎯 By Winrate", callback_data=f"analytics_ranking:{selected_uid}:winrate")
            ],
            [
                InlineKeyboardButton(text=f"🎯 Сменить стратегию [{selected_uid.upper()}]", callback_data=f"analytics_select_strat:{selected_uid}"),
                InlineKeyboardButton(text="🔙 Back to Analytics", callback_data=f"analytics_univ_{selected_uid}")
            ]
        ])

    @staticmethod
    def confirm_reset_analytics(selected_uid: str = "u15") -> InlineKeyboardMarkup:
        """Безопасное окно подтверждения сброса аналитики: Отмена наверху, PIN внизу."""
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 ❌ Отмена (Сохранить данные)", callback_data=f"analytics_univ_{selected_uid}")],
            [InlineKeyboardButton(text="🔐 Запросить защитный PIN-код", callback_data=f"reset_req_pin:{selected_uid}")]
        ])

    @staticmethod
    def confirm_reset_pin_menu(selected_uid: str, correct_pin: int, pin_options: List[int]) -> InlineKeyboardMarkup:
        """Клавиатура подтверждения с выбором защитного PIN-кода среди случайных вариантов."""
        pin_buttons = []
        for pin in pin_options:
            if pin == correct_pin:
                pin_buttons.append(InlineKeyboardButton(text=f"[{pin}]", callback_data=f"reset_pin_ok:{selected_uid}:{pin}"))
            else:
                pin_buttons.append(InlineKeyboardButton(text=f"[{pin}]", callback_data=f"reset_pin_fail:{selected_uid}"))
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 ❌ Отмена", callback_data=f"analytics_univ_{selected_uid}")],
            pin_buttons
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
