# ============================================================
# FILE: rules_engine.py
# ROLE: Strategy Pattern Rules Engine for Entry and Exit Signals
# ============================================================
from abc import ABC, abstractmethod
from typing import Dict, Any, Callable, Optional
from c_log import log
from utils import eval_condition

class BaseRule(ABC):
    @abstractmethod
    def check(self, side: str, **kwargs) -> bool:
        pass


# ==========================================
# ENTRY RULES (All must pass for signal)
# ==========================================
class EntryTrendRule(BaseRule):
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.is_active = cfg.get("is_active", False)

    def check(self, side: str, trend: str, **kwargs) -> bool:
        if not self.is_active:
            return True
        if side == "LONG":
            return trend == self.cfg.get("long_cond", "UP")
        elif side == "SHORT":
            return trend == self.cfg.get("short_cond", "DOWN")
        return False

class EntryRSIRule(BaseRule):
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.is_active = cfg.get("is_active", False)
        
    def check(self, side: str, rsi: str = "NEUTRAL", **kwargs) -> bool:
        if not self.is_active:
            return True
        if rsi == "UNSTABLE":
            return False
            
        if side == "LONG":
            return rsi == "LONG"
        elif side == "SHORT":
            return rsi == "SHORT"
            
        return False

class EntrySignalEngine:
    def __init__(self, enter_rules_cfg: Dict[str, Any]):
        self.rules = []
        if "trend" in enter_rules_cfg:
            self.rules.append(EntryTrendRule(enter_rules_cfg["trend"]))
        if "rsi" in enter_rules_cfg:
            self.rules.append(EntryRSIRule(enter_rules_cfg["rsi"]))
            
    def check_signal(self, side: str, trend: str, rsi: str) -> bool:
        """Returns True only if ALL active entry rules pass."""
        for rule in self.rules:
            if not rule.check(side, trend=trend, rsi=rsi):
                return False
        return True


# ==========================================
# EXIT RULES (Any one passing triggers exit)
# ==========================================
class ExitTrendReversalRule(BaseRule):
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.is_active = cfg.get("is_active", False)
        
    def check(self, side: str, trend: str, **kwargs) -> bool:
        if not self.is_active:
            return False
        if side == "LONG" and trend in self.cfg.get("long_exit_trends", []):
            return True
        if side == "SHORT" and trend in self.cfg.get("short_exit_trends", []):
            return True
        return False

class ExitTakeProfitRule(BaseRule):
    def __init__(self, cfg: Dict[str, Any], analytics_cfg: Dict[str, Any], get_slippage_ratio_fn: Callable[[str], float]):
        self.cfg = cfg
        self.analytics_cfg = analytics_cfg
        self.value = cfg.get("value")
        self.get_slippage_ratio_fn = get_slippage_ratio_fn
        
    def check(self, side: str, symbol: str, open_price: float, current_price: float, **kwargs) -> bool:
        if self.value is None:
            return False
            
        fee_ratio = self.analytics_cfg.get("taker_fee_ratio", 0.0) * 2
        slippage_ratio = self.get_slippage_ratio_fn(symbol) * 2
        fee_slip_ratio = fee_ratio + slippage_ratio
        
        if side == "LONG":
            pnl_ratio = (current_price - open_price) / open_price - fee_slip_ratio
        else:
            pnl_ratio = (open_price - current_price) / open_price - fee_slip_ratio
            
        if pnl_ratio >= self.value:
            log(f"[{symbol}][TAKE PROFIT] PnL {pnl_ratio*100:.2f}% >= {self.value*100:.2f}%", level="DEBUG")
            return True
            
        return False

class ExitSignalEngine:
    def __init__(self, exit_rules_cfg: Dict[str, Any], analytics_cfg: Dict[str, Any], get_slippage_ratio_fn: Callable[[str], float]):
        self.rules = []
        if "trend_reversal" in exit_rules_cfg:
            self.rules.append(ExitTrendReversalRule(exit_rules_cfg["trend_reversal"]))
        if "take_profit_ratio" in exit_rules_cfg:
            self.rules.append(ExitTakeProfitRule(exit_rules_cfg["take_profit_ratio"], analytics_cfg, get_slippage_ratio_fn))
            
    def check_signal(self, side: str, symbol: str, trend: str, open_price: float, current_price: float) -> bool:
        """Returns True if ANY active exit rule passes."""
        for rule in self.rules:
            if rule.check(side, symbol=symbol, trend=trend, open_price=open_price, current_price=current_price):
                return True
        return False
