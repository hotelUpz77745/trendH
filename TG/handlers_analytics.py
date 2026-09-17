# ============================================================
# FILE: TG/handlers_analytics.py
# ROLE: Telegram analytics handlers (Universes, Equity, Ledger, Leaderboard)
# ============================================================

import json
import csv
import time
from typing import Optional
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from consts import ANALYTICS_DIR
from ANALYTICS.metrics import AnalyticsMathEngine
from ANALYTICS.plotter import generate_equity_curve
from TG.keyboards import TGKeyboards
from c_log import UnifiedLogger
from utils import Utils

logger = UnifiedLogger("TGAnalytics")
analytics_router = Router(name="analytics_router")


class AnalyticsStates(StatesGroup):
    waiting_for_balance = State()


def _get_universe_list(bot_core) -> list:
    if bot_core and hasattr(bot_core, "universe_manager"):
        return bot_core.universe_manager.get_all_universes()
    return []


def _get_analytics_data(universe_id: str = "u1") -> dict:
    """Безопасное чтение файла аналитики вселенной с перерасчетом метрик."""
    suffix = f"_{universe_id}" if universe_id and universe_id != "default" else ""
    file_path = ANALYTICS_DIR / f"analytics{suffix}.json"
    if not file_path.exists():
        # Fallback to default if u1 not yet created
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


def _format_analytics_text(data: dict, bot_core=None, universe_id: str = "u1") -> str:
    """Форматирует сводку аналитики выбранной вселенной с нереализованным PnL."""
    univ_obj = None
    if bot_core and hasattr(bot_core, "universe_manager"):
        univ_obj = bot_core.universe_manager.get_universe(universe_id)

    univ_title = f"🌐 <b>Вселенная: {univ_obj.name}</b>" if univ_obj else f"🌐 <b>Вселенная: {universe_id.upper()}</b>"
    desc_str = f"<i>{univ_obj.description}</i>\n\n" if univ_obj and univ_obj.description else "\n"

    if not data:
        return f"{univ_title}\n{desc_str}📊 <b>Аналитика пока не содержит данных по сделкам.</b>"

    start_bal = float(data.get("start_balance_usdt", 0.0))
    if start_bal <= 0.0:
        from consts import ANALYTICS_CFG
        start_bal = float(ANALYTICS_CFG.get("default_start_balance", 1000.0))

    realized_pnl = float(data.get("realized_pnl_usdt", 0.0))

    # Расчет текущего нереализованного PnL по позициям этой вселенной
    unrealized_pnl = 0.0
    active_count = 0
    if univ_obj and hasattr(univ_obj, "state"):
        positions = getattr(univ_obj.state, "positions", {})
        current_prices = getattr(bot_core, "current_prices", {})
        for sym, sides in positions.items():
            for side, pos_info in sides.items():
                if not pos_info.is_active or pos_info.open_price <= 0:
                    continue
                active_count += 1
                cur_price = current_prices.get(sym, pos_info.open_price)
                if side == "LONG":
                    pnl_ratio = (cur_price - pos_info.open_price) / pos_info.open_price
                else:
                    pnl_ratio = (pos_info.open_price - cur_price) / pos_info.open_price
                unrealized_pnl += pnl_ratio * pos_info.size
    else:
        unrealized_pnl = float(data.get("unrealized_pnl_usdt", 0.0))

    # Живой перерасчет текущего баланса (Equity) и чистого профита с учетом нереализованного PnL
    live_net_profit = realized_pnl + unrealized_pnl
    live_cur_bal = start_bal + live_net_profit
    live_roi_pct = round(((live_cur_bal - start_bal) / start_bal) * 100, 2) if start_bal > 0 else 0.0

    total_trades = data.get("total_trades", 0)
    winning_trades = data.get("winning_trades", 0)
    winrate_pct = data.get("winrate_pct", 0.0)
    max_dd = data.get("max_drawdown_usdt", 0.0)
    rec_factor = data.get("recovery_factor", 0.0)

    pnl_sign = "+" if live_net_profit >= 0 else ""
    roi_sign = "+" if live_roi_pct >= 0 else ""
    u_sign = "+" if unrealized_pnl >= 0 else ""
    dd_val = -abs(max_dd) if max_dd > 0 else 0.0

    return (
        f"{univ_title}\n{desc_str}"
        f"• Стартовый баланс: <code>{start_bal:.2f} USDT</code>\n"
        f"• Текущий баланс: <code>{live_cur_bal:.2f} USDT</code>\n"
        f"• Чистый профит: <b>{pnl_sign}{live_net_profit:.4f} USDT</b> ({roi_sign}{live_roi_pct:.2f}%)\n"
        f"• Реализованный PnL: <code>{realized_pnl:.4f} USDT</code>\n"
        f"• Нереализованный PnL: <code>{u_sign}{unrealized_pnl:.4f} USDT</code> ({active_count} поз.)\n"
        f"• Всего сделок: <b>{total_trades}</b> (Побед: {winning_trades} | Winrate: {winrate_pct:.1f}%)\n"
        f"• Макс. просадка (DD): <code>{dd_val:.4f} USDT</code>\n"
        f"• Фактор восстановления: <code>{rec_factor:.2f}</code>\n"
    )


def _format_leaderboard_lines(bot_core) -> list:
    """Форматирует строки таблицы лидеров для всех параллельных вселенных."""
    if not bot_core or not hasattr(bot_core, "universe_manager"):
        return ["🏆 <b>Менеджер вселенных не инициализирован.</b>"]

    board = bot_core.universe_manager.get_leaderboard(bot_core.current_prices)
    if not board:
        return ["🏆 <b>Нет активных вселенных.</b>"]

    total_items = len(board)
    lines = [
        f"<b>🏆 Таблица лидеров всех стратегий ({total_items} шт.):</b>\n"
    ]

    for idx, item in enumerate(board, 1):
        medal = "🥇" if idx == 1 else ("🥈" if idx == 2 else ("🥉" if idx == 3 else f"{idx}."))
        uid = item["uid"]
        is_skip = uid.endswith("_skip") or "skip" in uid.lower()
        skip_tag = " ⚡<b>[SKIP]</b>" if is_skip else ""

        # Clean short name (up to 20 chars, removing redundant (SKIP))
        raw_name = item.get("name", uid).split("(")[0].strip().replace(" (SKIP)", "").replace(" (skip)", "")
        short_name = f" ({raw_name[:20]})" if raw_name else ""

        pnl_sign = "+" if item["net_profit"] >= 0 else ""
        u_sign = "+" if item["unrealized_pnl"] >= 0 else ""
        dd_val = -abs(item["max_dd"]) if item["max_dd"] > 0 else 0.0

        lines.append(
            f"{medal} <b>{uid.upper()}</b>{skip_tag}{short_name}\n"
            f"   • PnL: <b>{pnl_sign}{item['net_profit']:.2f}$</b> | WR: {item['winrate']:.0f}% ({item['total_trades']}) | DD: {dd_val:.2f}$ | Откр: {item['active_count']} ({u_sign}{item['unrealized_pnl']:.2f}$)"
        )

    return lines


def _format_leaderboard_text(bot_core) -> str:
    """Возвращает полный текст таблицы лидеров."""
    return "\n".join(_format_leaderboard_lines(bot_core))


def setup_analytics_handlers(router: Router, bot_core):
    """Регистрирует обработчики меню аналитики."""

    @router.message(F.text == "📊 Analytics")
    async def on_analytics_menu(message: Message, state: FSMContext):
        await state.clear()
        data = _get_analytics_data("u1")
        universes = _get_universe_list(bot_core)
        text = _format_analytics_text(data, bot_core=bot_core, universe_id="u1")
        await message.answer(text, reply_markup=TGKeyboards.analytics_menu("u1", universes), parse_mode="HTML")

    @router.callback_query(F.data == "analytics_back")
    async def on_analytics_back(callback: CallbackQuery, state: FSMContext):
        await state.clear()
        await callback.answer()
        data = _get_analytics_data("u1")
        universes = _get_universe_list(bot_core)
        text = _format_analytics_text(data, bot_core=bot_core, universe_id="u1")
        await callback.message.edit_text(text, reply_markup=TGKeyboards.analytics_menu("u1", universes), parse_mode="HTML")

    @router.callback_query(F.data.startswith("analytics_univ_"))
    async def on_switch_universe(callback: CallbackQuery):
        uid = callback.data.replace("analytics_univ_", "")
        await callback.answer(f"Вселенная {uid.upper()}")
        data = _get_analytics_data(uid)
        universes = _get_universe_list(bot_core)
        text = _format_analytics_text(data, bot_core=bot_core, universe_id=uid)
        await callback.message.edit_text(text, reply_markup=TGKeyboards.analytics_menu(uid, universes), parse_mode="HTML")

    @router.callback_query(F.data.startswith("analytics_leaderboard"))
    async def on_analytics_leaderboard(callback: CallbackQuery):
        await callback.answer()
        lines = _format_leaderboard_lines(bot_core)
        messages = Utils.split_telegram_text(lines, max_len=4000)
        kb = TGKeyboards.leaderboard_menu()

        if len(messages) == 1:
            try:
                await callback.message.edit_text(messages[0], reply_markup=kb, parse_mode="HTML")
            except TelegramBadRequest as e:
                if "message is not modified" not in str(e).lower():
                    logger.error(f"[Leaderboard] Telegram error: {e}")
            except Exception as e:
                logger.error(f"[Leaderboard] Error updating message: {e}")
        else:
            try:
                await callback.message.delete()
            except Exception:
                pass
            for i, msg in enumerate(messages):
                rm = kb if i == len(messages) - 1 else None
                await callback.message.answer(msg, reply_markup=rm, parse_mode="HTML")

    @router.callback_query(F.data.startswith("analytics_equity"))
    async def on_analytics_equity(callback: CallbackQuery):
        uid = callback.data.replace("analytics_equity_", "").replace("analytics_equity", "")
        uid = uid if uid else "u1"
        await callback.answer(f"Генерация графика эквити [{uid.upper()}]...")
        plot_path = generate_equity_curve(universe_id=uid)
        suffix = f"_{uid}" if uid and uid != "default" else ""
        if plot_path and (ANALYTICS_DIR / "images" / f"equity_curve{suffix}.png").exists():
            await callback.message.answer_photo(
                photo=FSInputFile(plot_path),
                caption=f"📈 <b>Кривая доходности [{uid.upper()}]</b>",
                parse_mode="HTML"
            )
        else:
            await callback.message.answer(f"⚠️ Недостаточно закрытых сделок для построения графика [{uid.upper()}].")

    @router.callback_query(F.data.startswith("analytics_ledger"))
    async def on_analytics_ledger(callback: CallbackQuery):
        uid = callback.data.replace("analytics_ledger_", "").replace("analytics_ledger", "")
        uid = uid if uid else "u1"
        await callback.answer()
        suffix = f"_{uid}" if uid and uid != "default" else ""
        txt_path = ANALYTICS_DIR / f"trades_ledger{suffix}.txt"
        if not txt_path.exists():
            txt_path = ANALYTICS_DIR / "trades_ledger.txt"

        if txt_path.exists():
            await callback.message.answer_document(
                FSInputFile(str(txt_path)),
                caption=f"📄 <b>Журнал сделок [{uid.upper()}] (CSV/TXT)</b>",
                parse_mode="HTML"
            )
        else:
            await callback.message.answer(f"⚠️ Журнал сделок для {uid.upper()} пока пуст.")

    @router.callback_query(F.data.startswith("analytics_ranking_"))
    async def on_analytics_ranking(callback: CallbackQuery):
        await callback.answer()
        parts = callback.data.split("_")  # analytics_ranking_{uid}_{sort_by}
        uid = parts[2] if len(parts) >= 4 else "u1"
        sort_by = parts[-1]  # profit, trades, winrate

        data = _get_analytics_data(uid)
        per_coin = data.get("per_coin", {})

        if not per_coin:
            await callback.message.edit_text(
                f"🏆 <b>Рейтинг монет [{uid.upper()}]:</b> пока нет закрытых сделок.",
                reply_markup=TGKeyboards.analytics_ranking_menu(uid),
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
            title = f"📊 <b>Рейтинг монет [{uid.upper()}] по количеству сделок:</b>"
        elif sort_by == "winrate":
            coin_items.sort(key=lambda x: (x["wr"], x["trades"]), reverse=True)
            title = f"🎯 <b>Рейтинг монет [{uid.upper()}] по Winrate:</b>"
        else:
            coin_items.sort(key=lambda x: x["pnl"], reverse=True)
            title = f"💵 <b>Рейтинг монет [{uid.upper()}] по PnL:</b>"

        lines = [title, ""]
        for idx, item in enumerate(coin_items, 1):
            sign = "+" if item["pnl"] >= 0 else ""
            lines.append(
                f"{idx}. <b>{item['sym']}</b>: {sign}{item['pnl']:.2f}$ | {item['trades']} сд. | WR: {item['wr']:.1f}%"
            )

        messages = Utils.split_telegram_text(lines, max_len=4000)
        kb = TGKeyboards.analytics_ranking_menu(uid)

        if len(messages) == 1:
            try:
                await callback.message.edit_text(messages[0], reply_markup=kb, parse_mode="HTML")
            except TelegramBadRequest as e:
                if "message is not modified" not in str(e).lower():
                    logger.error(f"[Ranking] Telegram error: {e}")
            except Exception as e:
                logger.error(f"[Ranking] Error updating ranking: {e}")
        else:
            try:
                await callback.message.delete()
            except Exception:
                pass
            for i, msg in enumerate(messages):
                rm = kb if i == len(messages) - 1 else None
                await callback.message.answer(msg, reply_markup=rm, parse_mode="HTML")

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
            "• <b>Leaderboard</b>: Сравнительная таблица всех параллельных вселенных."
        )
        await callback.message.edit_text(
            help_text,
            reply_markup=TGKeyboards.leaderboard_menu(),
            parse_mode="HTML"
        )

    @router.callback_query(F.data.startswith("analytics_set_balance_"))
    async def on_set_balance_btn(callback: CallbackQuery, state: FSMContext):
        uid = callback.data.replace("analytics_set_balance_", "")
        await callback.answer()
        await state.update_data(target_uid=uid)
        await state.set_state(AnalyticsStates.waiting_for_balance)
        await callback.message.answer(
            f"💰 <b>Введите стартовый баланс депозита [{uid.upper()}] в USDT</b> (например: <code>1000</code>):",
            parse_mode="HTML",
            reply_markup=TGKeyboards.back_reply()
        )

    @router.message(AnalyticsStates.waiting_for_balance)
    async def on_balance_input(message: Message, state: FSMContext):
        if message.text == "🔙 Back":
            await state.clear()
            await message.answer("Ввод отменен.", reply_markup=TGKeyboards.main_menu(getattr(bot_core, "is_paused", True)))
            return

        try:
            val = float(message.text.replace(",", ".").strip())
            if val < 0:
                raise ValueError()
        except ValueError:
            await message.answer("❌ Введите корректное положительное число (например: 1000):")
            return

        state_data = await state.get_data()
        target_uid = state_data.get("target_uid", "u1")
        suffix = f"_{target_uid}" if target_uid and target_uid != "default" else ""
        file_path = ANALYTICS_DIR / f"analytics{suffix}.json"

        data = _get_analytics_data(target_uid)
        data["start_balance_usdt"] = val
        if "cur_balance_usdt" not in data or data["cur_balance_usdt"] == 0:
            data["cur_balance_usdt"] = val

        AnalyticsMathEngine.calculate(data)
        file_path.write_text(json.dumps(data, indent=4), encoding="utf-8")

        await state.clear()
        is_paused = getattr(bot_core, "is_paused", True)
        await message.answer(
            f"✅ Стартовый баланс для [{target_uid.upper()}] установлен: <b>{val:.2f} USDT</b>",
            reply_markup=TGKeyboards.main_menu(is_paused),
            parse_mode="HTML"
        )

    @router.callback_query(F.data.startswith("analytics_reset_"))
    async def on_reset_prompt(callback: CallbackQuery):
        uid = callback.data.replace("analytics_reset_", "")
        await callback.answer()
        await callback.message.edit_text(
            f"⚠️ <b>Вы уверены, что хотите сбросить аналитику для [{uid.upper()}]?</b>\n"
            "Все записи по сделкам и расчетные метрики этой вселенной будут очищены.",
            reply_markup=TGKeyboards.confirm_reset_analytics(uid),
            parse_mode="HTML"
        )

    @router.callback_query(F.data.startswith("reset_analytics_confirm_"))
    async def on_reset_confirm(callback: CallbackQuery):
        uid = callback.data.replace("reset_analytics_confirm_", "")
        await callback.answer(f"Сброс аналитики [{uid.upper()}]...")
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
        suffix = f"_{uid}" if uid and uid != "default" else ""
        (ANALYTICS_DIR / f"analytics{suffix}.json").write_text(json.dumps(default_data, indent=4), encoding="utf-8")

        txt_path = ANALYTICS_DIR / f"trades_ledger{suffix}.txt"
        with open(txt_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(["Symbol", "Side", "Open Time", "Close Time", "PnL", "Balance"])

        await callback.message.edit_text(
            f"✅ <b>Аналитика и журнал сделок для [{uid.upper()}] успешно сброшены.</b>",
            parse_mode="HTML"
        )
