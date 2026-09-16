# ============================================================
# FILE: API/base_cex.py
# ROLE: Base classes for CEX adapters
# ============================================================
from abc import ABC, abstractmethod
from typing import Dict, Set, Optional, TypedDict
from curl_cffi.requests import AsyncSession

class TickerData(TypedDict):
    price: float
    volume: float
    timestamp: float

class BaseCEXAdapter(ABC):
    @abstractmethod
    async def get_all_prices(self, session: AsyncSession) -> Dict[str, float]:
        """
        Fetch all prices in a single request.
        Returns a dictionary mapping symbol to price.
        """
        pass

    @abstractmethod
    async def ping(self, session: AsyncSession) -> bool:
        """
        Check connection to the exchange.
        """
        pass
