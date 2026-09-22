# ============================================================
# FILE: CORE/indicators/cascade_flow.py
# ROLE: Liquidation Cascade Momentum (LCM) - детектор каскадов ликвидаций
#
# ГИПОТЕЗА:
#   Настоящий безоткатный импульс в крипте = каскад принудительных ликвидаций.
#   Цена не "пробивает уровень" — она проваливается сквозь плотность, потому что
#   биржа принудительно закрывает чужие позиции. Это событие имеет сигнатуру,
#   отличную от обычного пробоя:
#     1. OI резко падает (принудительное закрытие), а не растёт (новые позиции)
#     2. Taker flow доминирует в направлении каскада (>= 0.65)
#     3. Volume spike и ATR экспансия удерживаются > 2 баров
#     4. Funding flip или расширение в сторону движения
#     5. Сеточник в deep stress (vol_ratio >= 0.6, filled >= 3, uPnL < 0)
#   Вход: не на пробое, а на первом микро-откате ПОСЛЕ подтверждения каскада.
#
# PSEUDO-DATA SOURCE DOCUMENTATION (прототип):
# ==========================================
#   В продакшене используется Binance Futures WebSocket:
#     - wss://fstream.binance.com/ws/!openInterest@1m
#       формат: {"e":"openInterest","E":1690000000000,"s":"BTCUSDT","o":"123456.789"}
#     - wss://fstream.binance.com/ws/!markPrice@1s
#       формат: {"e":"markPriceUpdate","E":...,"s":"BTCUSDT","p":"27000.0",
#                "r":"0.00010000","T":1690003600000}
#     - REST fallback: GET /fapi/v1/openInterest?symbol=BTCUSDT
#
#   Для прототипа используется in-memory deque с API, полностью совместимым
#   с реальным потоком. Достаточно заменить add_oi()/add_funding() на вызовы
#   из WS-хендлера — остальная логика не меняется.
# ============================================================

from typing import Dict, List, Any, Optional
from collections import deque
import time
import numpy as np

from CORE.rules import BaseRule
from c_log import log


# ============================================================
# 1. Трекеры потока данных (OI + Funding)
# ============================================================

class OpenInterestTracker:
    """
    Трекер открытого интереса по каждому символу.
    
    Псевдо-источник: в прототипе add_oi() вызывается либо вручную,
    либо из WS-хендлера Binance !openInterest@1m.
    Retention: 30 мин по умолчанию (достаточно для окон 1-15 мин).
    """

    def __init__(self, max_retention_sec: float = 1800.0):
        self.max_retention_sec = float(max_retention_sec)
        # symbol -> deque[(ts_ms, oi)]
        self.data: Dict[str, deque] = {}

    def add_oi(self, symbol: str, oi: float, event_time_ms: int = 0) -> None:
        now_ms = int(event_time_ms) if event_time_ms > 0 else int(time.time() * 1000)
        if symbol not in self.data:
            self.data[symbol] = deque()
        self.data[symbol].append((now_ms, float(oi)))
        cutoff = now_ms - int(self.max_retention_sec * 1000)
        q = self.data[symbol]
        while q and q[0][0] < cutoff:
            q.popleft()

    def get_change_pct(self, symbol: str, window_sec: float) -> Optional[float]:
        """Изменение OI в % за окно window_sec. None если данных мало."""
        q = self.data.get(symbol)
        if not q or len(q) < 2:
            return None
        now_ms = int(time.time() * 1000)
        cutoff = now_ms - int(window_sec * 1000)
        relevant = [x for x in q if x[0] >= cutoff]
        if len(relevant) < 2:
            return None
        oldest, newest = relevant[0][1], relevant[-1][1]
        if oldest <= 0:
            return None
        return (newest - oldest) / oldest

    def get_current(self, symbol: str) -> Optional[float]:
        q = self.data.get(symbol)
        return q[-1][1] if q else None

    def clear(self, symbol: Optional[str] = None) -> None:
        if symbol is None:
            self.data.clear()
        else:
            self.data.pop(symbol, None)


class FundingRateTracker:
    """
    Трекер ставки финансирования (funding rate).
    
    Псевдо-источник: Binance markPrice@1s stream, поле "r".
    Funding обновляется каждые 8 часов, но markPrice stream
    отдаёт текущее значение (предсказанное) каждую секунду.
    """

    def __init__(self, max_retention_sec: float = 28800.0):  # 8h
        self.max_retention_sec = float(max_retention_sec)
        self.data: Dict[str, deque] = {}

    def add_funding(self, symbol: str, funding_rate: float, event_time_ms: int = 0) -> None:
        now_ms = int(event_time_ms) if event_time_ms > 0 else int(time.time() * 1000)
        if symbol not in self.data:
            self.data[symbol] = deque()
        self.data[symbol].append((now_ms, float(funding_rate)))
        cutoff = now_ms - int(self.max_retention_sec * 1000)
        q = self.data[symbol]
        while q and q[0][0] < cutoff:
            q.popleft()

    def get_current(self, symbol: str) -> Optional[float]:
        q = self.data.get(symbol)
        return q[-1][1] if q else None

    def get_flip(self, symbol: str, window_sec: float = 900.0) -> bool:
        """True если знак funding сменился за окно window_sec."""
        q = self.data.get(symbol)
        if not q or len(q) < 2:
            return False
        now_ms = int(time.time() * 1000)
        cutoff = now_ms - int(window_sec * 1000)
        relevant = [x for x in q if x[0] >= cutoff]
        if len(relevant) < 2:
            return False
        oldest = relevant[0][1]
        newest = relevant[-1][1]
        if oldest == 0 or newest == 0:
            return False
        return (oldest > 0) != (newest > 0)

    def clear(self, symbol: Optional[str] = None) -> None:
        if symbol is None:
            self.data.clear()
        else:
            self.data.pop(symbol, None)


# ============================================================
# 2. Калькулятор каскада
# ============================================================

class CascadeCalculator:
    """
    Детектор каскада ликвидаций. Возвращает score 0..100 и сигнал
    (CASCADE_LONG | CASCADE_SHORT | CASCADE_NONE).

    Score-based подход: каждая сигнатура даёт баллы, порог определяет
    силу каскада. Это устойчивее, чем AND-логика: если один из
    сигналов шумит, общий score всё ещё информативен.
    """

    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.is_active: bool = bool(cfg.get("is_active", False))
        self.timeframe: str = str(cfg.get("timeframe", "5m"))

        # Пороги сигнатур
        self.oi_drop_threshold: float = float(cfg.get("oi_drop_threshold", 0.03))     # -3% OI
        self.oi_window_sec: float = float(cfg.get("oi_window_sec", 900.0))            # за 15 мин
        self.taker_min_dominance: float = float(cfg.get("taker_min_dominance", 0.65))
        self.vol_spike_ratio: float = float(cfg.get("vol_spike_ratio", 2.5))
        self.vol_lookback: int = int(cfg.get("vol_lookback", 20))
        self.atr_expansion: float = float(cfg.get("atr_expansion", 1.3))
        self.atr_period: int = int(cfg.get("atr_period", 14))
        self.funding_flip_window: float = float(cfg.get("funding_flip_window", 900.0))

        # Порог срабатывания
        self.score_threshold: int = int(cfg.get("score_threshold", 60))

        # Веса сигнатур (сумма = 100)
        self.w_oi: int = int(cfg.get("w_oi", 30))
        self.w_taker: int = int(cfg.get("w_taker", 25))
        self.w_vol: int = int(cfg.get("w_vol", 15))
        self.w_atr: int = int(cfg.get("w_atr", 15))
        self.w_funding: int = int(cfg.get("w_funding", 15))

        self.long_cond: str = str(cfg.get("long_cond", "CASCADE_LONG"))
        self.short_cond: str = str(cfg.get("short_cond", "CASCADE_SHORT"))

        # Требовать подтверждение микро-отката после каскада
        self.require_pullback: bool = bool(cfg.get("require_pullback", True))

    @staticmethod
    def _calc_atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, length: int) -> float:
        if len(highs) < length + 1:
            return 0.0
        tr1 = highs[1:] - lows[1:]
        tr2 = np.abs(highs[1:] - closes[:-1])
        tr3 = np.abs(lows[1:] - closes[:-1])
        tr = np.maximum(np.maximum(tr1, tr2), tr3)
        return float(np.mean(tr[-length:]))

    def _extract_candles(self, candles: Any) -> Optional[Dict[str, np.ndarray]]:
        if not candles or not isinstance(candles, list):
            return None
        if not isinstance(candles[0], dict):
            return None
        closes = np.array([float(c.get("close", 0.0)) for c in candles], dtype=np.float64)
        highs = np.array([float(c.get("high", 0.0)) for c in candles], dtype=np.float64)
        lows = np.array([float(c.get("low", 0.0)) for c in candles], dtype=np.float64)
        vols = np.array([float(c.get("volume", 0.0)) for c in candles], dtype=np.float64)
        if closes.size < max(self.vol_lookback, self.atr_period) + 2:
            return None
        return {"close": closes, "high": highs, "low": lows, "volume": vols}

    def calculate(
        self,
        symbol: str,
        candles: Any,
        taker_flow: Optional[Dict[str, Any]],
        oi_tracker: OpenInterestTracker,
        funding_tracker: FundingRateTracker,
    ) -> Dict[str, Any]:
        """
        Возвращает:
        {
          "signals": [...],           # список сигналов
          "score": int,               # общий score 0..100
          "direction": "LONG"|"SHORT"|None,
          "components": {...},        # разбивка по сигнатурам
          "status": "OK"|"UNSTABLE"
        }
        """
        if not self.is_active:
            return {"signals": [], "score": 0, "direction": None, "status": "INACTIVE"}

        arr = self._extract_candles(candles)
        if arr is None:
            return {"signals": ["UNSTABLE"], "score": 0, "direction": None, "status": "UNSTABLE"}

        closes, highs, lows, vols = arr["close"], arr["high"], arr["low"], arr["volume"]

        # ---- Направление каскада ----
        # Определяем по последним 2 закрытым свечам
        price_change = (closes[-1] - closes[-3]) / closes[-3] if closes[-3] > 0 else 0.0
        if price_change == 0.0:
            return {"signals": ["UNSTABLE"], "score": 0, "direction": None, "status": "UNSTABLE"}
        direction = "LONG" if price_change > 0 else "SHORT"

        score = 0
        components: Dict[str, Any] = {}

        # ---- 1. OI drop ----
        oi_change = oi_tracker.get_change_pct(symbol, self.oi_window_sec)
        oi_pts = 0
        if oi_change is not None:
            if oi_change <= -self.oi_drop_threshold:
                oi_pts = self.w_oi
            elif oi_change <= -self.oi_drop_threshold * 0.5:
                oi_pts = int(self.w_oi * 0.5)
        components["oi_change"] = oi_change
        components["oi_pts"] = oi_pts
        score += oi_pts

        # ---- 2. Taker flow dominance ----
        taker_pts = 0
        taker_ratio = None
        if taker_flow and isinstance(taker_flow, dict):
            taker_ratio = float(taker_flow.get("taker_buy_ratio", 0.5))
            # для LONG нужен доминирующий buy, для SHORT — sell
            effective = taker_ratio if direction == "LONG" else (1.0 - taker_ratio)
            if effective >= self.taker_min_dominance:
                taker_pts = self.w_taker
            elif effective >= self.taker_min_dominance - 0.05:
                taker_pts = int(self.w_taker * 0.5)
        components["taker_ratio"] = taker_ratio
        components["taker_pts"] = taker_pts
        score += taker_pts

        # ---- 3. Volume spike ----
        vol_pts = 0
        last_vol = float(vols[-1])
        ref_vols = vols[-(self.vol_lookback + 1):-1]
        avg_vol = float(np.mean(ref_vols)) if ref_vols.size > 0 else 0.0
        vol_ratio = (last_vol / avg_vol) if avg_vol > 0 else 0.0
        if vol_ratio >= self.vol_spike_ratio:
            vol_pts = self.w_vol
        elif vol_ratio >= self.vol_spike_ratio * 0.7:
            vol_pts = int(self.w_vol * 0.5)
        components["vol_ratio"] = vol_ratio
        components["vol_pts"] = vol_pts
        score += vol_pts

        # ---- 4. ATR expansion ----
        atr_pts = 0
        atr_now = self._calc_atr(highs[-self.atr_period - 1:], lows[-self.atr_period - 1:], closes[-self.atr_period - 1:], self.atr_period)
        atr_long = self._calc_atr(highs, lows, closes, self.atr_period * 3)
        atr_ratio = (atr_now / atr_long) if atr_long > 0 else 0.0
        if atr_ratio >= self.atr_expansion:
            atr_pts = self.w_atr
        elif atr_ratio >= self.atr_expansion * 0.8:
            atr_pts = int(self.w_atr * 0.5)
        components["atr_ratio"] = atr_ratio
        components["atr_pts"] = atr_pts
        score += atr_pts

        # ---- 5. Funding flip / extreme ----
        funding_pts = 0
        funding_now = funding_tracker.get_current(symbol)
        funding_flip = funding_tracker.get_flip(symbol, self.funding_flip_window)
        if funding_flip:
            funding_pts = self.w_funding
        elif funding_now is not None and abs(funding_now) > 0.0005:  # > 0.05%
            # экстремальный funding, но не flip
            funding_pts = int(self.w_funding * 0.4)
        components["funding"] = funding_now
        components["funding_flip"] = funding_flip
        components["funding_pts"] = funding_pts
        score += funding_pts

        # ---- Микро-откат после каскада ----
        # Если require_pullback: последняя свеча должна быть против движения,
        # но не более чем на X% (иначе это уже разворот, а не откат)
        pullback_ok = True
        if self.require_pullback and len(closes) >= 3:
            last_bar = closes[-1] - closes[-2]
            if direction == "SHORT" and last_bar > 0:
                # откат вверх — ожидаемо
                pullback_ok = abs(last_bar / closes[-2]) < 0.005  # не более 0.5%
            elif direction == "LONG" and last_bar < 0:
                pullback_ok = abs(last_bar / closes[-2]) < 0.005
            else:
                # ещё нет отката — ждём
                pullback_ok = False
        components["pullback_ok"] = pullback_ok

        # ---- Финальный сигнал ----
        signals: List[str] = []
        is_cascade = score >= self.score_threshold and pullback_ok

        if is_cascade:
            if direction == "LONG":
                signals.append(self.long_cond)
            else:
                signals.append(self.short_cond)

        return {
            "signals": signals,
            "score": int(score),
            "direction": direction if is_cascade else None,
            "components": components,
            "status": "OK",
        }


# ============================================================
# 3. Правило входа
# ============================================================

class EntryCascadeMomentumRule(BaseRule):
    """
    Правило входа LCM.
    
    Логика:
    1. CascadeCalculator даёт сигнал CASCADE_LONG / CASCADE_SHORT.
    2. Гейт по grid stress: сеточник должен быть в deep stress
       (vol_ratio >= min_grid_vol_ratio, filled >= min_filled_level, uPnL < 0).
       Это отличает LCM от HVH impulse: мы не торгуем "просто импульс",
       мы торгуем "импульс, который ломает сетку".
    3. Одноразовое срабатывание: после входа cooldown (не переоткрывать
       на каждом тике). Управляется снаружи через reentry_cooldown_sec.
    """

    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.is_active: bool = bool(cfg.get("is_active", False))
        self.long_cond: str = str(cfg.get("long_cond", "CASCADE_LONG"))
        self.short_cond: str = str(cfg.get("short_cond", "CASCADE_SHORT"))

        # Grid stress gate
        self.min_grid_vol_ratio: float = float(cfg.get("min_grid_vol_ratio", 0.6))
        self.min_filled_level: int = int(cfg.get("min_filled_level", 3))
        self.require_grid_underwater: bool = bool(cfg.get("require_grid_underwater", True))

        # OI/Funding trackers инжектируются снаружи (shared singletons)
        self.oi_tracker: Optional[OpenInterestTracker] = None
        self.funding_tracker: Optional[FundingRateTracker] = None
        self.cascade_calc: CascadeCalculator = CascadeCalculator(cfg)

    def attach_trackers(
        self,
        oi_tracker: OpenInterestTracker,
        funding_tracker: FundingRateTracker,
    ) -> None:
        """Инжектирует shared trackers. Вызывается один раз при инициализации вселенной."""
        self.oi_tracker = oi_tracker
        self.funding_tracker = funding_tracker

    def check(self, side: str, indicators: Optional[Dict[str, Any]] = None, **kwargs) -> bool:
        if not self.is_active:
            return True

        if self.oi_tracker is None or self.funding_tracker is None:
            log("[LCM] trackers not attached, skipping", level="WARN", throttle_sec=300)
            return False

        indicators = indicators or kwargs.get("indicators", {})
        symbol = kwargs.get("symbol") or indicators.get("symbol")
        if not symbol:
            return False

        candles = indicators.get("candles", indicators.get("candles_5m", []))
        taker_flow = indicators.get("taker_flow_raw", {})

        # 1. Каскад
        cascade = self.cascade_calc.calculate(
            symbol=symbol,
            candles=candles,
            taker_flow=taker_flow,
            oi_tracker=self.oi_tracker,
            funding_tracker=self.funding_tracker,
        )
        signals = cascade.get("signals", [])
        if not signals or "UNSTABLE" in signals:
            return False

        target_cond = self.long_cond if side == "LONG" else self.short_cond
        if target_cond not in signals:
            return False

        # 2. Grid stress gate — берём данные сеточника из indicators
        grid_stress = indicators.get("grid_stress", {})
        opp_side = "SHORT" if side == "LONG" else "LONG"
        s_info = grid_stress.get(opp_side, {}) if isinstance(grid_stress, dict) else {}

        if not s_info.get("in_position", False):
            return False

        vol_ratio = float(s_info.get("volume_ratio", 0.0))
        filled = int(s_info.get("filled_levels", 0))
        u_pnl = float(s_info.get("unrealized_pnl", 0.0))

        if vol_ratio < self.min_grid_vol_ratio:
            return False
        if filled < self.min_filled_level:
            return False
        if self.require_grid_underwater and u_pnl >= 0:
            return False

        log(
            f"[LCM ENTRY] [{symbol}][{side}] cascade score={cascade['score']} "
            f"grid_vol={vol_ratio:.2f} filled={filled} uPnL={u_pnl:+.2f}",
            level="INFO"
        )
        return True


# Как подключается:

# В indicators должен прокидываться taker_flow_raw (сырой dict из RealtimeFlowTracker.get_flow()), а не taker_flow (список сигналов).

# Trackers создаются один раз в UniverseManager и инжектируются в правило через attach_trackers().

# В indicators["grid_stress"] уже приходит структура из cron analytics — переиспользуем.