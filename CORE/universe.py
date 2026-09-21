# ============================================================
# FILE: universe.py
# ROLE: Multi-Strategy Parallel Universe Engine & State Isolation
# ============================================================

import json
import time
from typing import Dict, Any, Optional, List, Callable, Union
from pathlib import Path

from c_log import log
from CORE.models import PositionState
from CORE.rules import EntrySignalEngine, ExitSignalEngine
from ANALYTICS.analytics import AnalyticsManager
from consts import DATA_DIR, ANALYTICS_DIR, ANALYTICS_CFG, cfg


class UniverseState:
    """Изолированное состояние позиций для конкретной торговой вселенной."""

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
                    self.positions[sym] = {"LONG": PositionState(symbol=sym, side="LONG"), "SHORT": PositionState(symbol=sym, side="SHORT")}
                for side, pos_dict in sides.items():
                    if pos_dict.get("is_active"):
                        pos = self.positions[sym][side]
                        pos.is_active, pos.open_price, pos.size = True, float(pos_dict.get("open_price", 0.0)), float(pos_dict.get("size", 0.0))
            active_cnt = sum(1 for sym, s in self.positions.items() for side, pos in s.items() if pos.is_active)
            log(f"[{self.universe_id}] Загружен стейт из {path.name} ({active_cnt} активных)", level="INFO" if active_cnt > 0 else "DEBUG")
        except Exception as e:
            log(f"[{self.universe_id}] Ошибка загрузки стейта: {e}", level="ERROR")

    def save_state(self):
        try:
            data = {sym: {"LONG": s["LONG"].__dict__, "SHORT": s["SHORT"].__dict__} for sym, s in self.positions.items()}
            with open(self.get_state_path(), "w", encoding="utf-8") as f:
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
            self.positions[symbol] = {"LONG": PositionState(symbol=symbol, side="LONG"), "SHORT": PositionState(symbol=symbol, side="SHORT")}
        self.positions[symbol][side].set_active(price, size, int(time.time() * 1000))
        self.save_state()

    def close_position(self, symbol: str, side: str):
        if symbol in self.positions and side in self.positions[symbol]:
            self.positions[symbol][side].reset()
            self.save_state()


class StrategyUniverse:
    """Автономная торговая вселенная (стратегия) с изолированным стейтом и аналитикой."""

    def __init__(
        self, universe_id: str, name: str, description: str, enter_rules: Dict[str, Any], exit_rules: Dict[str, Any],
        get_slippage_ratio_fn: Callable[[str], float], is_active: bool = True, backup_manager=None,
        inactive_grid_mode: Optional[str] = None, hedge_ratio: Optional[float] = None
    ):
        self.universe_id, self.name, self.description, self.is_active = universe_id, name, description, is_active
        self.enter_rules, self.exit_rules = enter_rules, exit_rules
        default_grid_mode = cfg.get("data_sources", {}).get("inactive_grid_mode", "TAKE_LEVEL_0")
        self.inactive_grid_mode = str(inactive_grid_mode or default_grid_mode).strip().upper()
        self.hedge_ratio = hedge_ratio if hedge_ratio is not None else cfg.get("data_sources", {}).get("default_hedge_ratio", 0.5)
        self.entry_engine, self.exit_engine = EntrySignalEngine(enter_rules), ExitSignalEngine(exit_rules, ANALYTICS_CFG, get_slippage_ratio_fn)
        self.state, self.analytics = UniverseState(universe_id=universe_id, backup_manager=backup_manager), AnalyticsManager(universe_id=universe_id)
        self.state.load_state()
        self.reentry_cooldown_sec: float = float(cfg.get("reentry_cooldown_sec", 60.0))
        self.last_exit_time, self.position_ext_data = {}, {}

    def get_dynamic_hedge_ratio(self, max_level: int = -1, active_count: int = 0) -> float:
        """
        Вычисляет динамический коэффициент хеджирования:
        - Если hedge_ratio число (float/int), возвращает его (обратная совместимость).
        - Если hedge_ratio словарь (карта зависимостей по уровням/количеству сеток):
          0-1: 1.0 (100% объема)
          2-3: 0.75 (75% объема)
          4+: 0.5 (50% объема)
        """
        if isinstance(self.hedge_ratio, (int, float)):
            return float(self.hedge_ratio)
        if isinstance(self.hedge_ratio, dict):
            if max_level >= 0:
                if str(max_level) in self.hedge_ratio:
                    return float(self.hedge_ratio[str(max_level)])
                if max_level in self.hedge_ratio:
                    return float(self.hedge_ratio[max_level])
                if max_level == 0 and "1" in self.hedge_ratio:
                    return float(self.hedge_ratio["1"])
            if active_count > 0:
                if str(active_count) in self.hedge_ratio:
                    return float(self.hedge_ratio[str(active_count)])
                if active_count in self.hedge_ratio:
                    return float(self.hedge_ratio[active_count])
            return float(self.hedge_ratio.get("default", 0.5))
        return 0.5

    def check_entry(self, side: str, indicators: Dict[str, Any], symbol: str = "") -> bool:
        return self.entry_engine.check_signal(side, indicators, symbol=symbol)

    def check_exit(self, side: str, symbol: str, open_price: float, current_price: float, indicators: Dict[str, Any], open_time_ms: Optional[int] = None, highest_price: Optional[float] = None, lowest_price: Optional[float] = None) -> bool:
        return self.exit_engine.check_signal(
            side, symbol, indicators.get("trend", "UNSTABLE"), open_price, current_price,
            indicators, open_time_ms, highest_price=highest_price, lowest_price=lowest_price
        )

    def process_tick(
        self, symbol: str, side: str, current_price: float, indicators: Dict[str, Any],
        get_slippage_ratio_fn: Callable[[str], float], is_paused: bool, invest_size: float,
        cron_state: Optional[Dict[str, Any]] = None
    ):
        """Обрабатывает тик цены для конкретной валютной пары и стороны."""
        pos = self.state.get_position(symbol, side)
        if pos:
            ext = self.position_ext_data.setdefault(symbol, {}).setdefault(side, {"highest": current_price, "lowest": current_price})
            ext["highest"] = max(ext["highest"], current_price)
            ext["lowest"] = min(ext["lowest"], current_price)

            should_exit = self.check_exit(
                side, symbol, pos.open_price, current_price, indicators,
                open_time_ms=pos.open_time, highest_price=ext["highest"], lowest_price=ext["lowest"]
            )
            if should_exit:
                fee_slip = (ANALYTICS_CFG.get("taker_fee_ratio", 0) + get_slippage_ratio_fn(symbol)) * 2
                pnl_ratio = (current_price - pos.open_price) / pos.open_price if side == "LONG" else (pos.open_price - current_price) / pos.open_price
                pnl_usd, comm_usd = pnl_ratio * pos.size, -(fee_slip * pos.size)
                reason = getattr(self.exit_engine, "last_exit_reason", "") or "EXIT"
                log(f"[SIGNAL EXIT] [{self.universe_id}][{symbol}][{side}] Выход [{reason}]! Вход: {pos.open_price:.4f} -> {current_price:.4f} | PnL: {pnl_ratio * 100:+.2f}% ({pnl_usd:+.2f}$)", level="INFO")
                self.analytics.record_virtual_trade(symbol, side, pnl_usd, comm_usd, open_time_ms=pos.open_time)
                self.state.close_position(symbol, side)
                self.last_exit_time.setdefault(symbol, {})[side] = time.time()
                self.position_ext_data.get(symbol, {}).pop(side, None)
        else:
            # Защита от моментального перезахода (re-entry cooldown)
            last_exit = self.last_exit_time.get(symbol, {}).get(side, 0.0)
            if (time.time() - last_exit) < self.reentry_cooldown_sec:
                return

            # Проверка условий входа
            if not is_paused and self.check_entry(side, indicators, symbol=symbol):
                eff_invest_size, eff_ratio, opp_accum = invest_size, 1.0, 0.0
                if cron_state and side in cron_state:
                    s_info = cron_state[side]
                    has_active = s_info.get("has_active", False)
                    opp_side = "SHORT" if side == "LONG" else "LONG"
                    opp_data = cron_state.get(opp_side, {})
                    opp_accum = opp_data.get("accum_usd", 0.0)
                    if opp_accum > 0:
                        opp_grid = opp_data.get("raw_grid", {})
                        opp_levels = [int(k) for k, v in opp_grid.items() if v.get("is_active", False)]
                        opp_max_lvl = max(opp_levels) if opp_levels else -1
                        eff_ratio = self.get_dynamic_hedge_ratio(max_level=opp_max_lvl, active_count=len(opp_levels))
                        eff_invest_size = round(opp_accum * eff_ratio, 2)
                    elif not has_active and opp_accum == 0.0:
                        eff_invest_size = 0.0 if self.inactive_grid_mode in ("SKIP", "SKIP_SIGNAL", "SKIP_IF_INACTIVE") else s_info.get("base_order_usd", invest_size)

                rsi_val = indicators.get("rsi_value")
                rsi_str = f"{rsi_val:.1f}" if rsi_val is not None else "N/A"
                htf_str = f", HTF: {indicators.get('trend_htf')}" if "trend_htf" in indicators else ""
                grid_str = ""
                stress_info = indicators.get("grid_stress")
                if stress_info and isinstance(stress_info, dict):
                    st_side = "SHORT" if side == "LONG" else "LONG"
                    s_data = stress_info.get(st_side, {})
                    if s_data.get("in_position"):
                        grid_str = f", Cron3[{st_side}]: vol={s_data.get('volume_ratio', 0.0):.1%}, dd={s_data.get('drawdown_pct', 0.0):+.2f}%"

                log(f"[SIGNAL ENTRY] [{self.universe_id}][{symbol}][{side}] Trend: {indicators.get('trend')}{htf_str}, RSI: {rsi_str}{grid_str}", level="INFO")
                if eff_invest_size > 0:
                    hedge_info_str = f" (hedge={eff_ratio:.0%})" if opp_accum > 0 else ""
                    log(f"[POSITION OPEN] [{self.universe_id}][{symbol}][{side}] Цена: {current_price}, Размер: {eff_invest_size}${hedge_info_str}{grid_str}", level="INFO")
                    self.state.open_position(symbol, side, current_price, eff_invest_size)
                    self.position_ext_data.setdefault(symbol, {})[side] = {"highest": current_price, "lowest": current_price}
                else:
                    log(f"[SIGNAL SKIPPED] [{self.universe_id}][{symbol}][{side}] Пропуск входа: размер 0", level="INFO", throttle_sec=30)

    def update_live_metrics(self, current_prices: Dict[str, float]) -> Dict[str, Any]:
        """В моменте рассчитывает нереализованный PnL, живое эквити и аккумулирует просадку."""
        an_data = self.analytics._read_data()
        start_bal = float(cfg.get("universes", {}).get(self.universe_id, {}).get("start_balance", an_data.get("start_balance_usdt", ANALYTICS_CFG.get("default_start_balance", 200.0))))
        realized_gross = float(an_data.get("realized_pnl_usdt", 0.0))
        realized_net = float(an_data.get("net_profit_usdt", realized_gross))
        commission_paid = abs(realized_gross - realized_net)
        realized_pnl = realized_net

        active_count = 0
        unrealized_pnl = 0.0
        for sym, sides in self.state.positions.items():
            for side, pos in sides.items():
                if pos.is_active and pos.open_price > 0:
                    active_count += 1
                    cur_p = current_prices.get(sym) or pos.open_price
                    ratio = (cur_p - pos.open_price if side == "LONG" else pos.open_price - cur_p) / pos.open_price
                    unrealized_pnl += ratio * pos.size

        live_net_profit = realized_pnl + unrealized_pnl
        live_equity = start_bal + live_net_profit

        prev_peak = float(an_data.get("peak_balance_usdt", start_bal))
        stored_start = float(an_data.get("start_balance_usdt", start_bal))
        prev_max_dd = float(an_data.get("max_drawdown_usdt", 0.0))

        # Защита от миграции стартового баланса (например, с 1000$ на 200$)
        if stored_start > 0 and abs(stored_start - start_bal) > 0.01:
            delta = start_bal - stored_start
            prev_peak = max(start_bal, prev_peak + delta)
            if prev_max_dd > prev_peak:
                prev_max_dd = max(0.0, prev_max_dd + delta)
            an_data["start_balance_usdt"] = start_bal
        elif prev_peak >= 800.0 and start_bal <= 300.0:
            prev_peak = start_bal + max(0.0, prev_peak - 1000.0)
            prev_max_dd = min(prev_max_dd, prev_peak - float(an_data.get("min_balance_usdt", start_bal)))

        peak_equity = max(prev_peak, start_bal, live_equity)
        current_dd = max(0.0, peak_equity - live_equity)
        max_dd = max(prev_max_dd, current_dd)

        prev_u = float(an_data.get("unrealized_pnl_usdt", 0.0))
        prev_cdd = float(an_data.get("current_drawdown_usdt", 0.0))
        if max_dd > prev_max_dd or peak_equity > prev_peak or abs(unrealized_pnl - prev_u) > 0.01 or abs(current_dd - prev_cdd) > 0.01:
            an_data.update({
                "universe_id": self.universe_id, "unrealized_pnl_usdt": round(unrealized_pnl, 4),
                "peak_balance_usdt": round(peak_equity, 4), "max_drawdown_usdt": round(max_dd, 4),
                "current_drawdown_usdt": round(current_dd, 4), "start_balance_usdt": round(start_bal, 2)
            })
            self.analytics._write_data(an_data)

        return {
            "realized_pnl": realized_pnl, "realized_gross": realized_gross, "commission_paid": commission_paid,
            "unrealized_pnl": unrealized_pnl, "live_net_profit": live_net_profit, "live_equity": live_equity,
            "peak_equity": peak_equity, "current_dd": current_dd, "max_dd": max_dd,
            "active_count": active_count, "start_balance": start_bal
        }

    def close_all_positions(self, current_prices: Dict[str, float], get_slippage_ratio_fn: Callable[[str], float]) -> int:
        """Экстренное закрытие всех позиций вселенной."""
        closed_count = 0
        fee_ratio = ANALYTICS_CFG.get("taker_fee_ratio", 0) * 2
        for symbol, sides in list(self.state.positions.items()):
            for side, pos in list(sides.items()):
                cur_p = current_prices.get(symbol)
                if not pos.is_active or not cur_p:
                    continue
                slip = fee_ratio + get_slippage_ratio_fn(symbol) * 2
                ratio = (cur_p - pos.open_price if side == "LONG" else pos.open_price - cur_p) / pos.open_price
                self.analytics.record_virtual_trade(symbol, side, ratio * pos.size, -(slip * pos.size), open_time_ms=pos.open_time)
                self.state.close_position(symbol, side)
                closed_count += 1
        return closed_count


class UniverseManager:
    """Менеджер параллельных вселенных (стратегий)."""

    def __init__(
        self, universes_cfg: Dict[str, Any], default_enter_rules: Dict[str, Any], default_exit_rules: Dict[str, Any],
        get_slippage_ratio_fn: Callable[[str], float], backup_manager=None
    ):
        self.universes: Dict[str, StrategyUniverse] = {}
        self.backup_manager = backup_manager
        if universes_cfg:
            for uid, udata in universes_cfg.items():
                if udata.get("is_active", True):
                    self.universes[uid] = StrategyUniverse(
                        universe_id=uid, name=udata.get("name", uid), description=udata.get("description", ""),
                        enter_rules=udata.get("enter_rules", default_enter_rules), exit_rules=udata.get("exit_rules", default_exit_rules),
                        get_slippage_ratio_fn=get_slippage_ratio_fn, is_active=True, backup_manager=backup_manager,
                        inactive_grid_mode=udata.get("inactive_grid_mode"), hedge_ratio=udata.get("hedge_ratio")
                    )
        else:
            self.universes["default"] = StrategyUniverse(
                universe_id="default", name="Default Strategy", description="Единая стратегия по умолчанию",
                enter_rules=default_enter_rules, exit_rules=default_exit_rules,
                get_slippage_ratio_fn=get_slippage_ratio_fn, is_active=True, backup_manager=backup_manager
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
                    if key == "hvh":
                        tf = val.get("timeframe", "5m")
                        combined[f"hvh_{tf}"] = dict(val)
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
                    combined["rsi"] = {"is_active": True, "timeframe": val.get("timeframe", "5m"), "window": val.get("window", 14), "conditions": {}}
        return combined

    def get_universe(self, uid: str) -> Optional[StrategyUniverse]:
        return self.universes.get(uid)

    def get_all_universes(self) -> List[StrategyUniverse]:
        return list(self.universes.values())

    def process_tick(
        self, symbol: str, side: str, current_price: float, indicators: Dict[str, Any],
        get_slippage_ratio_fn: Callable[[str], float], is_paused: bool, invest_size: float,
        cron_state: Optional[Dict[str, Any]] = None
    ):
        """Раздает тик во все активные вселенные параллельно."""
        for universe in self.universes.values():
            if universe.is_active:
                universe.process_tick(
                    symbol=symbol, side=side, current_price=current_price, indicators=indicators,
                    get_slippage_ratio_fn=get_slippage_ratio_fn, is_paused=is_paused,
                    invest_size=invest_size, cron_state=cron_state
                )

    def close_all_positions(self, current_prices: Dict[str, float], get_slippage_ratio_fn: Callable[[str], float]) -> int:
        return sum(u.close_all_positions(current_prices, get_slippage_ratio_fn) for u in self.universes.values())

    def update_all_live_metrics(self, current_prices: Dict[str, float]) -> None:
        """Обновляет живые метрики и аккумулирует просадку для всех активных вселенных и портфеля."""
        for univ in self.universes.values():
            if univ.is_active:
                univ.update_live_metrics(current_prices)
        self.get_portfolio_metrics(current_prices)

    def get_portfolio_metrics(self, current_prices: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """Рассчитывает суммарные (портфельные) метрики по всем активным вселенным."""
        current_prices = current_prices or {}
        tot_start, tot_realized, tot_unrealized = 0.0, 0.0, 0.0
        tot_active, tot_trades, tot_wins = 0, 0, 0
        merged_coins: Dict[str, Any] = {}
        for univ in self.universes.values():
            if not univ.is_active:
                continue
            m = univ.update_live_metrics(current_prices)
            an = univ.analytics._read_data() if hasattr(univ.analytics, "_read_data") else {}
            tot_start += m.get("start_balance", 200.0)
            tot_realized += m["realized_pnl"]
            tot_unrealized += m["unrealized_pnl"]
            tot_active += m["active_count"]
            tot_trades += int(an.get("total_trades", 0))
            tot_wins += int(an.get("winning_trades", 0))
            for coin, cdata in an.get("per_coin", {}).items():
                mc = merged_coins.setdefault(coin, {"realized_pnl_usdt": 0.0, "trades": 0, "win_count": 0, "loss_count": 0})
                mc["realized_pnl_usdt"] = round(mc["realized_pnl_usdt"] + float(cdata.get("realized_pnl_usdt", 0.0)), 4)
                mc["trades"] += int(cdata.get("trades", 0))
                mc["win_count"] += int(cdata.get("win_count", 0))
                mc["loss_count"] += int(cdata.get("loss_count", 0))

        tot_net = tot_realized + tot_unrealized
        tot_equity = tot_start + tot_net
        winrate = round((tot_wins / tot_trades) * 100.0, 2) if tot_trades > 0 else 0.0

        all_file = ANALYTICS_DIR / "analytics_all.json"
        port_data = {}
        if all_file.exists():
            try:
                port_data = json.loads(all_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        prev_peak = float(port_data.get("peak_balance_usdt", tot_start))
        peak_equity = max(prev_peak, tot_start, tot_equity)
        current_dd = max(0.0, peak_equity - tot_equity)
        max_dd = max(float(port_data.get("max_drawdown_usdt", 0.0)), current_dd)

        port_data.update({
            "universe_id": "all", "start_balance_usdt": round(tot_start, 2), "cur_balance_usdt": round(tot_start + tot_realized, 4),
            "realized_pnl_usdt": round(tot_realized, 4), "unrealized_pnl_usdt": round(tot_unrealized, 4), "net_profit_usdt": round(tot_net, 4),
            "peak_balance_usdt": round(peak_equity, 4), "current_drawdown_usdt": round(current_dd, 4), "max_drawdown_usdt": round(max_dd, 4),
            "total_trades": tot_trades, "winning_trades": tot_wins, "winrate_pct": winrate, "per_coin": merged_coins
        })
        try:
            all_file.write_text(json.dumps(port_data, indent=4), encoding="utf-8")
            (ANALYTICS_DIR / "analytics.json").write_text(json.dumps(port_data, indent=4), encoding="utf-8")
        except Exception:
            pass

        return {
            "start_balance": tot_start, "realized_pnl": tot_realized, "unrealized_pnl": tot_unrealized,
            "live_net_profit": tot_net, "live_equity": tot_equity, "peak_equity": peak_equity,
            "current_dd": current_dd, "max_dd": max_dd, "active_count": tot_active,
            "total_trades": tot_trades, "winning_trades": tot_wins, "winrate_pct": winrate,
            "active_universes": len([u for u in self.universes.values() if u.is_active])
        }

    def get_leaderboard(self, current_prices: Optional[Dict[str, float]] = None) -> List[Dict[str, Any]]:
        """Формирует сравнительную таблицу лидеров (Leaderboard) по всем запущенным вселенным."""
        leaderboard = []
        current_prices = current_prices or {}
        for uid, univ in self.universes.items():
            m = univ.update_live_metrics(current_prices)
            an_data = univ.analytics._read_data() if hasattr(univ.analytics, "_read_data") else {}
            tot_tr = an_data.get("total_trades", 0)
            wr = an_data.get("winrate_pct", 0.0)
            rec = round(m["live_net_profit"] / m["max_dd"], 2) if m["max_dd"] > 0 else 0.0
            leaderboard.append({
                "uid": uid, "name": univ.name, "description": univ.description,
                "net_profit": m["live_net_profit"], "realized_pnl": m["realized_pnl"],
                "commission_paid": m.get("commission_paid", 0.0), "unrealized_pnl": m["unrealized_pnl"],
                "total_trades": tot_tr, "winrate": wr, "max_dd": m["max_dd"],
                "current_dd": m["current_dd"], "recovery_factor": rec, "active_count": m["active_count"],
            })
        leaderboard.sort(key=lambda x: x["net_profit"], reverse=True)
        return leaderboard
