# ============================================================
# FILE: models.py
# ROLE: FSM Models and Dataclasses for Bot State
# ============================================================

from dataclasses import dataclass

@dataclass
class PositionState:
    symbol: str
    side: str  # "LONG" or "SHORT"
    
    open_price: float = 0.0
    size: float = 0.0
    open_time: int = 0
    is_active: bool = False
    
    def reset(self):
        """Сброс до дефолта: обнуление всех метрик и флагов."""
        self.open_price = 0.0
        self.size = 0.0
        self.open_time = 0
        self.is_active = False

    def set_active(self, price: float, size: float, open_time: int):
        self.open_price = price
        self.size = size
        self.open_time = open_time
        self.is_active = True
