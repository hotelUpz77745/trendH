# ============================================================
# FILE: TG/handlers_control.py
# ROLE: Telegram control handlers (Start, Stop, Status, Close All, Logs)
# ============================================================

import os
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from c_log import log
from consts import CFG_PATH, BASE_DIR, DATA_DIR
from cron_integration import CronIntegration
from TG.keyboards import TGKeyboards
from utils import Utils

control_router = Router(name="control_router")


def setup_control_handlers(router: Router, bot_core):
    """Регистрирует обработчики управления жизненным циклом и командами ядра."""

    @router.message(Command("start"))
    async def on_cmd_start(message: Message, state: FSMContext):
        await state.clear()
        status_str = "⏸️ Paused" if getattr(bot_core, "is_paused", True) else "▶️ Running"
        welcome_text = (
            f"<b>🤖 TrendH Paper Trading Bot</b>\n\n"
            f"Статус системы: <b>{status_str}</b>\n"
            f"Используйте кнопки меню ниже для управления."
        )
        is_paused = getattr(bot_core, "is_paused", True)
        await message.answer(welcome_text, reply_markup=TGKeyboards.main_menu(is_paused), parse_mode="HTML")

    @router.message(F.text == "▶️ Start")
    async def on_pre_start(message: Message, state: FSMContext):
        await state.clear()
        if not getattr(bot_core, "is_paused", True):
            await message.answer("⚠️ Торговля уже активна (Running)!", reply_markup=TGKeyboards.main_menu(False))
            return

        symbols = CronIntegration.get_symbols()
        total_syms = len(symbols)
        coins_preview = ", ".join(symbols[:12]) + ("..." if total_syms > 12 else "") if symbols else "Нет монет"

        info_text = (
            f"<b>Подготовка к запуску:</b>\n\n"
            f"• Отслеживаемых монет: <b>{total_syms}</b>\n"
            f"• Монеты: <code>{coins_preview}</code>\n\n"
            f"Подтвердите запуск торговли:"
        )
        await message.answer(info_text, reply_markup=TGKeyboards.confirm_start(), parse_mode="HTML")

    @router.message(F.text == "✅ Confirm Start")
    async def on_confirm_start(message: Message, state: FSMContext):
        await state.clear()
        if hasattr(bot_core, "set_paused"):
            bot_core.set_paused(False)
        else:
            bot_core.is_paused = False

        log("[TG] Торговый цикл активирован оператором через Telegram.", level="INFO")
        await message.answer("✅ <b>Торговый цикл успешно запущен!</b>", reply_markup=TGKeyboards.main_menu(False), parse_mode="HTML")

    @router.message(F.text == "⏸️ Stop")
    async def on_stop(message: Message, state: FSMContext):
        await state.clear()
        if getattr(bot_core, "is_paused", True):
            await message.answer("ℹ️ Торговля уже приостановлена!", reply_markup=TGKeyboards.main_menu(True))
            return

        if hasattr(bot_core, "set_paused"):
            bot_core.set_paused(True)
        else:
            bot_core.is_paused = True

        log("[TG] Торговый цикл приостановлен оператором через Telegram.", level="INFO")
        await message.answer("⏸️ <b>Торговля приостановлена!</b> (Новые входы заблокированы)", reply_markup=TGKeyboards.main_menu(True), parse_mode="HTML")

    @router.message(F.text == "🔙 Back")
    async def on_back(message: Message, state: FSMContext):
        await state.clear()
        is_paused = getattr(bot_core, "is_paused", True)
        await message.answer("Главное меню:", reply_markup=TGKeyboards.main_menu(is_paused))

    @router.message(F.text == "ℹ️ Status")
    async def on_status(message: Message, state: FSMContext):
        await state.clear()
        is_paused = getattr(bot_core, "is_paused", True)
        status_text = "⏸️ Paused" if is_paused else "▶️ Running"

        direction_mode = getattr(bot_core, "direction_mode", "HEDGE")
        symbols_count = len(getattr(bot_core, "symbols", []))

        # Сбор информации об открытых позициях со всех параллельных вселенных
        open_positions = []
        if hasattr(bot_core, "universe_manager") and bot_core.universe_manager:
            for uid, univ in bot_core.universe_manager.universes.items():
                positions = getattr(univ.state, "positions", {})
                for sym, sides in positions.items():
                    for side, pos_info in sides.items():
                        is_act = getattr(pos_info, "is_active", False) if hasattr(pos_info, "is_active") else (pos_info.get("is_active", False) if isinstance(pos_info, dict) else False)
                        if not is_act:
                            continue
                        open_price = getattr(pos_info, "open_price", 0.0) if hasattr(pos_info, "open_price") else float(pos_info.get("open_price", 0.0) if isinstance(pos_info, dict) else 0.0)
                        size_usd = getattr(pos_info, "size", 0.0) if hasattr(pos_info, "size") else float(pos_info.get("size", 0.0) if isinstance(pos_info, dict) else 0.0)
                        cur_price = getattr(bot_core, "current_prices", {}).get(sym, open_price)
                        
                        if open_price > 0:
                            pnl_ratio = (cur_price - open_price) / open_price if side == "LONG" else (open_price - cur_price) / open_price
                            pnl_usd = pnl_ratio * size_usd
                            pnl_pct = pnl_ratio * 100
                        else:
                            pnl_usd, pnl_pct = 0.0, 0.0

                        pnl_icon = "🟢" if pnl_usd >= 0 else "🔴"
                        open_positions.append(
                            f"  {pnl_icon} [<b>{uid}</b>] <b>{sym}</b> {side}: {size_usd:.1f}$ (Вход: {open_price:.4f} → {cur_price:.4f} | {pnl_pct:+.2f}% / {pnl_usd:+.2f}$)"
                        )
        else:
            positions = getattr(bot_core.state, "positions", {}) if hasattr(bot_core, "state") else {}
            for sym, sides in positions.items():
                for side, pos_info in sides.items():
                    is_act = getattr(pos_info, "is_active", False) if hasattr(pos_info, "is_active") else (pos_info.get("is_active", False) if isinstance(pos_info, dict) else False)
                    if not is_act:
                        continue
                    open_price = getattr(pos_info, "open_price", 0.0) if hasattr(pos_info, "open_price") else float(pos_info.get("open_price", 0.0) if isinstance(pos_info, dict) else 0.0)
                    size_usd = getattr(pos_info, "size", 0.0) if hasattr(pos_info, "size") else float(pos_info.get("size", 0.0) if isinstance(pos_info, dict) else 0.0)
                    cur_price = getattr(bot_core, "current_prices", {}).get(sym, open_price)
                    if open_price > 0:
                        pnl_ratio = (cur_price - open_price) / open_price if side == "LONG" else (open_price - cur_price) / open_price
                        pnl_usd = pnl_ratio * size_usd
                        pnl_pct = pnl_ratio * 100
                    else:
                        pnl_usd, pnl_pct = 0.0, 0.0
                    pnl_icon = "🟢" if pnl_usd >= 0 else "🔴"
                    open_positions.append(
                        f"  {pnl_icon} <b>{sym}</b> {side}: {size_usd:.1f}$ (Вход: {open_price:.4f} → {cur_price:.4f} | {pnl_pct:+.2f}% / {pnl_usd:+.2f}$)"
                    )

        pos_count = len(open_positions)
        header_lines = [
            "<b>📊 Control Panel & Status:</b>\n",
            f"• Статус ядра: <b>{status_text}</b>",
            f"• Режим направления: <b>{direction_mode}</b>",
            f"• Монет в мониторинге: <b>{symbols_count}</b>",
            f"• Открытых виртуальных позиций: <b>{pos_count}</b>\n",
            "<b>Активные позиции:</b>"
        ]
        body_lines = open_positions if open_positions else ["  <i>Нет открытых позиций</i>"]
        all_lines = header_lines + body_lines
        messages = Utils.split_telegram_text(all_lines, max_len=4000)

        for i, msg in enumerate(messages):
            rm = TGKeyboards.main_menu(is_paused) if i == len(messages) - 1 else None
            await message.answer(msg, reply_markup=rm, parse_mode="HTML")

    @router.message(F.text == "🚨 Close All")
    async def on_close_all_prompt(message: Message, state: FSMContext):
        await state.clear()
        total_open = 0
        if hasattr(bot_core, "universe_manager") and bot_core.universe_manager:
            for univ in bot_core.universe_manager.universes.values():
                for sides in getattr(univ.state, "positions", {}).values():
                    for pos in sides.values():
                        if getattr(pos, "is_active", False):
                            total_open += 1
        elif hasattr(bot_core, "state"):
            for sides in getattr(bot_core.state, "positions", {}).values():
                for pos in sides.values():
                    if getattr(pos, "is_active", False):
                        total_open += 1

        if total_open == 0:
            await message.answer("ℹ️ Нет открытых позиций для закрытия.")
            return

        warn_text = (
            f"⚠️ <b>ВНИМАНИЕ!</b>\n\n"
            f"Вы собираетесь экстренно закрыть по рынку <b>{total_open}</b> открытых позиций!\n"
            f"Все сделки будут зафиксированы в аналитике с учетом комиссий и проскальзывания."
        )
        await message.answer(warn_text, reply_markup=TGKeyboards.confirm_close_all(), parse_mode="HTML")

    @router.callback_query(F.data == "close_all_confirm")
    async def on_close_all_confirm(callback: CallbackQuery):
        await callback.answer()
        if hasattr(bot_core, "close_all_positions"):
            await bot_core.close_all_positions()
            await callback.message.edit_text("✅ <b>Все виртуальные позиции успешно закрыты по рынку!</b>", parse_mode="HTML")
        else:
            await callback.message.edit_text("❌ Ошибка: метод close_all_positions не найден в BotCore.")

    @router.callback_query(F.data == "close_all_cancel")
    async def on_close_all_cancel(callback: CallbackQuery):
        await callback.answer("Отменено")
        await callback.message.delete()

    @router.message(F.text == "📜 Logs")
    async def on_logs_menu(message: Message, state: FSMContext):
        await state.clear()
        await message.answer("Выберите нужный файл для скачивания:", reply_markup=TGKeyboards.logs_menu())

    @router.callback_query(F.data == "logs_get_logs")
    async def on_get_logs(callback: CallbackQuery):
        await callback.answer()
        log_path = BASE_DIR / "logs" / "all.log"
        if not log_path.exists():
            log_path = os.path.join("logs", "all.log")

        if os.path.exists(log_path):
            await callback.message.answer_document(FSInputFile(str(log_path)))
        else:
            await callback.message.answer("⚠️ Файл логов all.log пока не создан.")

    @router.callback_query(F.data == "logs_get_cfg")
    async def on_get_cfg(callback: CallbackQuery):
        await callback.answer()
        if CFG_PATH.exists():
            await callback.message.answer_document(FSInputFile(str(CFG_PATH)))
        else:
            await callback.message.answer("⚠️ Файл конфигурации cfg.json не найден.")

    @router.callback_query(F.data == "logs_get_state")
    async def on_get_state(callback: CallbackQuery):
        await callback.answer()
        state_path = DATA_DIR / "state.json"
        if state_path.exists():
            await callback.message.answer_document(FSInputFile(str(state_path)), caption="💾 Актуальный слепок state.json (позиции)")
        else:
            await callback.message.answer("⚠️ Файл state.json пока не создан (нет активных сохраненных позиций).")
