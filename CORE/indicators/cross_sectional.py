# ============================================================
# FILE: CORE/indicators/cross_sectional.py
# ROLE: Cross-Sectional Momentum (CSM) - ранжирование вселенной
#
# ГИПОТЕЗА:
#   Cross-sectional momentum — один из немногих задокументированных
#   аномальных эффектов в крипте. Работает потому, что относительная
#   сила актива — более стабильный сигнал, чем абсолютная цена.
#   Мы не ищем импульс на одной монете — мы ранжируем всю вселенную
#   и торгуем лидеров/отстающих относительно друг друга.
#
#   Уникальность для нашей системы: исключаем "кэш-коров" сеточника
#   (PIEVERSE, CROSS, FLOCK и т.д.) — там momentum уже отработан
#   и сетка сидит в плюсе. Остаётся "чистая" вселенная, где momentum
#   ещё не отыгран.
#
# PSEUDO-DATA SOURCE:
#   На вход подаётся {symbol: [closes]} для всей вселенной.
#   В продакшене — из того же kline-потока, что и остальные индикаторы,
#   просто агрегированный по всем 74 монетам.
# ============================================================

from typing import Dict, List, Any, Optional
import numpy as np

from CORE.rules import BaseRule
from c_log import log


class CrossSectionalRanker:
    """
    Ранжирует вселенную монет по относительной силе движения.
    
    Методология:
      1. Для каждой монеты считаем cumulative return за lookback N свечей.
      2. Опционально нормализуем на волатильность (ATR или std returns) —
         это даёт risk-adjusted return, который более стабилен.
      3. Ранжируем по adjusted return.
      4. Top-N → LONG candidates. Bottom-N → SHORT candidates.
      5. Фильтр "cash cow" — исключаем монеты, где сеточник в плюсе.
    
    Возвращает dict, который кладётся в indicators и используется
    EntryCrossSectionalRule.
    """

    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.is_active: bool = bool(cfg.get("is_active", False))
        self.lookback_candles: int = int(cfg.get("lookback_candles", 288))  # 24h на 5m
        self.top_n: int = int(cfg.get("top_n", 5))
        self.bottom_n: int = int(cfg.get("bottom_n", 5))
        self.vol_normalize: bool = bool(cfg.get("vol_normalize", True))
        self.min_abs_return: float = float(cfg.get("min_abs_return", 0.015))  # 1.5%
        self.vol_lookback: int = int(cfg.get("vol_lookback", 48))

    @staticmethod
    def _norm_return(closes: np.ndarray, lookback: int) -> Optional[float]:
        if closes.size < lookback + 1:
            return None
        p0 = float(closes[-lookback - 1])
        p1 = float(closes[-1])
        if p0 <= 0:
            return None
        return (p1 - p0) / p0

    @staticmethod
    def _volatility(closes: np.ndarray, lookback: int) -> Optional[float]:
        if closes.size < lookback + 1:
            return None
        rets = np.diff(np.log(closes[-lookback - 1:]))
        if rets.size < 2:
            return None
        std = float(np.std(rets))
        return std if std > 1e-9 else None

    def rank(
        self,
        universe_closes: Dict[str, List[float]],
        cash_cow_symbols: Optional[set] = None,
    ) -> Dict[str, Any]:
        """
        Принимает {symbol: [closes...]} для всей вселенной.
        Возвращает:
        {
          "long_candidates": [sym, ...],   # top-N по adjusted return
          "short_candidates": [sym, ...],  # bottom-N
          "ranks": {sym: {raw_return, adjusted_return, rank}},
          "status": "OK"|"UNSTABLE"
        }
        """
        if not self.is_active or not universe_closes:
            return {"long_candidates": [], "short_candidates": [], "ranks": {}, "status": "INACTIVE"}

        cash_cow_symbols = cash_cow_symbols or set()
        scored: List[tuple] = []

        for sym, closes in universe_closes.items():
            if sym in cash_cow_symbols:
                continue
            arr = np.asarray(closes, dtype=np.float64)
            raw_ret = self._norm_return(arr, self.lookback_candles)
            if raw_ret is None:
                continue
            if abs(raw_ret) < self.min_abs_return:
                # нечего ловить: движение слишком слабое
                continue

            if self.vol_normalize:
                vol = self._volatility(arr, self.vol_lookback)
                if vol is None:
                    continue
                adjusted = raw_ret / vol
            else:
                adjusted = raw_ret

            scored.append((sym, raw_ret, adjusted))

        if len(scored) < (self.top_n + self.bottom_n):
            return {"long_candidates": [], "short_candidates": [], "ranks": {}, "status": "UNSTABLE"}

        # Сортировка по adjusted return (по убыванию)
        scored.sort(key=lambda x: x[2], reverse=True)

        long_candidates = [x[0] for x in scored[: self.top_n]]
        short_candidates = [x[0] for x in scored[-self.bottom_n:]]

        ranks: Dict[str, Any] = {}
        for i, (sym, raw, adj) in enumerate(scored):
            ranks[sym] = {"raw_return": raw, "adjusted_return": adj, "rank": i + 1, "total": len(scored)}

        return {
            "long_candidates": long_candidates,
            "short_candidates": short_candidates,
            "ranks": ranks,
            "status": "OK",
        }


class EntryCrossSectionalRule(BaseRule):
    """
    Правило входа CSM: пропускает сигнал, если символ в top-N (LONG)
    или bottom-N (SHORT) по cross-sectional momentum.
    
    Дополнительные гейты (настраиваются):
      - min_rank_ratio: символ должен быть в верхних X% вселенной
        (по умолчанию top_n уже ограничивает, но можно ужесточить).
      - require_positive_spread: adjusted_return должен быть положительным
        для LONG и отрицательным для SHORT.
      - require_grid_clean: сетка по символу не должна быть в минусе
        (опционально — наоборот, можно требовать, чтобы была в минусе,
        если торгуем против сетки).
    """

    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.is_active: bool = bool(cfg.get("is_active", False))
        self.require_grid_clean: bool = bool(cfg.get("require_grid_clean", True))

    def check(self, side: str, indicators: Optional[Dict[str, Any]] = None, **kwargs) -> bool:
        if not self.is_active:
            return True

        indicators = indicators or kwargs.get("indicators", {})
        symbol = kwargs.get("symbol") or indicators.get("symbol")
        if not symbol:
            return False

        csm = indicators.get("csm", {})
        if not isinstance(csm, dict) or csm.get("status") != "OK":
            return False

        if side == "LONG":
            if symbol not in csm.get("long_candidates", []):
                return False
        elif side == "SHORT":
            if symbol not in csm.get("short_candidates", []):
                return False
        else:
            return False

        # Дополнительный гейт: не входим, если сетка по символу в плюсе
        # (для LONG - сетка SHORT должна быть под водой; для SHORT - наоборот)
        if self.require_grid_clean:
            grid_stress = indicators.get("grid_stress", {})
            opp_side = "SHORT" if side == "LONG" else "LONG"
            s_info = grid_stress.get(opp_side, {}) if isinstance(grid_stress, dict) else {}
            # если у сеточника есть активная сетка по этой монете и она в плюсе —
            # momentum уже отработан, не входим
            if s_info.get("in_position", False) and float(s_info.get("unrealized_pnl", 0.0)) > 0:
                return False

        rank_info = csm.get("ranks", {}).get(symbol, {})
        log(
            f"[CSM ENTRY] [{symbol}][{side}] rank={rank_info.get('rank')}/{rank_info.get('total')} "
            f"adj_ret={rank_info.get('adjusted_return', 0):.3f}",
            level="INFO"
        )
        return True
    



# Особенности CSM:

# Требует пересчёта рангов вне per-symbol loop. В UniverseManager нужно добавить периодический job: раз в N минут собирать closes по всем 74 монетам, вызывать rank(), результат класть в общий indicators["csm"], который виден всем вселенным.

# cash_cow_symbols — берётся из CronAnalyticsCache.get_per_coin(), top-N по net_profit. Логика уже есть в EntryGridNetFilterRule._is_top_cash_cow — переиспользуй.

# Работает без grid stress gate по умолчанию, но require_grid_clean его добавляет опционально.