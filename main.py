# ============================================================
# FILE: main.py
# ROLE: Main bot loop, signal processing, and virtual execution
# ============================================================
import asyncio
import time
import traceback
from typing import Dict, TYPE_CHECKING
from c_log import log
from API.binance import BinanceAdapter
from utils import Utils, NetworkServices
from cron_integration import CronIntegration
from ANALYTICS.analytics import AnalyticsManager
from CORE.rules import EntrySignalEngine, ExitSignalEngine
from CORE.models import PositionState
import json
from notifier import NotifierManager
from API.price_stream import BinanceHotPriceStream
from TG.tg_receiver import TelegramReceiver
from CORE.indicators import IndicatorsEngine

if TYPE_CHECKING:
    from API.price_stream import HotPriceTick
from consts import (
    cfg,
    MAIN_LOOP_DELAY_SEC,
    INDICATORS_REFRESH_INTERVAL_SEC,
    DIRECTION_MODE,
    ENTER_RULES,
    EXIT_RULES,
    ANALYTICS_CFG,
    PAPER_TRADING_CFG,
    TG_ENABLED,
    TG_TOKEN,
    CFG_PATH
)


class BotState:
    def __init__(self):
        # symbol -> {"LONG": PositionState, "SHORT": PositionState}
        self.positions: Dict[str, Dict[str, PositionState]] = {}

    def get_position(self, symbol: str, side: str):
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

    def close_position(self, symbol: str, side: str):
        if symbol in self.positions and side in self.positions[symbol]:
            self.positions[symbol][side].reset()

class Main:
    def __init__(self):
        self.utils = Utils()
        self.binance_client = BinanceAdapter()
        self.network = NetworkServices()
        self.analytics = AnalyticsManager()
        self.state = BotState()
        self.symbols = []
        self.symbol_indicators = {} # symbol -> {"rsi": float, "trend": str}
        self.symbol_volume_24h = {}
        self.current_prices = {} # symbol -> float
        self.klines_cache = {} # symbol -> tf -> timestamp -> close
        self.api_semaphore = asyncio.Semaphore(10)
        
        self.entry_engine = EntrySignalEngine(ENTER_RULES)
        self.exit_engine = ExitSignalEngine(EXIT_RULES, ANALYTICS_CFG, self.get_slippage_ratio)
        self.indicators_engine = IndicatorsEngine(ENTER_RULES)
        self.notifier = NotifierManager()
        
        self.price_stream = None
        self.stream_task = None
        self.tg_bot = None
        self.tg_task = None
        self.is_paused = not cfg.get("auto_start", True)
        self.direction_mode = DIRECTION_MODE

    def set_paused(self, paused: bool):
        """Переключает флаг паузы и сохраняет состояние auto_start в cfg.json."""
        self.is_paused = paused
        try:
            with open(CFG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["auto_start"] = not paused
            with open(CFG_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            cfg["auto_start"] = not paused
            log(f"[Main] Состояние auto_start сохранено: {not paused}", level="INFO")
        except Exception as e:
            log(f"[Main] Ошибка сохранения auto_start: {e}", level="ERROR")
        
    async def fetch_24h_volume(self, symbol: str):
        vol = await self.binance_client.get_24h_volume(self.network.session, symbol)
        self.symbol_volume_24h[symbol] = vol

    def get_slippage_ratio(self, symbol: str) -> float:
        vol = self.symbol_volume_24h.get(symbol, 0.0)
        base_ratio = PAPER_TRADING_CFG["slippage_base_ratio"]
        tiers = PAPER_TRADING_CFG.get("daily_volume_tiers_usdt", {})
        
        multiplier = 1.0
        # sort tiers
        sorted_tiers = sorted(
            [(float(k) if k != "inf" else float('inf'), v) for k, v in tiers.items()]
        )
        for threshold, mult in sorted_tiers:
            if vol <= threshold:
                multiplier = mult
                break
        
        return base_ratio * multiplier
        
    async def init_klines_cache(self, session):
        log("🚀 Pre-fetching klines history for all symbols...", level="INFO")
        history_size = cfg.get("klines_history_size", 300)
        tfs = self.indicators_engine.get_required_timeframes()
        
        async def _fetch(sym):
            if sym not in self.klines_cache:
                self.klines_cache[sym] = {}
            for tf in tfs:
                async with self.api_semaphore:
                    klines = await self.binance_client.get_klines(session, sym, interval=tf, limit=history_size)
                    if klines:
                        if tf not in self.klines_cache[sym]:
                            self.klines_cache[sym][tf] = {}
                        for k in klines:
                            self.klines_cache[sym][tf][int(k[0])] = float(k[4])
                await asyncio.sleep(0.01)

        tasks = [_fetch(sym) for sym in self.symbols]
        await asyncio.gather(*tasks)
        log(f"✅ Klines history loaded for {len(self.symbols)} symbols.", level="INFO")

    async def update_indicators(self, session, symbol: str):
        try:
            tfs = self.indicators_engine.get_required_timeframes()
            history_size = cfg.get("klines_history_size", 300)
            
            if symbol not in self.klines_cache:
                self.klines_cache[symbol] = {}
                
            klines_data = {}
            for tf in tfs:
                if tf not in self.klines_cache[symbol]:
                    self.klines_cache[symbol][tf] = {}
                    
                async with self.api_semaphore:
                    klines = await self.binance_client.get_klines(session, symbol, interval=tf, limit=5)
                    
                if klines:
                    for k in klines:
                        self.klines_cache[symbol][tf][int(k[0])] = float(k[4])
                        
                sorted_ts = sorted(self.klines_cache[symbol][tf].keys())
                for ts in sorted_ts[:-history_size]:
                    del self.klines_cache[symbol][tf][ts]
                    
                if sorted_ts:
                    klines_data[tf] = [self.klines_cache[symbol][tf][ts] for ts in sorted_ts[-history_size:]]

            if not klines_data:
                return

            self.symbol_indicators[symbol] = self.indicators_engine.calculate(klines_data)
        except Exception as e:
            log(f"[{symbol}] Error updating indicators: {e}", level="ERROR")

    def check_entry(self, symbol: str, side: str) -> bool:
        indicators = self.symbol_indicators.get(symbol)
        if not indicators: return False
        return self.entry_engine.check_signal(side, indicators["trend"], indicators["rsi"])

    def check_exit(self, symbol: str, side: str, open_price: float, current_price: float) -> bool:
        indicators = self.symbol_indicators.get(symbol)
        if not indicators: return False
        return self.exit_engine.check_signal(
            side, 
            symbol=symbol, 
            trend=indicators["trend"], 
            open_price=open_price, 
            current_price=current_price
        )

    async def on_tick(self, tick: 'HotPriceTick'):
        """WebSocket callback triggered instantly on every price change."""
        symbol = tick.symbol
        current_price = tick.price
        self.current_prices[symbol] = current_price
        
        indicators = self.symbol_indicators.get(symbol)
        if not indicators: return
        
        allow_long = self.direction_mode in ("LONG", "HEDGE", "MONO")
        allow_short = self.direction_mode in ("SHORT", "HEDGE", "MONO")
        
        has_long = self.state.get_position(symbol, "LONG") is not None
        has_short = self.state.get_position(symbol, "SHORT") is not None
        
        if self.direction_mode == "MONO":
            if has_long: allow_short = False
            if has_short: allow_long = False
            
        for side in ["LONG", "SHORT"]:
            if side == "LONG" and not allow_long: continue
            if side == "SHORT" and not allow_short: continue
            
            pos = self.state.get_position(symbol, side)
            if pos:
                # Check exit
                if self.check_exit(symbol, side, pos.open_price, current_price):
                    log(f"[{symbol}][{side}] Закрытие виртуальной позиции. Цена: {current_price}", level="INFO")
                    fee_ratio = ANALYTICS_CFG.get("taker_fee_ratio", 0) * 2
                    slippage_ratio = self.get_slippage_ratio(symbol) * 2
                    fee_slip_ratio = fee_ratio + slippage_ratio
                    
                    if side == "LONG":
                        pnl_ratio = (current_price - pos.open_price) / pos.open_price
                    else:
                        pnl_ratio = (pos.open_price - current_price) / pos.open_price
                        
                    pnl_usd = (pnl_ratio * pos.size)
                    comm_usd = -(fee_slip_ratio * pos.size)
                    
                    self.analytics.record_virtual_trade(symbol, side, pnl_usd, comm_usd)
                    self.state.close_position(symbol, side)
            else:
                # Check entry
                if not self.is_paused and self.check_entry(symbol, side):
                    cron_state = CronIntegration.get_symbol_state(symbol)
                    invest_size = cron_state.get(side, {}).get("invest_size", 0.0)
                    if invest_size > 0:
                        log(f"[{symbol}][{side}] Открытие виртуальной позиции. Цена: {current_price}, Размер: {invest_size}$", level="INFO")
                        self.state.open_position(symbol, side, current_price, invest_size)

    async def close_all_positions(self):
        """Экстренное закрытие всех виртуальных позиций по рынку."""
        closed_count = 0
        for symbol, sides in list(self.state.positions.items()):
            for side in list(sides.keys()):
                pos = sides[side]
                if not pos.is_active:
                    continue
                current_price = self.current_prices.get(symbol)
                if not current_price:
                    continue # Не можем закрыть без цены
                    
                fee_ratio = ANALYTICS_CFG.get("taker_fee_ratio", 0) * 2
                slippage_ratio = self.get_slippage_ratio(symbol) * 2
                fee_slip_ratio = fee_ratio + slippage_ratio
                
                if side == "LONG":
                    pnl_ratio = (current_price - pos.open_price) / pos.open_price
                else:
                    pnl_ratio = (pos.open_price - current_price) / pos.open_price
                    
                pnl_usd = (pnl_ratio * pos.size)
                comm_usd = -(fee_slip_ratio * pos.size)
                
                self.analytics.record_virtual_trade(symbol, side, pnl_usd, comm_usd)
                self.state.close_position(symbol, side)
                log(f"[{symbol}][{side}] Экстренное закрытие позиции. Цена: {current_price}, PnL: {pnl_usd:.4f}$", level="INFO")
                closed_count += 1
                
        log(f"✅ Close All: Успешно закрыто {closed_count} виртуальных позиций.", level="INFO")

    async def indicators_daemon(self):
        """Фоновый процесс обновления индикаторов (скачивание свечей)."""
        log("🚀 Запущен indicators_daemon.", level="INFO")
        while True:
            try:
                if self.symbols and not self.is_paused:
                    tasks = [self.update_indicators(self.network.session, sym) for sym in self.symbols]
                    if tasks:
                        await asyncio.gather(*tasks)
            except Exception as ex:
                log(f"Error in indicators_daemon: {ex}", level="ERROR")
                traceback.print_exc()
            await asyncio.sleep(INDICATORS_REFRESH_INTERVAL_SEC)

    async def volumes_daemon(self):
        """Фоновый процесс обновления объемов за 24 часа."""
        log("🚀 Запущен volumes_daemon.", level="INFO")
        while True:
            try:
                if self.symbols:
                    vol_tasks = [self.fetch_24h_volume(sym) for sym in self.symbols]
                    if vol_tasks:
                        await asyncio.gather(*vol_tasks)
            except Exception as ex:
                log(f"Error in volumes_daemon: {ex}", level="ERROR")
                traceback.print_exc()
            await asyncio.sleep(INDICATORS_REFRESH_INTERVAL_SEC)

    async def run(self):
        await self.network.initialize_session()
        if not await self.network.validate_session():
            log("Не удалось установить сессию.", level="ERROR")
            return

        session = self.network.session

        await self.notifier.start()

        # Start TelegramReceiver if enabled and token present
        if TG_ENABLED and TG_TOKEN:
            try:
                self.tg_bot = TelegramReceiver(self)
                self.tg_task = asyncio.create_task(self.tg_bot.start())
                log("🚀 TelegramReceiver успешно запущен параллельно с ядром.", level="INFO")
            except Exception as e:
                log(f"Не удалось инициализировать TelegramReceiver: {e}", level="ERROR")

        log("✅ Бот успешно запущен (Paper Trading mode)", level="INFO")
        try:
            self.symbols = CronIntegration.get_symbols()
            if self.symbols:
                await self.init_klines_cache(session)
                self.price_stream = BinanceHotPriceStream(self.symbols)
                self.stream_task = asyncio.create_task(self.price_stream.run(self.on_tick))
                log(f"🚀 Запущен HotPriceStream для {len(self.symbols)} пар.", level="INFO")
                
            self.indicators_task = asyncio.create_task(self.indicators_daemon())
            self.volumes_task = asyncio.create_task(self.volumes_daemon())
                
            while True:
                await asyncio.sleep(MAIN_LOOP_DELAY_SEC)

        except KeyboardInterrupt:
            log("⛔ Остановка по Ctrl+C", level="INFO")
        except Exception as ex:
            log(f"Сбой выполнения: {ex}", level="ERROR")
            traceback.print_exc()
        finally:
            log("Завершение работы.", level="INFO")
            if self.tg_task:
                self.tg_task.cancel()
            if hasattr(self, 'indicators_task') and self.indicators_task:
                self.indicators_task.cancel()
            if hasattr(self, 'volumes_task') and self.volumes_task:
                self.volumes_task.cancel()
            if self.tg_bot:
                await self.tg_bot.stop()
            if self.price_stream:
                self.price_stream.stop()
            await self.network.shutdown_session()

if __name__ == "__main__":
    try:
        asyncio.run(Main().run())
    except KeyboardInterrupt:
        pass
    except asyncio.exceptions.CancelledError:
        pass


## шпору не трогать!!
# # chmod 600 ssh_key.txt
# # eval "$(ssh-agent -s)" 
# # ssh-add ssh_key.txt
# # git remote set-url origin git@github.com:hotelUpz/uranus_bot.git
# # source .ssh-autostart.sh
# В терминале Git Bash, находясь в папке с проектом:
# source C:/Users/User/Desktop/My_Pro/HP_EliteBook_735_old/WORKSPACE/COMMON/.ssh-autostart.sh

# taskkill /F /IM python.exe