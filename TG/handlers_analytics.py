# ============================================================
# FILE: TG/handlers_analytics.py
# ROLE: Telegram analytics handlers (Universes, Equity, Ledger, Leaderboard)
# ============================================================

import json
import csv
import time
import random
from typing import Optional, Any
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from consts import ANALYTICS_DIR, ANALYTICS_CFG
from ANALYTICS.metrics import AnalyticsMathEngine
from ANALYTICS.plotter import generate_equity_curve, consolidate_portfolio_ledger
from TG.keyboards import TGKeyboards
from TG.strategy_guide import get_leader_badge, register_strategy_guide_handlers
from c_log import UnifiedLogger
from utils import Utils

logger = UnifiedLogger("TGAnalytics")
analytics_router = Router(name="analytics_router")


class AnalyticsStates(StatesGroup):
    waiting_for_balance = State()
    waiting_for_reset_confirm = State()


def _get_universe_list(bot_core) -> list:
    if bot_core and hasattr(bot_core, "universe_manager"):
        return bot_core.universe_manager.get_all_universes()
    return []


def _get_default_universe_id(bot_core=None) -> str:
    """Возвращает 'all' для показа суммарного портфеля всех стратегий по умолчанию."""
    return "all"


def _get_analytics_data(universe_id: str = "all") -> dict:
    """Безопасное чтение файла аналитики вселенной или портфеля с перерасчетом метрик."""
    suffix = f"_{universe_id}" if universe_id and universe_id not in ("default", "all") else ("_all" if universe_id == "all" else "")
    file_path = ANALYTICS_DIR / f"analytics{suffix}.json"
    if not file_path.exists():
        file_path = ANALYTICS_DIR / "analytics.json"
        if not file_path.exists():
            return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        AnalyticsMathEngine.calculate(data, universe_id=universe_id)
        return data
    except Exception:
        return {}


def _format_analytics_text(data: dict, bot_core=None, universe_id: str = "all") -> str:
    """Форматирует сводку аналитики выбранной вселенной или суммарного портфеля со всеми метриками."""
    cur_prices = getattr(bot_core, "current_prices", {})
    mgr = getattr(bot_core, "universe_manager", None)
    is_all = (universe_id in ("all", "total", "portfolio"))

    if is_all and mgr and hasattr(mgr, "get_portfolio_metrics"):
        m = mgr.get_portfolio_metrics(cur_prices)
        u_cnt = m.get("active_universes", len(mgr.universes))
        title = f"🌐 <b>Портфель: ВСЕ СТРАТЕГИИ ({u_cnt} шт.)</b>\n"
        desc = "<i>Сводная аналитика и аккумулированное эквити по всем активным стратегиям</i>\n\n"
        start_bal, realized_pnl, unrealized_pnl = m["start_balance"], m["realized_pnl"], m["unrealized_pnl"]
        active_count, live_net, live_bal = m["active_count"], m["live_net_profit"], m["live_equity"]
        max_dd, curr_dd = m["max_dd"], m["current_dd"]
        peak_bal = m.get("peak_equity", max(start_bal, live_bal))
        total_trades, winning_trades, winrate = m["total_trades"], m["winning_trades"], m["winrate_pct"]
    else:
        univ = mgr.get_universe(universe_id) if mgr else None
        badge = get_leader_badge(universe_id)
        title = f"🌐 <b>Вселенная: {univ.name if univ else universe_id.upper()}{badge}</b>\n"
        desc = f"<i>{univ.description}</i>\n\n" if univ and univ.description else "\n"
        if not data and not univ:
            return f"{title}{desc}📊 <b>Аналитика пока не содержит данных по сделкам.</b>"

        if univ and hasattr(univ, "update_live_metrics"):
            m = univ.update_live_metrics(cur_prices)
            start_bal = float(data.get("start_balance_usdt", m.get("start_balance", 200.0)))
            realized_pnl = float(data.get("realized_pnl_usdt", m["realized_pnl"]))
            unrealized_pnl, active_count = m["unrealized_pnl"], m["active_count"]
            live_net, live_bal = realized_pnl + unrealized_pnl, start_bal + (realized_pnl + unrealized_pnl)
            max_dd, curr_dd = m["max_dd"], m["current_dd"]
            peak_bal = m.get("peak_equity", float(data.get("peak_balance_usdt", max(start_bal, live_bal))))
        else:
            start_bal = float(data.get("start_balance_usdt", 0.0)) or 200.0
            realized_pnl = float(data.get("realized_pnl_usdt", 0.0))
            unrealized_pnl, active_count = float(data.get("unrealized_pnl_usdt", 0.0)), 0
            if univ and hasattr(univ, "state"):
                for sym, sides in getattr(univ.state, "positions", {}).items():
                    for side, pos in sides.items():
                        if pos.is_active and pos.open_price > 0:
                            active_count += 1
                            cp = cur_prices.get(sym) or pos.open_price
                            unrealized_pnl += ((cp - pos.open_price if side == "LONG" else pos.open_price - cp) / pos.open_price) * pos.size
            live_net, live_bal = realized_pnl + unrealized_pnl, start_bal + (realized_pnl + unrealized_pnl)
            max_dd, curr_dd = float(data.get("max_drawdown_usdt", 0.0)), float(data.get("current_drawdown_usdt", 0.0))
            peak_bal = float(data.get("peak_balance_usdt", max(start_bal, live_bal)))
        total_trades, winning_trades = int(data.get("total_trades", 0)), int(data.get("winning_trades", 0))
        winrate = float(data.get("winrate_pct", 0.0))

    peak_pnl = peak_bal - start_bal
    peak_p_s = "+" if peak_pnl >= 0 else ""
    roi = round((live_net / start_bal) * 100, 2) if start_bal > 0 else 0.0
    dd = -abs(max_dd) if max_dd > 0 else 0.0
    c_dd = -abs(curr_dd) if curr_dd > 0 else 0.0
    rec = round(live_net / max_dd, 2) if max_dd > 0 else 0.0
    p_s, r_s, u_s = ("+" if live_net >= 0 else ""), ("+" if roi >= 0 else ""), ("+" if unrealized_pnl >= 0 else "")

    return (
        f"{title}{desc}"
        f"• Стартовый баланс: <code>{start_bal:.2f} USDT</code>\n"
        f"• Пиковый баланс: <code>{peak_bal:.2f} USDT</code> ({peak_p_s}{peak_pnl:.2f}$)\n"
        f"• Текущий баланс: <code>{live_bal:.2f} USDT</code>\n"
        f"• Чистый профит: <b>{p_s}{live_net:.4f} USDT</b> ({r_s}{roi:.2f}%)\n"
        f"• Реализованный PnL: <code>{realized_pnl:.4f} USDT</code>\n"
        f"• Нереализованный PnL: <code>{u_s}{unrealized_pnl:.4f} USDT</code> ({active_count} поз.)\n"
        f"• Всего сделок: <b>{total_trades}</b> (Побед: {winning_trades} | WR: {winrate:.1f}%)\n"
        f"• Макс. просадка (DD): <code>{dd:.4f} USDT</code> (тек: {c_dd:.4f}$)\n"
        f"• Фактор восстановления: <code>{rec:.2f}</code>\n"
    )


def _format_leaderboard_lines(bot_core) -> list:
    """Форматирует строки таблицы лидеров для всех параллельных вселенных."""
    if not bot_core or not hasattr(bot_core, "universe_manager"):
        return ["🏆 <b>Менеджер вселенных не инициализирован.</b>"]
    board = bot_core.universe_manager.get_leaderboard(bot_core.current_prices)
    if not board:
        return ["🏆 <b>Нет активных вселенных.</b>"]
    lines = [f"<b>🏆 Таблица лидеров всех стратегий ({len(board)} шт.):</b>\n"]
    for idx, item in enumerate(board, 1):
        medal = "🥇" if idx == 1 else ("🥈" if idx == 2 else ("🥉" if idx == 3 else f"{idx}."))
        uid = item["uid"]
        badge = get_leader_badge(uid)
        skip_tag = " ⚡<b>[SKIP]</b>" if uid.endswith("_skip") or "skip" in uid.lower() else ""
        raw_name = item.get("name", uid).split("(")[0].strip().replace(" (SKIP)", "").replace(" (skip)", "")
        short_name = f" ({raw_name[:20]})" if raw_name else ""
        p_s = "+" if item["net_profit"] >= 0 else ""
        u_s = "+" if item["unrealized_pnl"] >= 0 else ""
        dd = -abs(item["max_dd"]) if item["max_dd"] > 0 else 0.0
        comm_val = item.get("commission_paid", 0.0)
        comm_str = f" (комса: -{comm_val:.2f}$)" if comm_val > 0.01 else ""
        lines.append(
            f"{medal} <b>{uid.upper()}</b>{badge}{skip_tag}{short_name}\n"
            f"   • Net PnL: <b>{p_s}{item['net_profit']:.2f}$</b>{comm_str} | WR: {item['winrate']:.0f}% ({item['total_trades']}) | DD: {dd:.2f}$ | Откр: {item['active_count']} ({u_s}{item['unrealized_pnl']:.2f}$)"
        )
    return lines


def _format_leaderboard_text(bot_core) -> str:
    """Возвращает полный текст таблицы лидеров."""
    return "\n".join(_format_leaderboard_lines(bot_core))


def _do_reset_analytics(uid: str, bot_core=None) -> None:
    """Выполняет фактический сброс файлов аналитики и журнала сделок для вселенной или всех вселенных."""
    now_ms = int(time.time() * 1000)
    targets = []
    if uid == "all" and bot_core and hasattr(bot_core, "universe_manager"):
        targets = [u.universe_id for u in bot_core.universe_manager.get_all_universes()] + ["all", "default"]
    else:
        targets = [uid]

    start_bal = float(ANALYTICS_CFG.get("default_start_balance", 200.0))
    for target_uid in set(targets):
        data = {
            "start_balance_usdt": start_bal, "first_trade_ts": now_ms, "cur_balance_usdt": start_bal,
            "total_trades": 0, "winning_trades": 0, "winrate_pct": 0.0, "realized_pnl_usdt": 0.0,
            "net_profit_usdt": 0.0, "unrealized_pnl_usdt": 0.0, "per_coin": {}
        }
        AnalyticsMathEngine.calculate(data, universe_id=target_uid)
        suffix = f"_{target_uid}" if target_uid and target_uid != "default" else ""
        (ANALYTICS_DIR / f"analytics{suffix}.json").write_text(json.dumps(data, indent=4), encoding="utf-8")
        with open(ANALYTICS_DIR / f"trades_ledger{suffix}.txt", mode="w", newline="", encoding="utf-8") as f:
            csv.writer(f, delimiter=';').writerow(["Symbol", "Side", "Open Time", "Close Time", "PnL", "Balance"])


async def _send_or_edit_split_messages(callback: CallbackQuery, messages: list, kb: Optional[Any], tag: str):
    """Отправляет одно или несколько сообщений без превышения лимита символов Telegram."""
    if len(messages) == 1:
        try:
            await callback.message.edit_text(messages[0], reply_markup=kb, parse_mode="HTML")
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e).lower():
                logger.error(f"[{tag}] Telegram error: {e}")
        except Exception as e:
            logger.error(f"[{tag}] Error updating: {e}")
    else:
        try:
            await callback.message.delete()
        except Exception:
            pass
        for i, msg in enumerate(messages):
            rm = kb if i == len(messages) - 1 else None
            await callback.message.answer(msg, reply_markup=rm, parse_mode="HTML")


def setup_analytics_handlers(router: Router, bot_core):
    """Регистрирует обработчики меню аналитики."""
    register_strategy_guide_handlers(router, bot_core)

    @router.message(F.text == "📊 Analytics")
    async def on_analytics_menu(message: Message, state: FSMContext):
        await state.clear()
        uid = _get_default_universe_id(bot_core)
        data = _get_analytics_data(uid)
        text = _format_analytics_text(data, bot_core=bot_core, universe_id=uid)
        await message.answer(text, reply_markup=TGKeyboards.analytics_menu(uid), parse_mode="HTML")

    @router.callback_query(F.data.startswith("analytics_back"))
    async def on_analytics_back(callback: CallbackQuery, state: FSMContext):
        await state.clear()
        await callback.answer()
        data_str = callback.data or ""
        uid = data_str.split(":")[-1] if ":" in data_str else _get_default_universe_id(bot_core)
        data = _get_analytics_data(uid)
        text = _format_analytics_text(data, bot_core=bot_core, universe_id=uid)
        await callback.message.edit_text(text, reply_markup=TGKeyboards.analytics_menu(uid), parse_mode="HTML")

    @router.callback_query(F.data.startswith("analytics_select_strat"))
    async def on_select_strategy_menu(callback: CallbackQuery):
        await callback.answer()
        data_str = callback.data or ""
        cur_uid = data_str.split(":")[-1] if ":" in data_str else _get_default_universe_id(bot_core)
        board = bot_core.universe_manager.get_leaderboard(bot_core.current_prices) if hasattr(bot_core, "universe_manager") else []
        text = (
            "<b>🎯 Выберите стратегию для детального просмотра:</b>\n"
            "<i>(Все активные стратегии упорядочены по результату в Лидерборде)</i>"
        )
        await callback.message.edit_text(
            text,
            reply_markup=TGKeyboards.strategy_select_menu(board, selected_uid=cur_uid),
            parse_mode="HTML"
        )

    @router.callback_query(F.data.startswith("analytics_univ_"))
    async def on_switch_universe(callback: CallbackQuery):
        uid = callback.data.replace("analytics_univ_", "")
        disp_name = "Все стратегии (Портфель)" if uid == "all" else f"Вселенная {uid.upper()}"
        await callback.answer(disp_name)
        data = _get_analytics_data(uid)
        text = _format_analytics_text(data, bot_core=bot_core, universe_id=uid)
        await callback.message.edit_text(text, reply_markup=TGKeyboards.analytics_menu(uid), parse_mode="HTML")

    @router.callback_query(F.data.startswith("analytics_leaderboard"))
    async def on_analytics_leaderboard(callback: CallbackQuery):
        await callback.answer()
        lines = _format_leaderboard_lines(bot_core)
        messages = Utils.split_telegram_text(lines, max_len=4000)
        await _send_or_edit_split_messages(callback, messages, TGKeyboards.leaderboard_menu(), "Leaderboard")

    @router.callback_query(F.data.startswith("analytics_equity"))
    async def on_analytics_equity(callback: CallbackQuery):
        uid = (callback.data.split(":")[-1] if ":" in callback.data else callback.data.replace("analytics_equity_", "")) or _get_default_universe_id(bot_core)
        await callback.answer(f"Генерация графика эквити [{uid.upper()}]...")
        plot_path = generate_equity_curve(universe_id=uid)
        suffix = f"_{uid}" if uid and uid != "default" else ""
        if plot_path and (ANALYTICS_DIR / "images" / f"equity_curve{suffix}.png").exists():
            await callback.message.answer_photo(photo=FSInputFile(plot_path), caption=f"📈 <b>Кривая доходности [{uid.upper()}]</b>", parse_mode="HTML")
        else:
            await callback.message.answer(f"⚠️ Недостаточно закрытых сделок для построения графика [{uid.upper()}].")

    @router.callback_query(F.data.startswith("analytics_ledger"))
    async def on_analytics_ledger(callback: CallbackQuery):
        uid = (callback.data.split(":")[-1] if ":" in callback.data else callback.data.replace("analytics_ledger_", "")) or _get_default_universe_id(bot_core)
        await callback.answer()
        if uid in ("all", "default"):
            consolidate_portfolio_ledger()
        suffix = f"_{uid}" if uid and uid != "default" else ""
        txt_path = ANALYTICS_DIR / f"trades_ledger{suffix}.txt"
        if not txt_path.exists():
            txt_path = ANALYTICS_DIR / "trades_ledger.txt"
        if txt_path.exists() and txt_path.stat().st_size > 60:
            await callback.message.answer_document(FSInputFile(str(txt_path)), caption=f"📄 <b>Журнал сделок [{uid.upper()}] (CSV/TXT)</b>", parse_mode="HTML")
        else:
            await callback.message.answer(f"⚠️ Журнал сделок для {uid.upper()} пока пуст.")

    @router.callback_query(F.data.startswith("analytics_ranking"))
    async def on_analytics_ranking(callback: CallbackQuery):
        await callback.answer()
        data_str = callback.data or ""
        if ":" in data_str:
            parts = data_str.split(":")
            uid = parts[1] if len(parts) > 1 else _get_default_universe_id(bot_core)
            sort_by = parts[2] if len(parts) > 2 else "profit"
        else:
            parts = data_str.split("_")
            uid = parts[2] if len(parts) >= 4 else _get_default_universe_id(bot_core)
            sort_by = parts[-1]

        data = _get_analytics_data(uid)
        per_coin = data.get("per_coin", {})
        kb = TGKeyboards.analytics_ranking_menu(uid)
        if not per_coin:
            await callback.message.edit_text(f"🏆 <b>Рейтинг монет [{uid.upper()}]:</b> пока нет закрытых сделок.", reply_markup=kb, parse_mode="HTML")
            return

        coin_items = [
            {"sym": s, "pnl": d.get("realized_pnl_usdt", 0.0), "trades": d.get("trades", 0), "wr": (d.get("win_count", 0) / d["trades"] * 100) if d.get("trades", 0) > 0 else 0.0}
            for s, d in per_coin.items() if d.get("trades", 0) > 0
        ]
        if sort_by == "trades":
            coin_items.sort(key=lambda x: x["trades"], reverse=True)
            title = f"📊 <b>Рейтинг монет [{uid.upper()}] по количеству сделок:</b>"
        elif sort_by == "winrate":
            coin_items.sort(key=lambda x: (x["wr"], x["trades"]), reverse=True)
            title = f"🎯 <b>Рейтинг монет [{uid.upper()}] по Winrate:</b>"
        else:
            coin_items.sort(key=lambda x: x["pnl"], reverse=True)
            title = f"💵 <b>Рейтинг монет [{uid.upper()}] по PnL:</b>"

        lines = [title, ""] + [f"{i}. <b>{x['sym']}</b>: {'+' if x['pnl'] >= 0 else ''}{x['pnl']:.2f}$ | {x['trades']} сд. | WR: {x['wr']:.1f}%" for i, x in enumerate(coin_items, 1)]
        await _send_or_edit_split_messages(callback, Utils.split_telegram_text(lines, max_len=4000), kb, "Ranking")

    @router.callback_query(F.data == "analytics_help")
    async def on_analytics_help(callback: CallbackQuery):
        await callback.answer()
        help_text = (
            "<b>ℹ️ Шпаргалка по показателям аналитики:</b>\n\n"
            "• <b>ROI (%)</b>: Доходность относительно стартового депозита.\n"
            "• <b>Net Profit</b>: Чистая прибыль с учетом комиссий.\n"
            "• <b>Realized PnL</b>: Суммарный закрытый результат по всем сделкам.\n"
            "• <b>Winrate (%)</b>: Процент прибыльных сделок от общего числа.\n"
            "• <b>Max Drawdown</b>: Максимальная историческая просадка баланса.\n"
            "• <b>Recovery Factor</b>: PnL / Max Drawdown.\n"
            "• <b>Leaderboard</b>: Сравнительная таблица всех 30 вселенных."
        )
        await callback.message.edit_text(help_text, reply_markup=TGKeyboards.leaderboard_menu(), parse_mode="HTML")

    @router.callback_query(F.data.startswith("analytics_set_balance_"))
    async def on_set_balance_btn(callback: CallbackQuery, state: FSMContext):
        uid = callback.data.replace("analytics_set_balance_", "")
        await callback.answer()
        await state.update_data(target_uid=uid)
        await state.set_state(AnalyticsStates.waiting_for_balance)
        await callback.message.answer(
            f"💰 <b>Введите стартовый баланс депозита [{uid.upper()}] в USDT</b> (например: <code>1000</code>):",
            parse_mode="HTML", reply_markup=TGKeyboards.back_reply()
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
        target_uid = state_data.get("target_uid", _get_default_universe_id(bot_core))
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
        await message.answer(f"✅ Стартовый баланс для [{target_uid.upper()}] установлен: <b>{val:.2f} USDT</b>", reply_markup=TGKeyboards.main_menu(is_paused), parse_mode="HTML")

    @router.callback_query(F.data.startswith("analytics_reset"))
    async def on_reset_prompt(callback: CallbackQuery, state: FSMContext):
        uid = (callback.data.split(":")[-1] if ":" in callback.data else callback.data.replace("analytics_reset_", "")) or _get_default_universe_id(bot_core)
        await callback.answer()
        await state.update_data(reset_target_uid=uid)
        await state.set_state(AnalyticsStates.waiting_for_reset_confirm)
        text = (
            f"⚠️ <b>ВНИМАНИЕ: Сброс аналитики для [{uid.upper()}]!</b>\n\n"
            "Удалит историю сделок, Ledger, график Equity и метрики по монетам.\n\n"
            "🛡 <b>Защита:</b> отправьте <code>СБРОС</code> в чат или запросите PIN ниже.\n"
            "<i>(Нажмите «Отмена», чтобы сохранить данные)</i>"
        )
        await callback.message.edit_text(text, reply_markup=TGKeyboards.confirm_reset_analytics(uid), parse_mode="HTML")

    @router.callback_query(F.data.startswith("reset_req_pin"))
    async def on_reset_req_pin(callback: CallbackQuery, state: FSMContext):
        await callback.answer()
        uid = (callback.data.split(":")[-1] if ":" in callback.data else "") or _get_default_universe_id(bot_core)
        pin = random.randint(1000, 9999)
        decoys = {random.randint(1000, 9999) for _ in range(10) if _ != pin}
        opts = list(list(decoys)[:2]) + [pin]
        random.shuffle(opts)
        await state.update_data(reset_pin=pin, reset_target_uid=uid)
        await callback.message.edit_text(
            f"🔐 <b>Защитная проверка сброса [{uid.upper()}]</b>\n\nДля подтверждения нажмите кнопку с PIN: <b>[{pin}]</b>\n<i>(Другой PIN отменит операцию)</i>",
            reply_markup=TGKeyboards.confirm_reset_pin_menu(uid, pin, opts), parse_mode="HTML"
        )

    @router.callback_query(F.data.startswith("reset_pin_fail"))
    async def on_reset_pin_fail(callback: CallbackQuery, state: FSMContext):
        await state.clear()
        await callback.answer("❌ Неверный код! Сброс отменен.", show_alert=True)
        uid = (callback.data.split(":")[-1] if ":" in callback.data else "") or _get_default_universe_id(bot_core)
        text = _format_analytics_text(_get_analytics_data(uid), bot_core=bot_core, universe_id=uid)
        await callback.message.edit_text(f"🛡 <b>Сброс отменен.</b> Неверный защитный код. Данные [{uid.upper()}] сохранены.\n\n" + text, reply_markup=TGKeyboards.analytics_menu(uid), parse_mode="HTML")

    @router.callback_query(F.data.startswith("reset_pin_ok"))
    async def on_reset_pin_ok(callback: CallbackQuery, state: FSMContext):
        await callback.answer("Сброс выполняется...")
        uid = callback.data.split(":")[1] if ":" in callback.data else _get_default_universe_id(bot_core)
        await state.clear()
        _do_reset_analytics(uid, bot_core=bot_core)
        disp_uid = "ВСЕ СТРАТЕГИИ" if uid == "all" else uid.upper()
        text = _format_analytics_text(_get_analytics_data(uid), bot_core=bot_core, universe_id=uid)
        await callback.message.edit_text(f"✅ <b>Аналитика и журнал сделок для [{disp_uid}] успешно сброшены.</b>\n\n" + text, reply_markup=TGKeyboards.analytics_menu(uid), parse_mode="HTML")

    @router.callback_query(F.data.startswith("reset_analytics_confirm"))
    async def on_reset_confirm_legacy(callback: CallbackQuery, state: FSMContext):
        await callback.answer()
        uid = callback.data.replace("reset_analytics_confirm_", "").replace("reset_analytics_confirm:", "") or _get_default_universe_id(bot_core)
        await state.clear()
        _do_reset_analytics(uid, bot_core=bot_core)
        disp_uid = "ВСЕ СТРАТЕГИИ" if uid == "all" else uid.upper()
        text = _format_analytics_text(_get_analytics_data(uid), bot_core=bot_core, universe_id=uid)
        await callback.message.edit_text(f"✅ <b>Аналитика для [{disp_uid}] успешно сброшена.</b>\n\n" + text, reply_markup=TGKeyboards.analytics_menu(uid), parse_mode="HTML")

    @router.message(AnalyticsStates.waiting_for_reset_confirm)
    async def on_reset_text_confirm(message: Message, state: FSMContext):
        text = (message.text or "").strip().upper()
        data = await state.get_data()
        uid = data.get("reset_target_uid", _get_default_universe_id(bot_core))
        await state.clear()
        paused = getattr(bot_core, "is_paused", True)
        disp_uid = "ВСЕ СТРАТЕГИИ" if uid == "all" else uid.upper()
        if text in ["СБРОС", "RESET", f"СБРОС {disp_uid}", f"RESET {disp_uid}", "СБРОС ALL", "RESET ALL"]:
            _do_reset_analytics(uid, bot_core=bot_core)
            await message.answer(f"✅ <b>Аналитика и журнал сделок для [{disp_uid}] успешно сброшены.</b>", reply_markup=TGKeyboards.main_menu(paused), parse_mode="HTML")
        else:
            await message.answer(f"🛡 Сброс аналитики для [{disp_uid}] <b>отменен</b>.", reply_markup=TGKeyboards.main_menu(paused), parse_mode="HTML")
