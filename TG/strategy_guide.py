# ============================================================
# FILE: TG/strategy_guide.py
# ROLE: Strategy cheat sheet, documentation & proven leaders badge engine
# ============================================================

from typing import Dict, Any, List, Optional
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from c_log import UnifiedLogger

logger = UnifiedLogger("StrategyGuide")

PROVEN_LEADERS = {
    "u3_anti_trend": {
        "rank": "🥇",
        "badge": " 💎 [PROVEN LEADER]",
        "stats": "34 сд. | WR: 70.6% | Realized: +17.49$ | Net: +14.03$"
    },
    "u15_anti_fade": {
        "rank": "🥈",
        "badge": " 💎 [PROVEN LEADER]",
        "stats": "65 сд. | WR: 61.5% | Realized: +7.67$ | Net: -0.47$"
    }
}


def is_proven_leader(uid: str) -> bool:
    """Проверяет, входит ли стратегия в топ-2 доказанных лидеров реальных торгов."""
    return uid in PROVEN_LEADERS


def get_leader_badge(uid: str) -> str:
    """Возвращает специальный маркер лидера для отображения в заголовках и списках."""
    leader = PROVEN_LEADERS.get(uid)
    return leader["badge"] if leader else ""


STRATEGY_DESCRIPTIONS: Dict[str, Dict[str, str]] = {
    "u3_anti_trend": {
        "name": "Trend-Aligned Pullback Fade 🥇",
        "concept": "<b>Покупка откатов по старшему тренду.</b> Стратегия ловит ложные пробои уровней на M5 (fade) СТРОГО в направлении глобального тренда H1. Это позволяет заходить по лучшим ценам с минимальным риском.",
        "entry": "• <b>HTF Trend (1h)</b>: EMA(10) > EMA(30) + подтверждение 2 свечи.\n• <b>S/R Anti (5m)</b>: Ложный пробой уровня против тренда.\n• <b>Volume Filter (1m)</b>: Всплеск тикового объема (slice_factor > 1.1).",
        "exit": "• <b>Take Profit</b>: +3.5%\n• <b>Stop Loss</b>: -2.0%\n• <b>Trend Reversal</b>: Немедленный выход при сломе тренда H1 (переход в FLAT или разворот).",
        "note": "🏆 <b>Лидер #1 реальных торгов</b>: 70.6% винрейт, чистая прибыль +14.03 USDT."
    },
    "u15_anti_fade": {
        "name": "Pure Liquidity Fade (Range Return) 🥈",
        "concept": "<b>Сбор ликвидности на ложных импульсах.</b> Вход в контртренд, когда маркет-мейкер выносит стопы за экстремумы, а поток маркет-ордеров (Taker Flow) резко истощается.",
        "entry": "• <b>S/R Anti (5m)</b>: Вынос за границу диапазона (Swing Length 15, Margin 2.0).\n• <b>Taker Flow Anti (5m)</b>: Доминирование противоположной стороны (покупка при падении агрессии продавцов).",
        "exit": "• <b>Take Profit</b>: +2.5%\n• <b>Stop Loss</b>: -2.5%\n• <b>Time Stop</b>: Закрытие через 20 минут (1200 сек), если цена не пошла в плюс.",
        "note": "🥈 <b>Лидер #2 реальных торгов</b>: 61.5% винрейт на 65 сделках, около безубытка с комиссиями."
    },
    "u3_anti_opt": {
        "name": "Volume Fade (Noise-Filtered & Optimized) 🎯",
        "concept": "<b>Оптимизированный сбор ликвидности на объемах.</b> Устраняет проблему комиссионного перегруза u3_anti_aggr: фильтр объема загрублен до 1.4 (отсекает 65% шума), TP поднят до 3.2%, добавлен кулдаун 3 мин.",
        "entry": "• <b>S/R Anti (5m)</b>: Ложный пробой зоны уровня.\n• <b>Volume Filter (1m)</b>: Всплеск объема (slice_factor > 1.4).\n• <b>Re-entry Cooldown</b>: 180 сек.",
        "exit": "• <b>Take Profit</b>: +3.2% | <b>Stop Loss</b>: -2.5%\n• <b>Trend Reversal Anti</b>: Выход при закреплении истинного пробоя.",
        "note": "🎯 <b>Оптимизация</b>: За счет роста TP и фильтрации шума снижает комиссии в 3 раза, превращая валовый перевес в чистый плюс."
    },
    "u3_anti_aggr": {
        "name": "Aggressive Volume Fade ⚠️",
        "concept": "<b>Агрессивный скальпинг перерастяжек.</b> Вход на минутном объеме против микро-пробоя M5. Паттерн показал высокий Gross (+18.29$), но из-за короткого TP 1.8% и 251 сделки комиссии съели весь результат.",
        "entry": "• <b>S/R Anti (5m)</b>: Ложный импульс за локальный уровень.\n• <b>Volume Filter (1m)</b>: Импульсный объем (slice_factor > 1.1).",
        "exit": "• <b>Take Profit</b>: +1.8% | <b>Stop Loss</b>: -3.0%\n• <b>Trend Reversal Anti</b>: Выход при закреплении пробоя.",
        "note": "⚠️ <b>Высокий оборот (High Churn)</b>: 251 сд., Net: -7.82$. Комиссии ($26.11) превысили валовую прибыль. Не является лидером!"
    },
    "u_hvh_pullback": {
        "name": "HVH Mean-Reversion Pullback 🆕",
        "concept": "<b>Откат волатильности к средней по старшему тренду.</b> Когда цена на 15m перерастягивается за полосы HVH против тренда 1h и сеточник застрял, бот выкупает откат в сторону тренда.",
        "entry": "• <b>HTF Trend (1h)</b>: Подтвержденный тренд H1 (UP для лонга, DOWN для шорта).\n• <b>HVH (15m)</b>: Цена коснулась границы полосы HVH (dev=1.8, mode=rolling, pullback).\n• <b>Grid Stress</b>: Сетка сеточника набрала >= 3 уровней и 50% объема.",
        "exit": "• <b>Chandelier Exit</b>: Трейлинг 3.0x ATR от точки входа.\n• <b>Take Profit</b>: +8.0% | <b>Stop Loss</b>: -3.0%\n• <b>Trend Reversal</b>: Выход при переходе тренда H1 в FLAT.",
        "note": "⭐ <b>Новая стратегия</b>: Описана в tech_debt.md для взятия крупных трендовых движений."
    },
    "u_hvh_impulse": {
        "name": "Pure Impulse HVH Breakout 🆕",
        "concept": "<b>Пробой взрывной волатильности (Momentum).</b> Вход в сторону сильного безоткатного движения, пробивающего адаптивный канал HVH и продавливающего сетку сеточника.",
        "entry": "• <b>HVH (5m)</b>: Импульсный пробой границы канала HVH (dev=2.0, mode=rolling, impulse).\n• <b>Taker Flow (5m)</b>: Агрессивное доминирование покупателей (>60%) или продавцов (<40%).\n• <b>Grid Stress</b>: Застревание противоположной сетки (filled >= 3).",
        "exit": "• <b>Chandelier Exit</b>: Динамический трейлинг-стоп 2.5x ATR.\n• <b>Take Profit</b>: +6.0% | <b>Stop Loss</b>: -2.5%",
        "note": "⚡ <b>Новая стратегия</b>: Забирает импульсы, на которых сеточник уходит в просадку."
    },
    "u1": {
        "name": "Dual EMA Trend Follower",
        "concept": "<b>Классический тренд-следящий алгоритм.</b> Торговля по наклону двух EMA на M5 с фильтрацией ложных колебаний свечами подтверждения.",
        "entry": "• <b>Trend (5m)</b>: Быстрая EMA(10) выше медленной EMA(30) + 3 подтверждающих бара.",
        "exit": "• <b>Trend Reversal</b>: Смена направления EMA.\n• <b>Take Profit</b>: +5.0% | <b>Stop Loss</b>: -3.0%",
        "note": "Базовый эталон трендового ядра TrendH."
    },
    "u2": {
        "name": "EMA Trend + RSI Momentum",
        "concept": "<b>Трендовый импульс с фильтрацией флэта по RSI.</b> Вход только когда тренд подтверждается нахождением RSI в зоне активного движения (50–70 для лонга).",
        "entry": "• <b>Trend (5m)</b>: EMA(10) > EMA(30).\n• <b>RSI (5m)</b>: В диапазоне от 50 до 70 (LONG) или 30 до 50 (SHORT).",
        "exit": "• <b>Trend Reversal</b>: Смена тренда EMA.\n• <b>Take Profit</b>: +5.0% | <b>Stop Loss</b>: -3.0%",
        "note": "Исключает входы в перекупленности и глубокой перепроданности."
    },
    "u3": {
        "name": "Trend + Volume Breakout",
        "concept": "<b>Тренд с подтверждением объема.</b> Вход по тренду 5m только при превышении среднестатистического объема свечи.",
        "entry": "• <b>Trend (5m)</b>: EMA(10) > EMA(30).\n• <b>Volume Filter (1m)</b>: Объем выше порога slice_factor.",
        "exit": "• <b>Trend Reversal</b>: Переход в FLAT/DOWN.\n• <b>Take Profit</b>: +4.5% | <b>Stop Loss</b>: -2.5%",
        "note": "Отсекает вялотекущие движения без институционального интереса."
    },
    "u4": {
        "name": "Trend + Support/Resistance Breakout",
        "concept": "<b>Пробой уровней поддержки/сопротивления по тренду.</b> Вход при истинном пробое ценового уровня в сторону тренда.",
        "entry": "• <b>Trend (5m)</b>: EMA(10) > EMA(30).\n• <b>S/R Levels (5m)</b>: Пробой зоны сопротивления (LONG) или поддержки (SHORT).",
        "exit": "• <b>Trend Reversal</b> + <b>Take Profit</b>: +5.0% | <b>Stop Loss</b>: -2.5%",
        "note": "Минимизирует риск застревания в середине ценового диапазона."
    },
    "u5": {
        "name": "Trend + EMA Cross Trigger",
        "concept": "<b>Момент пересечения скользящих средних.</b> Вход ровно в момент смены тренда на пересечении EMA.",
        "entry": "• <b>EMA Cross (5m)</b>: Свежее пересечение быстрой и медленной EMA.",
        "exit": "• <b>Trend Reversal</b> + <b>Take Profit</b>: +4.0% | <b>Stop Loss</b>: -2.0%",
        "note": "Ловит самое начало зарождающегося трендового движения."
    },
    "u6": {
        "name": "S/R Breakout + RSI Impulse",
        "concept": "<b>Импульсный пробой диапазона с ускорением RSI.</b> Пробой уровня, поддержанный сильным импульсом RSI выше 55/ниже 45.",
        "entry": "• <b>S/R Levels (5m)</b>: Пробой границы уровня.\n• <b>RSI (5m)</b>: Нахождение в импульсной зоне.",
        "exit": "• <b>Take Profit</b>: +4.5% | <b>Stop Loss</b>: -2.5%",
        "note": "Высокая динамика, чистый ценовой экшн."
    },
    "u7": {
        "name": "Multi-Filter Quad Trend",
        "concept": "<b>Квадро-фильтр высокой надежности.</b> Требует одновременного совпадения тренда 5m, тренда H1, объема и RSI.",
        "entry": "• <b>Trend (5m)</b> + <b>HTF Trend (1h)</b> + <b>Volume (1m)</b> + <b>RSI (5m)</b>.",
        "exit": "• <b>Trend Reversal</b> + <b>Take Profit</b>: +6.0% | <b>Stop Loss</b>: -2.5%",
        "note": "Редкие, но максимально выверенные входы."
    },
    "u8": {
        "name": "Grid Stress Relief Overlay",
        "concept": "<b>Снятие стресса сеточника (Хедж).</b> Автоматическое открытие контр-позиции, когда сетка набрала опасный объем.",
        "entry": "• <b>Grid Stress</b>: Набор сеткой >= 3 уровней и >= 55% объема.",
        "exit": "• <b>Grid Relief</b>: Сетка разгрузилась до < 15% объема или закрылась по TP.\n• <b>Stop Loss</b>: -5.0%",
        "note": "Специальный симбиотический модуль защиты сетки cron3."
    },
    "u15": {
        "name": "Pure Breakout Sniper",
        "concept": "<b>Автономный снайпер пробоев уровней.</b> Торгует пробои консолидаций с подтверждением HTF тренда H1.",
        "entry": "• <b>HTF Trend (1h)</b>: Тренд H1.\n• <b>S/R Levels (5m)</b>: Пробой уровня с плотностью thickness_k=0.17.\n• <b>Taker Flow (5m)</b>: Taker Buy > 60%.",
        "exit": "• <b>Chandelier Exit</b>: 2.2x ATR\n• <b>Time Stop</b>: 1200 сек\n• <b>TP</b>: +4.5% | <b>SL</b>: -2.0%",
        "note": "Институциональный пробойный сетап."
    },
    "u15_cons": {
        "name": "Conservative Breakout Sniper",
        "concept": "<b>Консервативный снайпер.</b> Повышенные требования к потоку ордеров (Taker Buy >= 65%) и увеличенный отступ уровня.",
        "entry": "• <b>HTF Trend (1h)</b> + <b>S/R Levels (margin 2.5)</b> + <b>Taker Flow >= 65%</b>.",
        "exit": "• <b>Chandelier Exit</b>: 2.0x ATR | <b>TP</b>: +4.0% | <b>SL</b>: -1.8%",
        "note": "Максимально жесткий отбор качественных пробоев."
    },
    "u16": {
        "name": "Institutional Order Flow Follower",
        "concept": "<b>Следование за потоком рыночных покупок/продаж.</b> Вход при явном перевесе маркет-агрессоров без ожидания уровней.",
        "entry": "• <b>HTF Trend (1h)</b> + <b>Taker Flow (5m)</b>: Taker Buy > 62%.",
        "exit": "• <b>Chandelier Exit</b>: 2.5x ATR | <b>TP</b>: +5.0% | <b>SL</b>: -2.5%",
        "note": "Использует живой WebSocket-поток реальных сделок."
    },
    "u17": {
        "name": "Volatility Squeeze Breakout",
        "concept": "<b>Выстрел из сжатия волатильности (Squeeze).</b> Полосы Боллинджера сужаются внутри каналов Кельтнера, накапливая энергию.",
        "entry": "• <b>HTF Trend (1h)</b> + <b>Volatility Squeeze (5m)</b>: Разжатие пружины (SQUEEZE_LONG / SHORT).",
        "exit": "• <b>Chandelier Exit</b>: 2.5x ATR | <b>TP</b>: +5.5% | <b>SL</b>: -2.5%",
        "note": "Классическая институциональная модель Джона Картера."
    },
    "u18": {
        "name": "Squeeze + Taker Flow Synergy",
        "concept": "<b>Синергия сжатия и потока ордеров.</b> Разжатие пружины волатильности, подтвержденное притоком маркет-покупок.",
        "entry": "• <b>HTF Trend (1h)</b> + <b>Squeeze (5m)</b> + <b>Taker Flow (5m) > 60%</b>.",
        "exit": "• <b>Chandelier Exit</b>: 2.5x ATR | <b>TP</b>: +6.0% | <b>SL</b>: -2.5%",
        "note": "Высокая вероятность продолжения импульса."
    },
    "u19": {
        "name": "Relative Strength vs BTC Momentum",
        "concept": "<b>Опережающая сила монеты к Биткоину.</b> Покупка альткоинов, растущих сильнее BTC, и шорт слабейших альткоинов.",
        "entry": "• <b>HTF Trend (1h)</b> + <b>Relative Strength (5m)</b>: Альфа к BTC > 1.2% за 12 свечей.",
        "exit": "• <b>Chandelier Exit</b>: 2.2x ATR | <b>TP</b>: +5.0% | <b>SL</b>: -2.2%",
        "note": "Выбирает лидеров рынка для направленной торговли."
    }
}


def format_strategy_guide_text(uid: str, bot_core=None) -> str:
    """Форматирует подробную шпаргалку по выбранной стратегии."""
    info = STRATEGY_DESCRIPTIONS.get(uid)
    if not info:
        name = uid.upper()
        if bot_core and hasattr(bot_core, "universe_manager"):
            univ = bot_core.universe_manager.get_universe(uid)
            if univ:
                name = univ.name
        return f"<b>📖 Стратегия [{uid.upper()}]: {name}</b>\n\n<i>Описание параметров доступно в cfg.json</i>"

    badge = get_leader_badge(uid)
    leader_info = PROVEN_LEADERS.get(uid)
    proven_block = ""
    if leader_info:
        proven_block = f"\n💎 <b>РЕАЛЬНЫЕ РЕЗУЛЬТАТЫ:</b> <code>{leader_info['stats']}</code>\n"

    return (
        f"📖 <b>ШПАРГАЛКА: {info['name'].upper()}{badge}</b>\n"
        f"{proven_block}\n"
        f"📌 <b>Суть и идея стратегии:</b>\n{info['concept']}\n\n"
        f"🟢 <b>Правила входа (Entry Rules):</b>\n{info['entry']}\n\n"
        f"🔴 <b>Правила выхода (Exit Rules):</b>\n{info['exit']}\n\n"
        f"💡 <b>Примечание:</b>\n<i>{info['note']}</i>"
    )


def strategy_guide_keyboard(universes: List[Any], current_uid: str = "all") -> InlineKeyboardMarkup:
    """Клавиатура выбора стратегии для просмотра шпаргалки."""
    buttons = []
    # Сначала проверенные лидеры
    leader_row = []
    for l_uid, l_data in PROVEN_LEADERS.items():
        leader_row.append(InlineKeyboardButton(
            text=f"{l_data['rank']} {l_uid.upper()} 💎",
            callback_data=f"strat_guide_detail:{l_uid}"
        ))
    if leader_row:
        buttons.append(leader_row)

    # Остальные стратегии
    row = []
    for u in universes:
        uid = u["uid"] if isinstance(u, dict) else (getattr(u, "universe_id", None) or getattr(u, "uid", str(u)))
        if uid in PROVEN_LEADERS or uid in ("all", "default"):
            continue
        tag = " 🆕" if "hvh" in uid.lower() else ""
        row.append(InlineKeyboardButton(text=f"{uid.upper()}{tag}", callback_data=f"strat_guide_detail:{uid}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([InlineKeyboardButton(text="🔙 Назад в Аналитику", callback_data=f"analytics_univ_{current_uid}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def strategy_guide_detail_keyboard(uid: str) -> InlineKeyboardMarkup:
    """Клавиатура карточки шпаргалки с кнопкой возврата в список шпаргалок."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Аналитика стратегии", callback_data=f"analytics_univ_{uid}"),
            InlineKeyboardButton(text="📈 Equity", callback_data=f"analytics_equity:{uid}")
        ],
        [
            InlineKeyboardButton(text="📑 Все стратегии (Справочник)", callback_data="strat_guide_menu:all"),
            InlineKeyboardButton(text="🔙 Главная аналитика", callback_data="analytics_back")
        ]
    ])


def register_strategy_guide_handlers(router: Router, bot_core):
    """Регистрирует маршруты интерактивного справочника стратегий."""

    @router.callback_query(F.data.startswith("strat_guide_menu"))
    async def on_guide_menu(callback: CallbackQuery):
        await callback.answer()
        data_str = callback.data or ""
        cur_uid = data_str.split(":")[-1] if ":" in data_str else "all"
        board = bot_core.universe_manager.get_leaderboard(bot_core.current_prices) if hasattr(bot_core, "universe_manager") else []
        text = (
            "<b>📖 СПРАВОЧНИК И ШПАРГАЛКА ПО СТРАТЕГИЯМ</b>\n\n"
            "<i>Выберите стратегию, чтобы узнать логику входа, условия выхода и результаты:</i>\n\n"
            "💎 — <b>Проверенные лидеры реальных торгов</b>\n"
            "🆕 — <b>Новые адаптивные HVH-стратегии</b>"
        )
        await callback.message.edit_text(
            text,
            reply_markup=strategy_guide_keyboard(board, current_uid=cur_uid),
            parse_mode="HTML"
        )

    @router.callback_query(F.data.startswith("strat_guide_detail:"))
    async def on_guide_detail(callback: CallbackQuery):
        await callback.answer()
        uid = callback.data.split(":")[1]
        text = format_strategy_guide_text(uid, bot_core=bot_core)
        await callback.message.edit_text(
            text,
            reply_markup=strategy_guide_detail_keyboard(uid),
            parse_mode="HTML"
        )
