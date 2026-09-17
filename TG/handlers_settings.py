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
            f"• Индикаторы: <b>Trend (5m) + Trend HTF (1h) + RSI (14)</b>\n"
            f"• Выход: <b>Trend Reversal / TP Ratio / Stop Loss</b>\n\n"
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
            f"• Индикаторы: <b>Trend (5m) + Trend HTF (1h) + RSI (14)</b>\n\n"
            f"Выберите категорию для просмотра или изменения:"
        )
        await callback.message.edit_text(text, reply_markup=TGKeyboards.settings_menu(), parse_mode="HTML")

    @router.callback_query(F.data == "settings_rules")
    async def on_settings_rules(callback: CallbackQuery):
        await callback.answer()
        trend_cfg = ENTER_RULES.get("trend", {})
        trend_htf_cfg = ENTER_RULES.get("trend_htf", {})
        rsi_cfg = ENTER_RULES.get("rsi", {})
        rsi_wl_cfg = ENTER_RULES.get("rsi_waterline50", {})
        sr_cfg = ENTER_RULES.get("sr_levels", {})
        ec_cfg = ENTER_RULES.get("ema_cross", {})
        vol_cfg = ENTER_RULES.get("vol_filter", {})
        exit_rev = EXIT_RULES.get("trend_reversal", {})
        exit_tp = EXIT_RULES.get("take_profit_ratio", {})
        exit_sl = EXIT_RULES.get("stop_loss_ratio", {})
        slip_base = PAPER_TRADING_CFG.get("slippage_base_ratio", PAPER_TRADING_CFG.get("slippage_base_pct", 0.0005))
        fee_ratio = ANALYTICS_CFG.get("taker_fee_ratio", 0.0006)

        htf_info = ""
        if trend_htf_cfg.get("is_active", False):
            htf_info = (
                f"• <b>Trend HTF ({trend_htf_cfg.get('timeframe', '1h')})</b>: "
                f"Fast={trend_htf_cfg.get('sma_fast', 10)}, Slow={trend_htf_cfg.get('sma_slow', 30)}, "
                f"Подтверждение={trend_htf_cfg.get('confirmation_candles', 2)}\n"
            )

        wl_info = ""
        if rsi_wl_cfg.get("is_active", False):
            wl_info = (
                f"• <b>RSI Waterline ({rsi_wl_cfg.get('timeframe', '5m')})</b>: "
                f"Waterline={rsi_wl_cfg.get('waterline', 50.0)}, Long={rsi_wl_cfg.get('long_cond')}, Short={rsi_wl_cfg.get('short_cond')}\n"
            )

        sr_info = ""
        if sr_cfg.get("is_active", False):
            sr_info = (
                f"• <b>SR Levels ({sr_cfg.get('timeframe', '5m')})</b>: "
                f"Swing={sr_cfg.get('swing_len', 15)}, Window={sr_cfg.get('window', 300)}, "
                f"Margin={sr_cfg.get('margin', 2.0)}, Mode={sr_cfg.get('level_mode', 'latest')}\n"
            )

        ec_info = ""
        if ec_cfg.get("is_active", False):
            ec_info = (
                f"• <b>EMA Cross ({ec_cfg.get('timeframe', '5m')})</b>: "
                f"Period1={ec_cfg.get('period1', 9)}, Period2={ec_cfg.get('period2', 21)}, "
                f"Long={ec_cfg.get('long_cond')}, Short={ec_cfg.get('short_cond')}\n"
            )

        vol_info = ""
        if vol_cfg.get("is_active", False):
            mode = vol_cfg.get("mode", "a")
            sf = vol_cfg.get(mode, {}).get("slice_factor", 1.0)
            vol_info = (
                f"• <b>Volume Filter ({vol_cfg.get('timeframe', '1m')})</b>: "
                f"Mode={mode.upper()}, Period={vol_cfg.get('period', 14)}, SliceFactor={sf}\n"
            )

        tp_val = exit_tp.get("value")
        tp_str = f"{tp_val * 100:.1f}% ({tp_val})" if tp_val is not None else "Отключен (null)"
        sl_val = exit_sl.get("value")
        sl_str = f"{sl_val * 100:.1f}% ({sl_val})" if sl_val is not None else "Отключен (null)"

        rules_text = (
            f"<b>📊 Правила торговой стратегии:</b>\n\n"
            f"<b>Вход (Enter Rules):</b>\n"
            f"• <b>Trend ({trend_cfg.get('timeframe', '5m')})</b>: "
            f"Fast={trend_cfg.get('sma_fast', 10)}, Slow={trend_cfg.get('sma_slow', 30)}, "
            f"Подтверждение={trend_cfg.get('confirmation_candles', 2)}\n"
            f"{htf_info}"
            f"• <b>RSI ({rsi_cfg.get('timeframe', '5m')})</b>: "
            f"Window={rsi_cfg.get('window', 14)}, Conds={rsi_cfg.get('conditions', {})}\n"
            f"{wl_info}"
            f"{sr_info}"
            f"{ec_info}"
            f"{vol_info}\n"
            f"<b>Выход (Exit Rules):</b>\n"
            f"• <b>Trend Reversal</b>: Long={exit_rev.get('long_exit_trends')}, Short={exit_rev.get('short_exit_trends')}\n"
            f"• <b>Take Profit</b>: {tp_str}\n"
            f"• <b>Stop Loss</b>: {sl_str}\n\n"
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
