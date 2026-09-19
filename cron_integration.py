# ============================================================
# FILE: cron_integration.py
# ROLE: Integrates configurations and runtime grid state from cron3Papper
# ============================================================
import os
import json
import time
from typing import Dict, Any, List, Optional
from c_log import log
from consts import cfg
from CORE.rules import BaseRule


class CronIntegration:
    """
    Интеграционный слой для взаимодействия с внешним сеточным ботом cron3Papper.
    Считывает символы торговли и текущий статус заполнения сеток (Grid Inventory Stress).
    """

    _cache: Dict[str, Any] = {}
    _cache_ttl_sec: float = 1.0

    @classmethod
    def clear_cache(cls):
        """Очищает кэш состояния сеток."""
        cls._cache.clear()

    @staticmethod
    def get_symbols() -> List[str]:
        """Возвращает список торгуемых символов из конфигурации cron3Papper."""
        try:
            data_sources = cfg.get("data_sources", {})
            hardcoded_symbols = data_sources.get("hardcoded_symbols", [])
            if hardcoded_symbols and isinstance(hardcoded_symbols, list) and len(hardcoded_symbols) > 0:
                return hardcoded_symbols

            symbols_path = data_sources.get("symbols_path")
            if not symbols_path or not os.path.exists(symbols_path):
                return []

            with open(symbols_path, "r", encoding="utf-8") as f:
                app_json = json.load(f)
            syms = app_json.get("symbols", [])
            log(f"[CronIntegration] Загружено {len(syms)} символов из {symbols_path}", level="INFO")
            return syms
        except Exception as e:
            log(f"[CronIntegration] Error reading symbols: {e}", level="ERROR", throttle_sec=60)
            return []

    @classmethod
    def _find_runtime_file(cls, symbol: str) -> Optional[str]:
        """
        Ищет файл состояния валютной пары в целевом runtime_path.
        Резервный путь к тестовым фикстурам используется только если runtime_path не существует.
        """
        data_sources = cfg.get("data_sources", {})
        candidate_dirs = []

        runtime_path = data_sources.get("runtime_path")
        if runtime_path and os.path.exists(runtime_path):
            candidate_dirs.append(runtime_path)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            fixtures_path = os.path.join(base_dir, "tests", "fixtures", "sample_runtime", "runtime")
            if os.path.exists(fixtures_path):
                candidate_dirs.append(fixtures_path)

        sym_lower = symbol.lower()
        sym_upper = symbol.upper()

        for c_dir in candidate_dirs:
            for fname in (f"{sym_lower}.json", f"{sym_upper}.json", f"{symbol}.json"):
                fpath = os.path.join(c_dir, fname)
                if os.path.exists(fpath):
                    return fpath
        return None

    @classmethod
    def get_symbol_state(cls, symbol: str) -> Dict[str, Any]:
        """
        Считывает базовый статус инвентаря для расчета размера ордера.
        Возвращает размер позиции в USD для LONG и SHORT.
        При hardcoded_size = null размер рассчитывается динамически от набранной сетки:
        хэдж-позиция берет 50% объема застрявшей сетки противоположной стороны.
        """
        result = {
            "LONG": {"invest_size": 50.0, "volume": 0.0, "enabled": False},
            "SHORT": {"invest_size": 50.0, "volume": 0.0, "enabled": False}
        }
        try:
            data_sources = cfg.get("data_sources", {})
            hardcoded_size = data_sources.get("hardcoded_size")
            if hardcoded_size is not None and float(hardcoded_size) > 0:
                size_val = float(hardcoded_size)
                result["LONG"] = {"invest_size": size_val, "volume": 0.0, "enabled": True}
                result["SHORT"] = {"invest_size": size_val, "volume": 0.0, "enabled": True}
                return result

            inactive_mode = str(data_sources.get("inactive_grid_mode", "TAKE_LEVEL_0")).strip().upper()
            is_skip_mode = inactive_mode in ("SKIP", "SKIP_SIGNAL", "SKIP_IF_INACTIVE") or data_sources.get("skip_if_grid_inactive") is True

            file_path = cls._find_runtime_file(symbol)
            if not file_path:
                return result

            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            sides_info = {}
            for s in ("LONG", "SHORT"):
                s_data = data.get(s, {})
                enabled = s_data.get("enable", False)
                base_inv = float(s_data.get("invest_size", 0.0))
                grid = s_data.get("grid", {})
                active_vol_pct = sum(v.get("volume", 0.0) for v in grid.values() if v.get("is_active", False))
                has_active = any(v.get("is_active", False) for v in grid.values())
                level_0_pct = float(grid.get("0", {}).get("volume", 12.96))
                accum_usd = (active_vol_pct / 100.0) * base_inv if active_vol_pct > 0 else 0.0
                base_order_usd = (level_0_pct / 100.0) * base_inv if (base_inv > 0 and level_0_pct > 0) else 50.0
                sides_info[s] = {
                    "enabled": enabled,
                    "base_inv": base_inv,
                    "accum_usd": accum_usd,
                    "base_order_usd": base_order_usd,
                    "has_active": has_active,
                    "grid": grid
                }

            default_hedge_ratio = data_sources.get("default_hedge_ratio", 0.5)
            for side in ("LONG", "SHORT"):
                s_info = sides_info.get(side, {})
                opp_info = sides_info.get("SHORT" if side == "LONG" else "LONG", {})
                result[side]["enabled"] = s_info.get("enabled", False)
                result[side]["raw_grid"] = s_info.get("grid", {})
                result[side]["has_active"] = s_info.get("has_active", False)
                result[side]["base_order_usd"] = s_info.get("base_order_usd", 50.0)
                result[side]["accum_usd"] = s_info.get("accum_usd", 0.0)

                # Хэджирование: если на противоположной стороне набран объем, хэдж берет долю от hedge_ratio
                if opp_info.get("accum_usd", 0.0) > 0:
                    opp_grid = opp_info.get("grid", {})
                    opp_levels = [int(k) for k, v in opp_grid.items() if v.get("is_active", False)]
                    opp_max_lvl = max(opp_levels) if opp_levels else -1
                    opp_count = len(opp_levels)
                    ratio = cls.resolve_hedge_ratio(default_hedge_ratio, max_level=opp_max_lvl, active_count=opp_count)
                    calc_size = opp_info["accum_usd"] * ratio
                elif s_info.get("has_active", False) and s_info.get("accum_usd", 0.0) > 0:
                    calc_size = s_info["accum_usd"]
                else:
                    # На нужной стороне не активирован ни один уровень сетки
                    if is_skip_mode:
                        calc_size = 0.0
                    else:
                        calc_size = s_info.get("base_order_usd", 50.0)

                result[side]["invest_size"] = round(calc_size, 2)
        except Exception as e:
            log(f"[CronIntegration] Error reading state for {symbol}: {e}", level="ERROR", throttle_sec=60)
        return result

    @classmethod
    def resolve_hedge_ratio(cls, hedge_cfg: Any, max_level: int = -1, active_count: int = 0) -> float:
        """
        Вычисляет динамический коэффициент хеджирования:
        - Если hedge_cfg - float/int, возвращает его (обратная совместимость).
        - Если hedge_cfg - dict (карта зависимостей по уровням/количеству сеток):
          0-1: 1.0 (100% объема)
          2-3: 0.75 (75% объема)
          4+: 0.5 (50% объема)
        """
        if isinstance(hedge_cfg, (int, float)):
            return float(hedge_cfg)
        if isinstance(hedge_cfg, dict):
            if max_level >= 0:
                if str(max_level) in hedge_cfg:
                    return float(hedge_cfg[str(max_level)])
                if max_level in hedge_cfg:
                    return float(hedge_cfg[max_level])
                if max_level == 0 and "1" in hedge_cfg:
                    return float(hedge_cfg["1"])
            if active_count > 0:
                if str(active_count) in hedge_cfg:
                    return float(hedge_cfg[str(active_count)])
                if active_count in hedge_cfg:
                    return float(hedge_cfg[active_count])
            if "default" in hedge_cfg:
                return float(hedge_cfg["default"])
            return 0.5
        return 0.5

    @classmethod
    def get_grid_stress(cls, symbol: str, current_price: float = 0.0) -> Dict[str, Any]:
        """
        Анализирует уровень стресса сетки cron3Papper (Inventory-Stress Momentum Overlay).
        Рассчитывает долю набранного объема (volume_ratio), максимальный активный уровень
        усреднения (0..5) и просадку от средней цены входа.
        """
        now = time.time()
        cached = cls._cache.get(symbol)
        if cached and (now - cached["ts"] < cls._cache_ttl_sec):
            data = dict(cached["data"])
            if current_price > 0:
                cls._enrich_drawdown(data, current_price)
            return data

        empty_side = {
            "in_position": False,
            "volume_ratio": 0.0,
            "accumulated_volume": 0.0,
            "max_level": -1,
            "drawdown_pct": 0.0,
            "stressed": False,
            "extreme": False,
            "avg_entry_price": 0.0
        }
        res = {
            "status": "NEUTRAL",
            "stressed_side": None,
            "opposite_side": None,
            "volume_ratio": 0.0,
            "max_level": -1,
            "drawdown_pct": 0.0,
            "extreme": False,
            "LONG": dict(empty_side),
            "SHORT": dict(empty_side)
        }

        file_path = cls._find_runtime_file(symbol)
        if not file_path:
            cls._cache[symbol] = {"ts": now, "data": res}
            return res

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)

            for side in ("LONG", "SHORT"):
                if side not in raw_data or not isinstance(raw_data[side], dict):
                    continue
                s_data = raw_data[side]
                grid = s_data.get("grid", {})
                active_levels = [int(k) for k, v in grid.items() if v.get("is_active", False)]
                accum_vol = sum(v.get("volume", 0.0) for k, v in grid.items() if v.get("is_active", False))
                vol_ratio = round(accum_vol / 100.0, 4)
                max_lvl = max(active_levels) if active_levels else -1
                in_pos = bool(s_data.get("in_position", False) or len(active_levels) > 0)
                avg_price = float(s_data.get("avg_entry_price", 0.0))

                dd_pct = 0.0
                if current_price > 0 and avg_price > 0:
                    if side == "LONG":
                        dd_pct = max(0.0, (avg_price - current_price) / avg_price * 100.0)
                    else:
                        dd_pct = max(0.0, (current_price - avg_price) / avg_price * 100.0)

                price_stressed = True
                if avg_price > 0 and current_price > 0:
                    price_stressed = (current_price <= avg_price) if side == "LONG" else (current_price >= avg_price)

                stressed = in_pos and price_stressed and (vol_ratio >= 0.45 or max_lvl >= 2)
                extreme = in_pos and price_stressed and (vol_ratio >= 0.70 or max_lvl >= 4)

                res[side] = {
                    "in_position": in_pos,
                    "volume_ratio": vol_ratio,
                    "accumulated_volume": round(accum_vol, 2),
                    "max_level": max_lvl,
                    "drawdown_pct": round(dd_pct, 2),
                    "stressed": stressed,
                    "extreme": extreme,
                    "avg_entry_price": avg_price,
                    "price_stressed": price_stressed
                }

            long_st = res["LONG"]["stressed"]
            short_st = res["SHORT"]["stressed"]
            long_ext = res["LONG"]["extreme"]
            short_ext = res["SHORT"]["extreme"]

            if long_ext and not short_ext:
                res["status"] = "LONG_GRID_EXTREME"
                res["stressed_side"] = "LONG"
                res["opposite_side"] = "SHORT"
                res["volume_ratio"] = res["LONG"]["volume_ratio"]
                res["max_level"] = res["LONG"]["max_level"]
                res["extreme"] = True
            elif short_ext and not long_ext:
                res["status"] = "SHORT_GRID_EXTREME"
                res["stressed_side"] = "SHORT"
                res["opposite_side"] = "LONG"
                res["volume_ratio"] = res["SHORT"]["volume_ratio"]
                res["max_level"] = res["SHORT"]["max_level"]
                res["extreme"] = True
            elif long_st and not short_st:
                res["status"] = "LONG_GRID_STRESSED"
                res["stressed_side"] = "LONG"
                res["opposite_side"] = "SHORT"
                res["volume_ratio"] = res["LONG"]["volume_ratio"]
                res["max_level"] = res["LONG"]["max_level"]
            elif short_st and not long_st:
                res["status"] = "SHORT_GRID_STRESSED"
                res["stressed_side"] = "SHORT"
                res["opposite_side"] = "LONG"
                res["volume_ratio"] = res["SHORT"]["volume_ratio"]
                res["max_level"] = res["SHORT"]["max_level"]
            elif long_st and short_st:
                if res["LONG"]["volume_ratio"] >= res["SHORT"]["volume_ratio"]:
                    res["status"] = "LONG_GRID_STRESSED"
                    res["stressed_side"] = "LONG"
                    res["opposite_side"] = "SHORT"
                    res["volume_ratio"] = res["LONG"]["volume_ratio"]
                    res["max_level"] = res["LONG"]["max_level"]
                else:
                    res["status"] = "SHORT_GRID_STRESSED"
                    res["stressed_side"] = "SHORT"
                    res["opposite_side"] = "LONG"
                    res["volume_ratio"] = res["SHORT"]["volume_ratio"]
                    res["max_level"] = res["SHORT"]["max_level"]

            cls._cache[symbol] = {"ts": now, "data": dict(res)}
            log(
                f"[CRON3 RUNTIME PARSED] [{symbol}] LONG: in_pos={res['LONG']['in_position']}, "
                f"vol={res['LONG']['volume_ratio']:.1%}, lvl={res['LONG']['max_level']}/5, "
                f"avg={res['LONG']['avg_entry_price']:.4f} | SHORT: in_pos={res['SHORT']['in_position']}, "
                f"vol={res['SHORT']['volume_ratio']:.1%}, lvl={res['SHORT']['max_level']}/5, "
                f"avg={res['SHORT']['avg_entry_price']:.4f} | Status: {res['status']}",
                level="DEBUG",
                throttle_sec=30,
                throttle_key=f"cron_parse_{symbol}"
            )
        except Exception as e:
            log(f"[CronIntegration] Error calculating grid stress for {symbol}: {e}", level="ERROR", throttle_sec=60)
            cls._cache[symbol] = {"ts": now, "data": res}
        return res

    @staticmethod
    def _enrich_drawdown(data: Dict[str, Any], current_price: float):
        """Пересчитывает просадку на основе свежей цены тика."""
        for side in ("LONG", "SHORT"):
            s_info = data.get(side, {})
            avg_p = s_info.get("avg_entry_price", 0.0)
            if avg_p > 0:
                if side == "LONG":
                    s_info["drawdown_pct"] = round(max(0.0, (avg_p - current_price) / avg_p * 100.0), 2)
                else:
                    s_info["drawdown_pct"] = round(max(0.0, (current_price - avg_p) / avg_p * 100.0), 2)


# ==========================================
# RULES FOR GRID STRESS INTEGRATION
# ==========================================
class EntryGridStressRule(BaseRule):
    """
    Правило входа по стрессу инвентаря сетки (Inventory-Stress Momentum Overlay).
    Если застряла LONG-сетка -> TrendH открывает SHORT.
    Если застряла SHORT-сетка -> TrendH открывает LONG.
    """

    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.is_active: bool = bool(cfg.get("is_active", False))
        self.long_cond: str = str(cfg.get("long_cond", "SHORT_GRID_STRESSED"))
        self.short_cond: str = str(cfg.get("short_cond", "LONG_GRID_STRESSED"))
        self.min_volume_ratio: float = float(cfg.get("min_volume_ratio", 0.5))
        self.min_filled_level: int = int(cfg.get("min_filled_level", 3))
        self.extreme_only: bool = bool(cfg.get("extreme_only", False))

    def check(self, side: str, indicators: Optional[Dict[str, Any]] = None, **kwargs) -> bool:
        if not self.is_active:
            return True
        indicators = indicators or kwargs.get("indicators", {})
        stress = indicators.get("grid_stress", kwargs.get("grid_stress"))
        if not stress or not isinstance(stress, dict):
            return False

        status = stress.get("status", "NEUTRAL")
        target_side = "SHORT" if side == "LONG" else "LONG"
        side_info = stress.get(target_side, {})

        if not side_info.get("in_position", False):
            return False

        passed = False
        if self.extreme_only:
            extreme_cond = "SHORT_GRID_EXTREME" if side == "LONG" else "LONG_GRID_EXTREME"
            passed = (status == extreme_cond or side_info.get("extreme", False))
        else:
            vol_ok = side_info.get("volume_ratio", 0.0) >= self.min_volume_ratio
            lvl_ok = side_info.get("max_level", -1) >= self.min_filled_level
            if vol_ok and lvl_ok:
                expected_cond = self.long_cond if side == "LONG" else self.short_cond
                passed = status in (expected_cond, f"{target_side}_GRID_EXTREME") or side_info.get("stressed", False) or side_info.get("price_stressed", True)

        if passed:
            symbol = kwargs.get("symbol", indicators.get("symbol", "N/A"))
            cur_p = kwargs.get("current_price", indicators.get("current_price", 0.0))
            vol_r = side_info.get("volume_ratio", 0.0)
            accum_v = side_info.get("accumulated_volume", vol_r * 100.0)
            avg_p = side_info.get("avg_entry_price", 0.0)
            dd_p = side_info.get("drawdown_pct", 0.0)
            log(
                f"[GRID STRESS MATCH] [{symbol}][{side}] cron3_stuck={target_side} | "
                f"vol_ratio={vol_r:.1%} ({accum_v:.1f}%), max_lvl={side_info.get('max_level', -1)}/5, "
                f"avg_price={avg_p:.4f}, cur_price={cur_p:.4f}, dd={dd_p:+.2f}%, status={status}",
                level="INFO",
                throttle_sec=5,
                throttle_key=f"gsm_{symbol}_{side}"
            )
        return passed


class ExitGridReliefRule(BaseRule):
    """
    Правило выхода при закрытии или разгрузке позиции сетки сеточником (Grid Relief).
    Если застрявшая сторона закрыла позицию по TP или сбросила объемы, хэдж закрывается.
    """

    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.is_active: bool = bool(cfg.get("is_active", False))
        self.exit_on_position_close: bool = bool(cfg.get("exit_on_position_close", True))
        self.max_volume_ratio: float = float(cfg.get("max_volume_ratio", 0.2))

    def check(self, side: str, indicators: Optional[Dict[str, Any]] = None, **kwargs) -> bool:
        if not self.is_active:
            return False
        indicators = indicators or kwargs.get("indicators", {})
        stress = indicators.get("grid_stress", kwargs.get("grid_stress"))
        if not stress or not isinstance(stress, dict):
            return False

        hedged_grid_side = "LONG" if side == "SHORT" else "SHORT"
        grid_data = stress.get(hedged_grid_side, {})
        if not grid_data:
            return False

        if self.exit_on_position_close and not grid_data.get("in_position", False):
            return True
        if grid_data.get("volume_ratio", 0.0) <= self.max_volume_ratio:
            return True
        return False
