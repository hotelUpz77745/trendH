# ============================================================
# FILE: TG/handlers_analytics.py
# ROLE: Telegram analytics handlers (Equity, Ledger, Ranking, Stats)
# ============================================================

import json
import csv
import time
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from consts import ANALYTICS_DIR
from ANALYTICS.metrics import AnalyticsMathEngine
from ANALYTICS.plotter import generate_equity_curve
from TG.keyboards import TGKeyboards

analytics_router = Router(name="analytics_router")


class AnalyticsStates(StatesGroup):
    waiting_for_balance = State()


def _get_analytics_data() -> dict:
    """Безопасное чтение файла аналитики с автоматическим перерасчетом метрик."""
    file_path = ANALYTICS_DIR / "analytics.json"
    if not file_path.exists():
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        AnalyticsMathEngine.calculate(data)
        return data
    except Exception:
        return {}


def _format_analytics_text(data: dict) -> str:
    """Форматирует глобальную математическую сводку аналитики."""
    if not data:
        return "📊 <b>Аналитика пока не содержит данных по сделкам.</b>"

    start_bal = data.get("start_balance_usdt", 0.0)
    cur_bal = data.get("cur_balance_usdt", 0.0)
    net_profit = data.get("net_profit_usdt", 0.0)
    realized_pnl = data.get("realized_pnl_usdt", 0.0)
    unrealized_pnl = data.get("unrealized_pnl_usdt", 0.0)
    total_trades = data.get("total_trades", 0)
    winning_trades = data.get("winning_trades", 0)
    winrate_pct = data.get("winrate_pct", 0.0)
    max_dd = data.get("max_drawdown_usdt", 0.0)
    rec_factor = data.get("recovery_factor", 0.0)
    roi_pct = data.get("roi_pct", 0.0)

    pnl_sign = "+" if net_profit >= 0 else ""
    roi_sign = "+" if roi_pct >= 0 else ""
    dd_val = -abs(max_dd) if max_dd > 0 else 0.0

    return (
        f"<b>📊 Сводная аналитика (Paper Trading):</b>\n\n"
        f"• Стартовый баланс: <code>{start_bal:.2f} USDT</code>\n"
        f"• Текущий баланс: <code>{cur_bal:.2f} USDT</code>\n"
        f"• Чистый профит: <b>{pnl_sign}{net_profit:.4f} USDT</b> ({roi_sign}{roi_pct:.2f}%)\n"
        f"• Реализованный PnL: <code>{realized_pnl:.4f} USDT</code>\n"
        f"• Плавающий PnL: <code>{unrealized_pnl:.4f} USDT</code>\n"
        f"• Всего сделок: <b>{total_trades}</b> (Побед: {winning_trades} | Winrate: {winrate_pct:.1f}%)\n"
        f"• Макс. просадка (DD): <code>{dd_val:.4f} USDT</code>\n"
        f"• Фактор восстановления: <code>{rec_factor:.2f}</code>\n"
    )


def setup_analytics_handlers(router: Router, bot_core):
    """Регистрирует обработчики меню аналитики."""

    @router.message(F.text == "📊 Analytics")
    async def on_analytics_menu(message: Message, state: FSMContext):
        await state.clear()
        data = _get_analytics_data()
        text = _format_analytics_text(data)
        await message.answer(text, reply_markup=TGKeyboards.analytics_menu(), parse_mode="HTML")

    @router.callback_query(F.data == "analytics_back")
    async def on_analytics_back(callback: CallbackQuery, state: FSMContext):
        await state.clear()
        await callback.answer()
        data = _get_analytics_data()
        text = _format_analytics_text(data)
        await callback.message.edit_text(text, reply_markup=TGKeyboards.analytics_menu(), parse_mode="HTML")

    @router.callback_query(F.data == "analytics_equity")
    async def on_analytics_equity(callback: CallbackQuery):
        await callback.answer("Генерация графика эквити...")
        plot_path = generate_equity_curve()
        if plot_path and (ANALYTICS_DIR / "images" / "equity_curve.png").exists():
            await callback.message.answer_photo(
                photo=FSInputFile(plot_path),
                caption="📈 <b>Кривая доходности (Equity Curve)</b>",
                parse_mode="HTML"
            )
        else:
            await callback.message.answer("⚠️ Недостаточно закрытых сделок для построения графика эквити.")

    @router.callback_query(F.data == "analytics_ledger")
    async def on_analytics_ledger(callback: CallbackQuery):
        await callback.answer()
        txt_path = ANALYTICS_DIR / "trades_ledger.txt"
        if txt_path.exists():
            await callback.message.answer_document(
                FSInputFile(str(txt_path)),
                caption="📄 <b>Журнал всех виртуальных сделок (CSV/TXT)</b>",
                parse_mode="HTML"
            )
        else:
            await callback.message.answer("⚠️ Журнал сделок trades_ledger.txt пока пуст.")

    @router.callback_query(F.data.startswith("analytics_ranking"))
    async def on_analytics_ranking(callback: CallbackQuery):
        await callback.answer()
        sort_by = callback.data.split("_")[-1]  # profit, trades, winrate
        data = _get_analytics_data()
        per_coin = data.get("per_coin", {})

        if not per_coin:
            await callback.message.edit_text(
                "🏆 <b>Рейтинг монет:</b> пока нет закрытых сделок.",
                reply_markup=TGKeyboards.analytics_ranking_menu(),
                parse_mode="HTML"
            )
            return

        coin_items = []
        for sym, cdata in per_coin.items():
            pnl = cdata.get("realized_pnl_usdt", 0.0)
            trades = cdata.get("trades", 0)
            wins = cdata.get("win_count", 0)
            wr = (wins / trades * 100) if trades > 0 else 0.0
            coin_items.append({"sym": sym, "pnl": pnl, "trades": trades, "wr": wr})

        if sort_by == "trades":
            coin_items.sort(key=lambda x: x["trades"], reverse=True)
            title = "📊 <b>Рейтинг монет по количеству сделок:</b>"
        elif sort_by == "winrate":
            coin_items.sort(key=lambda x: (x["wr"], x["trades"]), reverse=True)
            title = "🎯 <b>Рейтинг монет по Winrate:</b>"
        else:
            coin_items.sort(key=lambda x: x["pnl"], reverse=True)
            title = "💵 <b>Рейтинг монет по PnL:</b>"

        lines = [title, ""]
        for idx, item in enumerate(coin_items[:15], 1):
            sign = "+" if item["pnl"] >= 0 else ""
            lines.append(
                f"{idx}. <b>{item['sym']}</b>: {sign}{item['pnl']:.2f}$ | {item['trades']} сд. | WR: {item['wr']:.1f}%"
            )

        await callback.message.edit_text(
            "\n".join(lines),
            reply_markup=TGKeyboards.analytics_ranking_menu(),
            parse_mode="HTML"
        )

    @router.callback_query(F.data == "analytics_help")
    async def on_analytics_help(callback: CallbackQuery):
        await callback.answer()
        help_text = (
            "<b>ℹ️ Шпаргалка по показателям аналитики:</b>\n\n"
            "• <b>ROI (%)</b>: Доходность относительно стартового депозита.\n"
            "• <b>Net Profit</b>: Чистая прибыль с учетом комиссий и проскальзывания.\n"
            "• <b>Realized PnL</b>: Суммарный закрытый результат по всем сделкам.\n"
            "• <b>Winrate (%)</b>: Процент прибыльных сделок от общего числа.\n"
            "• <b>Max Drawdown</b>: Максимальная историческая просадка баланса.\n"
            "• <b>Recovery Factor</b>: Отношение прибыли к макс. просадке (PnL / DD).\n"
            "• <b>DRME</b>: Дневная доходность на максимальный сайз (Daily Return on Max Exposure).\n"
            "• <b>MDME</b>: Максимальная просадка на максимальный сайз (Max DD on Max Exposure)."
        )
        await callback.message.edit_text(
            help_text,
            reply_markup=TGKeyboards.analytics_ranking_menu(),
            parse_mode="HTML"
        )

    @router.callback_query(F.data == "analytics_set_balance")
    async def on_set_balance_btn(callback: CallbackQuery, state: FSMContext):
        await callback.answer()
        await state.set_state(AnalyticsStates.waiting_for_balance)
        await callback.message.answer(
            "💰 <b>Введите стартовый баланс депозита в USDT</b> (например: <code>1000</code>):",
            parse_mode="HTML",
            reply_markup=TGKeyboards.back_reply()
        )

    @router.message(AnalyticsStates.waiting_for_balance)
    async def on_balance_input(message: Message, state: FSMContext):
        if message.text == "🔙 Back":
            await state.clear()
            data = _get_analytics_data()
            await message.answer("Ввод отменен.", reply_markup=TGKeyboards.main_menu(getattr(bot_core, "is_paused", True)))
            return

        try:
            val = float(message.text.replace(",", ".").strip())
            if val < 0:
                raise ValueError()
        except ValueError:
            await message.answer("❌ Введите корректное положительное число (например: 1000):")
            return

        file_path = ANALYTICS_DIR / "analytics.json"
        data = _get_analytics_data()
        data["start_balance_usdt"] = val
        if "cur_balance_usdt" not in data or data["cur_balance_usdt"] == 0:
            data["cur_balance_usdt"] = val

        AnalyticsMathEngine.calculate(data)
        file_path.write_text(json.dumps(data, indent=4), encoding="utf-8")

        await state.clear()
        is_paused = getattr(bot_core, "is_paused", True)
        await message.answer(
            f"✅ Стартовый баланс установлен: <b>{val:.2f} USDT</b>",
            reply_markup=TGKeyboards.main_menu(is_paused),
            parse_mode="HTML"
        )

    @router.callback_query(F.data == "analytics_reset")
    async def on_reset_prompt(callback: CallbackQuery):
        await callback.answer()
        await callback.message.edit_text(
            "⚠️ <b>Вы уверены, что хотите сбросить всю аналитику?</b>\n"
            "Все записи по сделкам и расчетные метрики будут очищены.",
            reply_markup=TGKeyboards.confirm_reset_analytics(),
            parse_mode="HTML"
        )

    @router.callback_query(F.data == "reset_analytics_confirm")
    async def on_reset_confirm(callback: CallbackQuery):
        await callback.answer("Сброс аналитики...")
        current_ms = int(time.time() * 1000)
        default_data = {
            "start_balance_usdt": 1000.0,
            "first_trade_ts": current_ms,
            "cur_balance_usdt": 1000.0,
            "total_trades": 0,
            "winning_trades": 0,
            "winrate_pct": 0.0,
            "realized_pnl_usdt": 0.0,
            "net_profit_usdt": 0.0,
            "unrealized_pnl_usdt": 0.0,
            "per_coin": {}
        }
        AnalyticsMathEngine.calculate(default_data)
        (ANALYTICS_DIR / "analytics.json").write_text(json.dumps(default_data, indent=4), encoding="utf-8")

        # Очищаем ledger
        txt_path = ANALYTICS_DIR / "trades_ledger.txt"
        with open(txt_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(["Symbol", "Side", "Open Time", "Close Time", "PnL", "Balance"])

        await callback.message.edit_text(
            "✅ <b>Аналитика и журнал сделок успешно сброшены.</b>",
            parse_mode="HTML"
        )
