# ============================================================
# FILE: API/binance.py
# ROLE: Binance REST API adapter (klines and 24h volumes)
# ============================================================
import aiohttp
from typing import Dict, List, Optional
from curl_cffi.requests import AsyncSession
from .base_cex import BaseCEXAdapter, TickerData
from c_log import UnifiedLogger
import asyncio
import time

logger = UnifiedLogger("BINANCE")

class BinanceAdapter(BaseCEXAdapter):
    async def get_all_prices(self, session: AsyncSession) -> Dict[str, float]:
        url = "https://fapi.binance.com/fapi/v1/ticker/price"
        try:
            response = await session.get(url, timeout=10.0)
            if response.status_code != 200:
                logger.error(f"HTTP Error fetching all prices: {response.status_code}")
                return {}
            
            data = response.json()
            prices = {}
            for item in data:
                symbol = item.get("symbol", "")
                price = float(item.get("price", 0))
                if price > 0:
                    prices[symbol] = price
            return prices
        except Exception as e:
            logger.error(f"Exception fetching all prices: {e}")
            return {}

    async def ping(self, session: AsyncSession) -> bool:
        url = "https://fapi.binance.com/fapi/v1/ping"
        try:
            response = await session.get(url, timeout=10.0)
            return response.status_code == 200
        except Exception:
            return False

    async def get_klines(self, session: AsyncSession, symbol: str, interval: str = "5m", limit: int = 200) -> Optional[list]:
        full_symbol = f"{symbol}USDT" if not symbol.endswith("USDT") else symbol
        url = f"https://fapi.binance.com/fapi/v1/klines?symbol={full_symbol}&interval={interval}&limit={limit}"
        try:
            response = await session.get(url, timeout=10.0)
            if response.status_code != 200:
                logger.error(f"HTTP Error fetching klines for {full_symbol}: {response.status_code}")
                return None
            return response.json()
        except Exception as e:
            logger.error(f"Exception fetching klines for {full_symbol}: {e}")
            return None

    async def get_24h_volume(self, session: AsyncSession, symbol: str) -> float:
        """Fetch 24hr quote volume in USDT for slippage mapping."""
        url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
        params = {"symbol": symbol}
        for attempt in range(3):
            try:
                resp = await session.get(url, params=params, timeout=5.0)
                if resp.status_code == 200:
                    data = resp.json()
                    # Return quote volume
                    return float(data.get("quoteVolume", 0.0))
                elif resp.status_code == 429:
                    from c_log import log
                    log(f"[BinanceAdapter] Rate limit exceeded on ticker, backoff.", level="WARNING")
                    import asyncio
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                else:
                    from c_log import log
                    log(f"[BinanceAdapter] Error {resp.status_code} on ticker: {resp.text}", level="ERROR")
                    return 0.0
            except Exception as e:
                from c_log import log
                log(f"[BinanceAdapter] Exception on ticker attempt {attempt+1}: {e}", level="WARNING")
                if attempt < 2:
                    import asyncio
                    await asyncio.sleep(1)
                else:
                    return 0.0
        return 0.0
