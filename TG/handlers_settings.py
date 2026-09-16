# ============================================================
# FILE: TG/handlers_settings.py
# ROLE: Telegram settings handlers (Strategy parameters, Coins, Direction Mode)
# ============================================================

import json
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from consts import (
    CFG_PATH,
    cfg,
    ENTER_RULES,
    EXIT_RULES,
    DIRECTION_MODE,
    ANALYTICS_CFG,
    PAPER_TRADING_CFG
)
from cron_integration import CronIntegration
from TG.keyboards import TGKeyboards

settings_router = Router(name="settings_router")


def _save_cfg_key(key: str, value):
    """Сохраняет измененный ключ конфигурации в cfg.json и оперативную память."""
    try:
        with open(CFG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        data[key] = value
        with open(CFG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        cfg[key] = value
    except Exception as e:
        pass


def setup_settings_handlers(router: Router, bot_core):
    """Регистрирует обработчики меню настроек бота."""

    @router.message(F.text == "⚙️ Settings")
    async def on_settings_menu(message: Message, state: FSMContext):
        await state.clear()
        cur_mode = cfg.get("DIRECTION_MODE", "HEDGE")
        symbols = CronIntegration.get_symbols()

        text = (
            f"<b>⚙️ Параметры и настройки бота (TrendH):</b>\n\n"
            f"• Режим торговли (Direction): <b>{cur_mode}</b>\n"
            f"• Монет в пуле: <b>{len(symbols)}</b>\n"
            f"• Индикаторы: <b>Trend (SMA 10/30) + RSI (14)</b>\n"
            f"• Выход: <b>Trend Reversal / TP Ratio</b>\n\n"
            f"Выберите категорию для просмотра или изменения:"
        )
        await message.answer(text, reply_markup=TGKeyboards.settings_menu(), parse_mode="HTML")

    @router.callback_query(F.data == "settings_back")
    async def on_settings_back(callback: CallbackQuery):
        await callback.answer()
        cur_mode = cfg.get("DIRECTION_MODE", "HEDGE")
        symbols = CronIntegration.get_symbols()

        text = (
            f"<b>⚙️ Параметры и настройки бота (TrendH):</b>\n\n"
            f"• Режим торговли (Direction): <b>{cur_mode}</b>\n"
            f"• Монет в пуле: <b>{len(symbols)}</b>\n"
            f"• Индикаторы: <b>Trend (SMA 10/30) + RSI (14)</b>\n\n"
            f"Выберите категорию для просмотра или изменения:"
        )
        await callback.message.edit_text(text, reply_markup=TGKeyboards.settings_menu(), parse_mode="HTML")

    @router.callback_query(F.data == "settings_rules")
    async def on_settings_rules(callback: CallbackQuery):
        await callback.answer()
        trend_cfg = ENTER_RULES.get("trend", {})
        rsi_cfg = ENTER_RULES.get("rsi", {})
        exit_rev = EXIT_RULES.get("trend_reversal", {})
        exit_tp = EXIT_RULES.get("take_profit_ratio", {})
        slip_base = PAPER_TRADING_CFG.get("slippage_base_ratio", 0.001)
        fee_ratio = ANALYTICS_CFG.get("taker_fee_ratio", 0.0006)

        rules_text = (
            f"<b>📊 Правила торговой стратегии:</b>\n\n"
            f"<b>Вход (Enter Rules):</b>\n"
            f"• <b>Trend ({trend_cfg.get('timeframe', '5m')})</b>: "
            f"SMA Fast={trend_cfg.get('sma_fast', 10)}, Slow={trend_cfg.get('sma_slow', 30)}, "
            f"Свечей подтверждения={trend_cfg.get('confirmation_candles', 5)}\n"
            f"• <b>RSI ({rsi_cfg.get('timeframe', '5m')})</b>: "
            f"Window={rsi_cfg.get('window', 14)}, Long='{rsi_cfg.get('long_cond')}', Short='{rsi_cfg.get('short_cond')}'\n\n"
            f"<b>Выход (Exit Rules):</b>\n"
            f"• <b>Trend Reversal</b>: Long выходы: {exit_rev.get('long_exit_trends')}, Short выходы: {exit_rev.get('short_exit_trends')}\n"
            f"• <b>Take Profit Ratio</b>: {exit_tp.get('value', 'null')}\n\n"
            f"<b>Исполнение (Paper Trading):</b>\n"
            f"• Базовый слиппедж (ratio): <code>{slip_base}</code> ({slip_base * 100:.2f}%)\n"
            f"• Комиссия тейкера (ratio): <code>{fee_ratio}</code> ({fee_ratio * 100:.2f}%)"
        )
        await callback.message.edit_text(rules_text, reply_markup=TGKeyboards.settings_menu(), parse_mode="HTML")

    @router.callback_query(F.data == "settings_coins")
    async def on_settings_coins(callback: CallbackQuery):
        await callback.answer()
        symbols = CronIntegration.get_symbols()
        if not symbols:
            await callback.message.edit_text(
                "🪙 <b>Список активных монет пуст.</b>\nПроверьте путь data_sources в cfg.json.",
                reply_markup=TGKeyboards.settings_menu(),
                parse_mode="HTML"
            )
            return

        lines = [f"<b>🪙 Активные монеты пула ({len(symbols)}):</b>\n"]
        for sym in symbols[:20]:
            st = CronIntegration.get_symbol_state(sym)
            long_info = f"L: {st['LONG']['invest_size']}$" if st['LONG']['enabled'] else "L: ❌"
            short_info = f"S: {st['SHORT']['invest_size']}$" if st['SHORT']['enabled'] else "S: ❌"
            lines.append(f"• <b>{sym}</b>: [{long_info} | {short_info}]")

        if len(symbols) > 20:
            lines.append(f"\n<i>...и еще {len(symbols) - 20} монет</i>")

        await callback.message.edit_text("\n".join(lines), reply_markup=TGKeyboards.settings_menu(), parse_mode="HTML")

    @router.callback_query(F.data == "settings_direction_mode")
    async def on_settings_direction_mode(callback: CallbackQuery):
        await callback.answer()
        cur_mode = cfg.get("DIRECTION_MODE", "HEDGE")
        text = (
            f"<b>🔀 Режим направления позиций (DIRECTION_MODE):</b>\n\n"
            f"Текущий режим: <b>{cur_mode}</b>\n\n"
            f"• <b>HEDGE</b> — разрешены одновременные позиции LONG и SHORT.\n"
            f"• <b>MONO</b> — только одна активная позиция (LONG либо SHORT).\n"
            f"• <b>LONG</b> — разрешены только покупки (LONG).\n"
            f"• <b>SHORT</b> — разрешены только продажи (SHORT)."
        )
        await callback.message.edit_text(text, reply_markup=TGKeyboards.direction_mode_menu(cur_mode), parse_mode="HTML")

    @router.callback_query(F.data.startswith("set_dir_"))
    async def on_set_direction_mode(callback: CallbackQuery):
        new_mode = callback.data.replace("set_dir_", "")
        await callback.answer(f"Режим переключен на {new_mode}")
        _save_cfg_key("DIRECTION_MODE", new_mode)
        if hasattr(bot_core, "direction_mode"):
            bot_core.direction_mode = new_mode

        text = f"✅ <b>Режим торговли успешно изменен на: {new_mode}</b>"
        await callback.message.edit_text(text, reply_markup=TGKeyboards.direction_mode_menu(new_mode), parse_mode="HTML")
