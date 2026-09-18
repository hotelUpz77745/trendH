# ============================================================
# FILE: CORE/indicators/__init__.py
# ROLE: Indicators subdomain facade, engine & public API exports
# ============================================================

from typing import Dict, List, Set, Any, Optional

from CORE.indicators.trend_osc import (
    IndicatorsMath,
    TrendCalculator,
    RSICalculator,
    RSIWaterlineCalculator,
    EMACrossCalculator,
    VolumeFilterCalculator,
)
from CORE.indicators.hvh import HVHCalculator, EntryHVHRule
from CORE.indicators.sr_levels import SRLevelsCalculator
from CORE.indicators.squeeze_flow import (
    RealtimeFlowTracker,
    TakerFlowCalculator,
    VolatilitySqueezeCalculator,
    RelativeStrengthCalculator,
    ChandelierTrailingCalculator,
    EntryTakerFlowRule,
    EntryVolatilitySqueezeRule,
    EntryRelativeStrengthRule,
    ExitChandelierRule,
)


class IndicatorsEngine:
    """
    Фасадный интерфейс индикаторного блока системы.
    Координирует работу всех индикаторов и правил субдомена indicators/.
    """

    def __init__(self, enter_rules: Dict[str, Any]):
        self.trend_calcs: Dict[str, TrendCalculator] = {}
        for key in ["trend", "trend_htf"]:
            if key in enter_rules:
                self.trend_calcs[key] = TrendCalculator(enter_rules[key])

        # Поддержка дополнительных ключей тренда при их наличии
        for key, val in enter_rules.items():
            if key.startswith("trend") and key not in self.trend_calcs and isinstance(val, dict):
                self.trend_calcs[key] = TrendCalculator(val)

        rsi_cfg = enter_rules.get("rsi")
        self.rsi_calc = RSICalculator(rsi_cfg) if rsi_cfg else None

        waterline_cfg = enter_rules.get("rsi_waterline50")
        self.rsi_waterline_calc = RSIWaterlineCalculator(waterline_cfg) if waterline_cfg else None

        sr_cfg = enter_rules.get("sr_levels")
        self.sr_calc = SRLevelsCalculator(sr_cfg) if sr_cfg else None

        ema_cross_cfg = enter_rules.get("ema_cross")
        self.ema_cross_calc = EMACrossCalculator(ema_cross_cfg) if ema_cross_cfg else None

        vol_cfg = enter_rules.get("vol_filter")
        self.vol_filter_calc = VolumeFilterCalculator(vol_cfg) if vol_cfg else None

        tf_cfg = enter_rules.get("taker_flow")
        self.taker_flow_calc = TakerFlowCalculator(tf_cfg) if tf_cfg and tf_cfg.get("is_active") else None

        sq_cfg = enter_rules.get("volatility_squeeze")
        self.squeeze_calc = VolatilitySqueezeCalculator(sq_cfg) if sq_cfg and sq_cfg.get("is_active") else None

        rs_cfg = enter_rules.get("relative_strength")
        self.relative_strength_calc = RelativeStrengthCalculator(rs_cfg) if rs_cfg and rs_cfg.get("is_active") else None

        self.hvh_calcs: Dict[str, HVHCalculator] = {}
        for key, val in enter_rules.items():
            if (key == "hvh" or key.startswith("hvh_")) and isinstance(val, dict) and val.get("is_active"):
                tf = str(val.get("timeframe", "5m"))
                self.hvh_calcs[tf] = HVHCalculator(val)

        hvh_cfg = enter_rules.get("hvh")
        self.hvh_calc = self.hvh_calcs.get(str(hvh_cfg.get("timeframe", "5m"))) if hvh_cfg and hvh_cfg.get("is_active") else (list(self.hvh_calcs.values())[0] if self.hvh_calcs else None)

    def get_required_timeframes(self) -> Set[str]:
        """Возвращает набор таймфреймов, данные по которым требуются для расчетов."""
        tfs = set()
        for calc in self.trend_calcs.values():
            if calc.is_active:
                tfs.add(calc.timeframe)
        if self.rsi_calc and self.rsi_calc.is_active:
            tfs.add(self.rsi_calc.timeframe)
        if self.rsi_waterline_calc and self.rsi_waterline_calc.is_active:
            tfs.add(self.rsi_waterline_calc.timeframe)
        if self.sr_calc and self.sr_calc.is_active:
            tfs.add(self.sr_calc.timeframe)
        if self.ema_cross_calc and self.ema_cross_calc.is_active:
            tfs.add(self.ema_cross_calc.timeframe)
        if self.vol_filter_calc and self.vol_filter_calc.is_active:
            tfs.add(self.vol_filter_calc.timeframe)
        if self.taker_flow_calc and self.taker_flow_calc.is_active:
            tfs.add(self.taker_flow_calc.timeframe)
        if self.squeeze_calc and self.squeeze_calc.is_active:
            tfs.add(self.squeeze_calc.timeframe)
        if self.relative_strength_calc and self.relative_strength_calc.is_active:
            tfs.add("5m")
        for tf, calc in self.hvh_calcs.items():
            if calc.is_active:
                tfs.add(tf)
        if self.hvh_calc and self.hvh_calc.is_active:
            tfs.add(self.hvh_calc.timeframe)
        return tfs if tfs else {"5m"}

    def calculate(
        self,
        klines_by_tf: Dict[str, Any],
        current_price: Optional[float] = None,
        btc_closes: Optional[List[float]] = None,
        realtime_flow: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Вычисляет показатели индикаторов по переданному словарю {таймфрейм: свечи/closes}.
        """
        closes_by_tf: Dict[str, List[float]] = {}
        for tf, raw in klines_by_tf.items():
            if isinstance(raw, list):
                if raw and isinstance(raw[0], dict):
                    closes_by_tf[tf] = [float(c.get("close", 0.0)) for c in raw]
                else:
                    closes_by_tf[tf] = [float(c) for c in raw]
            elif isinstance(raw, dict) and "close" in raw:
                closes_by_tf[tf] = [float(x) for x in raw["close"]]
            else:
                closes_by_tf[tf] = []

        result: Dict[str, Any] = {}
        for key, calc in self.trend_calcs.items():
            if calc.is_active:
                closes = closes_by_tf.get(calc.timeframe, [])
                result[key] = calc.calculate(closes)
            else:
                result[key] = "UNSTABLE"

        if "trend" not in result:
            result["trend"] = "UNSTABLE"

        rsi_states = ["UNSTABLE"]
        rsi_val = None
        if self.rsi_calc and self.rsi_calc.is_active:
            closes_rsi = closes_by_tf.get(self.rsi_calc.timeframe, [])
            rsi_states = self.rsi_calc.calculate(closes_rsi)
            rsi_val = self.rsi_calc.get_raw_value(closes_rsi)

        result["rsi"] = rsi_states
        result["rsi_value"] = rsi_val

        if self.rsi_waterline_calc and self.rsi_waterline_calc.is_active:
            closes_wl = closes_by_tf.get(self.rsi_waterline_calc.timeframe, [])
            result["rsi_waterline50"] = self.rsi_waterline_calc.calculate(closes_wl)
        else:
            result["rsi_waterline50"] = []

        if self.sr_calc and self.sr_calc.is_active:
            candles_sr = klines_by_tf.get(self.sr_calc.timeframe, [])
            sr_res = self.sr_calc.calculate(candles_sr, current_price=current_price)
            result["sr_levels"] = sr_res["signals"]
            result["sr_levels_data"] = sr_res
        else:
            result["sr_levels"] = []
            result["sr_levels_data"] = {"signals": [], "support": [], "resistance": []}

        if self.ema_cross_calc and self.ema_cross_calc.is_active:
            closes_ec = closes_by_tf.get(self.ema_cross_calc.timeframe, [])
            result["ema_cross"] = self.ema_cross_calc.calculate(closes_ec)
        else:
            result["ema_cross"] = []

        if self.vol_filter_calc and self.vol_filter_calc.is_active:
            candles_vol = klines_by_tf.get(self.vol_filter_calc.timeframe, [])
            result["vol_filter"] = self.vol_filter_calc.calculate(candles_vol)
        else:
            result["vol_filter"] = []

        if self.taker_flow_calc and self.taker_flow_calc.is_active:
            candles_tf = klines_by_tf.get(self.taker_flow_calc.timeframe, [])
            result["taker_flow"] = self.taker_flow_calc.calculate(candles_tf, realtime_flow=realtime_flow)
        else:
            result["taker_flow"] = []

        if self.squeeze_calc and self.squeeze_calc.is_active:
            candles_sq = klines_by_tf.get(self.squeeze_calc.timeframe, [])
            result["volatility_squeeze"] = self.squeeze_calc.calculate(candles_sq)
        else:
            result["volatility_squeeze"] = []

        if self.relative_strength_calc and self.relative_strength_calc.is_active:
            coin_closes = closes_by_tf.get("5m", [])
            result["relative_strength"] = self.relative_strength_calc.calculate(coin_closes, btc_closes or [])
        else:
            result["relative_strength"] = []

        all_hvh_sigs: List[str] = []
        for tf, calc in self.hvh_calcs.items():
            if calc.is_active:
                c_hvh = klines_by_tf.get(tf, [])
                s_hvh = calc.calculate(c_hvh)
                result[f"hvh_{tf}"] = s_hvh
                all_hvh_sigs.extend(s_hvh)
        if self.hvh_calc and self.hvh_calc.is_active and not all_hvh_sigs:
            candles_hvh = klines_by_tf.get(self.hvh_calc.timeframe, [])
            all_hvh_sigs = self.hvh_calc.calculate(candles_hvh)
        result["hvh"] = list(dict.fromkeys(all_hvh_sigs)) if all_hvh_sigs else []

        result["candles_5m"] = klines_by_tf.get("5m", [])
        return result


__all__ = [
    "IndicatorsEngine",
    "IndicatorsMath",
    "TrendCalculator",
    "RSICalculator",
    "RSIWaterlineCalculator",
    "EMACrossCalculator",
    "VolumeFilterCalculator",
    "HVHCalculator",
    "EntryHVHRule",
    "SRLevelsCalculator",
    "RealtimeFlowTracker",
    "TakerFlowCalculator",
    "VolatilitySqueezeCalculator",
    "RelativeStrengthCalculator",
    "ChandelierTrailingCalculator",
    "EntryTakerFlowRule",
    "EntryVolatilitySqueezeRule",
    "EntryRelativeStrengthRule",
    "ExitChandelierRule",
]
