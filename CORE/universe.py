# ============================================================
# FILE: universe.py
# ROLE: Multi-Strategy Parallel Universe Engine & State Isolation
# ============================================================

import json
import time
from typing import Dict, Any, Optional, List, Callable
from pathlib import Path

from c_log import log
from CORE.models import PositionState
from CORE.rules import EntrySignalEngine, ExitSignalEngine
from ANALYTICS.analytics import AnalyticsManager
from ANALYTICS.metrics import AnalyticsMathEngine
from consts import DATA_DIR, ANALYTICS_CFG


class UniverseState:
    """
    Изолированное состояние позиций для конкретной торговой вселенной.
    Сохраняет состояние в logs/data/state_{universe_id}.json.
    """

    def __init__(self, universe_id: str = "default", backup_manager=None):
        self.universe_id = universe_id
        self.backup_manager = backup_manager
        # symbol -> {"LONG": PositionState, "SHORT": PositionState}
        self.positions: Dict[str, Dict[str, PositionState]] = {}

    def get_state_path(self) -> Path:
        suffix = f"_{self.universe_id}" if self.universe_id and self.universe_id != "default" else ""
        return DATA_DIR / f"state{suffix}.json"

    def load_state(self):
        path = self.get_state_path()
        if not path.exists():
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for sym, sides in data.items():
                if sym not in self.positions:
                    self.positions[sym] = {
                        "LONG": PositionState(symbol=sym, side="LONG"),
                        "SHORT": PositionState(symbol=sym, side="SHORT")
                    }
                for side, pos_dict in sides.items():
                    if pos_dict.get("is_active"):
                        pos = self.positions[sym][side]
                        pos.is_active = True
                        pos.open_price = float(pos_dict.get("open_price", 0.0))
                        pos.size = float(pos_dict.get("size", 0.0))
            active_cnt = sum(1 for sym, s in self.positions.items() for side, pos in s.items() if pos.is_active)
            if active_cnt > 0:
                log(f"[{self.universe_id}] Восстановлено {active_cnt} активных позиций из {path.name}", level="INFO")
            else:
                log(f"[{self.universe_id}] Загружен стейт из {path.name} (0 активных позиций)", level="DEBUG")
        except Exception as e:
            log(f"[{self.universe_id}] Ошибка загрузки стейта: {e}", level="ERROR")

    def save_state(self):
        path = self.get_state_path()
        try:
            data = {}
            for sym, sides in self.positions.items():
                data[sym] = {
                    "LONG": sides["LONG"].__dict__,
                    "SHORT": sides["SHORT"].__dict__
                }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            if self.backup_manager:
                self.backup_manager.mark_changed()
        except Exception as e:
            log(f"[{self.universe_id}] Ошибка сохранения стейта: {e}", level="ERROR")

    def get_position(self, symbol: str, side: str) -> Optional[PositionState]:
        pos = self.positions.get(symbol, {}).get(side)
        if pos and pos.is_active:
            return pos
        return None

    def open_position(self, symbol: str, side: str, price: float, size: float):
        if symbol not in self.positions:
            self.positions[symbol] = {
                "LONG": PositionState(symbol=symbol, side="LONG"),
                "SHORT": PositionState(symbol=symbol, side="SHORT")
            }
        now_ms = int(time.time() * 1000)
        self.positions[symbol][side].set_active(price, size, now_ms)
        self.save_state()

    def close_position(self, symbol: str, side: str):
        if symbol in self.positions and side in self.positions[symbol]:
            self.positions[symbol][side].reset()
            self.save_state()


class StrategyUniverse:
    """
    Автономная торговая вселенная (стратегия).
    Объединяет собственные правила входа, выхода, стейт и аналитику.
    """

    def __init__(
        self,
        universe_id: str,
        name: str,
        description: str,
        enter_rules: Dict[str, Any],
        exit_rules: Dict[str, Any],
        get_slippage_ratio_fn: Callable[[str], float],
        is_active: bool = True,
        backup_manager=None
    ):
        self.universe_id = universe_id
        self.name = name
        self.description = description
        self.is_active = is_active
        self.enter_rules = enter_rules
        self.exit_rules = exit_rules

        self.entry_engine = EntrySignalEngine(enter_rules)
        self.exit_engine = ExitSignalEngine(exit_rules, ANALYTICS_CFG, get_slippage_ratio_fn)
        self.state = UniverseState(universe_id=universe_id, backup_manager=backup_manager)
        self.analytics = AnalyticsManager(universe_id=universe_id)
        self.state.load_state()

    def check_entry(self, side: str, indicators: Dict[str, Any]) -> bool:
        return self.entry_engine.check_signal(side, indicators)

    def check_exit(self, side: str, symbol: str, open_price: float, current_price: float, indicators: Dict[str, Any], open_time_ms: Optional[int] = None) -> bool:
        trend = indicators.get("trend", "UNSTABLE")
        return self.exit_engine.check_signal(
            side=side,
            symbol=symbol,
            trend=trend,
            open_price=open_price,
            current_price=current_price,
            indicators=indicators,
            open_time_ms=open_time_ms
        )

    def process_tick(
        self,
        symbol: str,
        side: str,
        current_price: float,
        indicators: Dict[str, Any],
        get_slippage_ratio_fn: Callable[[str], float],
        is_paused: bool,
        invest_size: float
    ):
        """Обрабатывает тик цены для конкретной валютной пары и стороны."""
        pos = self.state.get_position(symbol, side)
        if pos:
            # Проверка условий выхода (Take Profit, Stop Loss, Trend Reversal, Time Stop)
            should_exit = self.check_exit(side, symbol, pos.open_price, current_price, indicators, open_time_ms=pos.open_time)
            if should_exit:
                fee_ratio = ANALYTICS_CFG.get("taker_fee_ratio", 0) * 2
                slippage_ratio = get_slippage_ratio_fn(symbol) * 2
                fee_slip_ratio = fee_ratio + slippage_ratio

                if side == "LONG":
                    pnl_ratio = (current_price - pos.open_price) / pos.open_price
                else:
                    pnl_ratio = (pos.open_price - current_price) / pos.open_price

                pnl_usd = pnl_ratio * pos.size
                comm_usd = -(fee_slip_ratio * pos.size)
                pnl_pct = pnl_ratio * 100

                log(
                    f"[SIGNAL EXIT] [{self.universe_id}][{symbol}][{side}] Выход! Вход: {pos.open_price:.4f} -> {current_price:.4f} | PnL: {pnl_pct:+.2f}% ({pnl_usd:+.2f}$)",
                    level="INFO"
                )
                self.analytics.record_virtual_trade(symbol, side, pnl_usd, comm_usd, open_time_ms=pos.open_time)
                self.state.close_position(symbol, side)
        else:
            # Проверка условий входа
            if not is_paused and self.check_entry(side, indicators):
                rsi_val = indicators.get("rsi_value")
                rsi_str = f"{rsi_val:.1f}" if rsi_val is not None else "N/A"
                htf_str = f", HTF: {indicators.get('trend_htf')}" if "trend_htf" in indicators else ""
                sr_states = indicators.get("sr_levels", [])
                sr_str = f", SR: {','.join(sr_states)}" if sr_states else ""
                ec_states = indicators.get("ema_cross", [])
                ec_str = f", EMACross: {','.join(ec_states)}" if ec_states else ""
                vol_states = indicators.get("vol_filter", [])
                vol_str = f", VolF: {','.join(vol_states)}" if vol_states else ""

                grid_str = ""
                stress_info = indicators.get("grid_stress")
                if stress_info and isinstance(stress_info, dict):
                    st_side = "SHORT" if side == "LONG" else "LONG"
                    s_data = stress_info.get(st_side, {})
                    if s_data.get("in_position"):
                        grid_str = (
                            f", Cron3[{st_side}]: vol={s_data.get('volume_ratio', 0.0):.1%}, "
                            f"lvl={s_data.get('max_level', -1)}/5, avg={s_data.get('avg_entry_price', 0.0):.4f}, "
                            f"dd={s_data.get('drawdown_pct', 0.0):+.2f}%, status={stress_info.get('status')}"
                        )

                log(
                    f"[SIGNAL ENTRY] [{self.universe_id}][{symbol}][{side}] Trend: {indicators.get('trend')}{htf_str}, RSI: {rsi_str}{sr_str}{ec_str}{vol_str}{grid_str}",
                    level="INFO"
                )
                if invest_size > 0:
                    log(f"[POSITION OPEN] [{self.universe_id}][{symbol}][{side}] Цена: {current_price}, Размер: {invest_size}${grid_str}", level="INFO")
                    self.state.open_position(symbol, side, current_price, invest_size)
                else:
                    log(f"[SIGNAL SKIPPED] [{self.universe_id}][{symbol}][{side}] Пропуск входа: размер позиции 0 (сетка cron3 не активна)", level="INFO", throttle_sec=30)

    def close_all_positions(self, current_prices: Dict[str, float], get_slippage_ratio_fn: Callable[[str], float]) -> int:
        """Экстренное закрытие всех позиций вселенной."""
        closed_count = 0
        for symbol, sides in list(self.state.positions.items()):
            for side, pos in list(sides.items()):
                if not pos.is_active:
                    continue
                current_price = current_prices.get(symbol)
                if not current_price:
                    continue

                fee_ratio = ANALYTICS_CFG.get("taker_fee_ratio", 0) * 2
                slippage_ratio = get_slippage_ratio_fn(symbol) * 2
                fee_slip_ratio = fee_ratio + slippage_ratio

                if side == "LONG":
                    pnl_ratio = (current_price - pos.open_price) / pos.open_price
                else:
                    pnl_ratio = (pos.open_price - current_price) / pos.open_price

                pnl_usd = pnl_ratio * pos.size
                comm_usd = -(fee_slip_ratio * pos.size)

                self.analytics.record_virtual_trade(symbol, side, pnl_usd, comm_usd, open_time_ms=pos.open_time)
                self.state.close_position(symbol, side)
                closed_count += 1
        return closed_count


class UniverseManager:
    """
    Менеджер параллельных вселенных (стратегий).
    Координирует работу нескольких изолированных StrategyUniverse.
    """

    def __init__(
        self,
        universes_cfg: Dict[str, Any],
        default_enter_rules: Dict[str, Any],
        default_exit_rules: Dict[str, Any],
        get_slippage_ratio_fn: Callable[[str], float],
        backup_manager=None
    ):
        self.universes: Dict[str, StrategyUniverse] = {}
        self.backup_manager = backup_manager

        if universes_cfg:
            for uid, udata in universes_cfg.items():
                if not udata.get("is_active", True):
                    continue
                name = udata.get("name", uid)
                desc = udata.get("description", "")
                enter_rules = udata.get("enter_rules", default_enter_rules)
                exit_rules = udata.get("exit_rules", default_exit_rules)
                self.universes[uid] = StrategyUniverse(
                    universe_id=uid,
                    name=name,
                    description=desc,
                    enter_rules=enter_rules,
                    exit_rules=exit_rules,
                    get_slippage_ratio_fn=get_slippage_ratio_fn,
                    is_active=True,
                    backup_manager=backup_manager
                )
        else:
            # Одиночная вселенная по умолчанию
            self.universes["default"] = StrategyUniverse(
                universe_id="default",
                name="Default Strategy",
                description="Единая стратегия по умолчанию",
                enter_rules=default_enter_rules,
                exit_rules=default_exit_rules,
                get_slippage_ratio_fn=get_slippage_ratio_fn,
                is_active=True,
                backup_manager=backup_manager
            )

    def get_combined_enter_rules(self) -> Dict[str, Any]:
        """
        Объединяет правила входа и выхода всех активных вселенных, чтобы IndicatorsEngine
        мог централизованно рассчитать все необходимые таймфреймы и индикаторы.
        """
        combined: Dict[str, Any] = {}
        for universe in self.universes.values():
            for key, val in universe.enter_rules.items():
                if isinstance(val, dict) and val.get("is_active"):
                    if key not in combined:
                        combined[key] = dict(val)
                    else:
                        combined[key]["is_active"] = True
                    for suffix in ("_anti", "_reverse", "_inv"):
                        if key.endswith(suffix):
                            base_key = key[:-len(suffix)]
                            if base_key not in combined:
                                combined[base_key] = dict(val)
                            else:
                                combined[base_key]["is_active"] = True
                            break
            for key, val in universe.exit_rules.items():
                base_exit = key
                for suffix in ("_anti", "_reverse", "_inv"):
                    if key.endswith(suffix):
                        base_exit = key[:-len(suffix)]
                        break
                if base_exit == "rsi" and isinstance(val, dict) and val.get("is_active"):
                    if "rsi" not in combined:
                        combined["rsi"] = {
                            "is_active": True,
                            "timeframe": val.get("timeframe", "5m"),
                            "window": val.get("window", 14),
                            "conditions": {}
                        }
                    else:
                        combined["rsi"]["is_active"] = True
        return combined

    def get_universe(self, uid: str) -> Optional[StrategyUniverse]:
        return self.universes.get(uid)

    def get_all_universes(self) -> List[StrategyUniverse]:
        return list(self.universes.values())

    def process_tick(
        self,
        symbol: str,
        side: str,
        current_price: float,
        indicators: Dict[str, Any],
        get_slippage_ratio_fn: Callable[[str], float],
        is_paused: bool,
        invest_size: float
    ):
        """Раздает тик во все активные вселенные параллельно."""
        for universe in self.universes.values():
            if universe.is_active:
                universe.process_tick(
                    symbol=symbol,
                    side=side,
                    current_price=current_price,
                    indicators=indicators,
                    get_slippage_ratio_fn=get_slippage_ratio_fn,
                    is_paused=is_paused,
                    invest_size=invest_size
                )

    def close_all_positions(self, current_prices: Dict[str, float], get_slippage_ratio_fn: Callable[[str], float]) -> int:
        total_closed = 0
        for universe in self.universes.values():
            total_closed += universe.close_all_positions(current_prices, get_slippage_ratio_fn)
        return total_closed

    def get_leaderboard(self, current_prices: Optional[Dict[str, float]] = None) -> List[Dict[str, Any]]:
        """
        Формирует сравнительную таблицу лидеров (Leaderboard) по всем запущенным вселенным.
        """
        leaderboard = []
        current_prices = current_prices or {}

        for uid, univ in self.universes.items():
            an_data = univ.analytics._read_data() if hasattr(univ.analytics, "_read_data") else {}
            if an_data:
                AnalyticsMathEngine.calculate(an_data)

            realized_pnl = float(an_data.get("realized_pnl_usdt", an_data.get("net_profit_usdt", 0.0)))
            total_trades = an_data.get("total_trades", 0)
            winrate = an_data.get("winrate_pct", 0.0)
            max_dd = an_data.get("max_drawdown_usdt", 0.0)
            recovery_factor = an_data.get("recovery_factor", 0.0)

            # Подсчет активных позиций и нереализованного PnL
            active_count = 0
            unrealized_pnl = 0.0
            for sym, sides in univ.state.positions.items():
                for side, pos in sides.items():
                    if pos.is_active and pos.open_price > 0:
                        active_count += 1
                        cur_p = current_prices.get(sym, pos.open_price)
                        if side == "LONG":
                            ratio = (cur_p - pos.open_price) / pos.open_price
                        else:
                            ratio = (pos.open_price - cur_p) / pos.open_price
                        unrealized_pnl += ratio * pos.size

            live_net_profit = realized_pnl + unrealized_pnl
            leaderboard.append({
                "uid": uid,
                "name": univ.name,
                "description": univ.description,
                "net_profit": live_net_profit,
                "realized_pnl": realized_pnl,
                "total_trades": total_trades,
                "winrate": winrate,
                "max_dd": max_dd,
                "recovery_factor": recovery_factor,
                "active_count": active_count,
                "unrealized_pnl": unrealized_pnl
            })

        # Сортировка по чистому профиту (Net Profit)
        leaderboard.sort(key=lambda x: x["net_profit"], reverse=True)
        return leaderboard
