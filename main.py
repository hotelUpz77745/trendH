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
from CORE.watchdog import LoopWatchdog
from CORE.backup import RuntimeBackupManager
from CORE.squeeze_flow import RealtimeFlowTracker
from consts import AUTO_CLOSING_CFG

if TYPE_CHECKING:
    from API.price_stream import HotPriceTick
from consts import (
    cfg,
    MAIN_LOOP_DELAY_SEC,
    INDICATORS_REFRESH_INTERVAL_SEC,
    DIRECTION_MODE,
    ENTER_RULES,
    EXIT_RULES,
    UNIVERSES_CFG,
    ANALYTICS_CFG,
    PAPER_TRADING_CFG,
    TG_ENABLED,
    TG_TOKEN,
    CFG_PATH,
    ANALYTICS_DIR,
    DATA_DIR
)
from CORE.universe import UniverseManager


class Main:
    def __init__(self):
        self.utils = Utils()
        self.binance_client = BinanceAdapter()
        self.network = NetworkServices()
        self.symbols = []
        self.btc_symbol = "BTCUSDT"
        self.flow_tracker = RealtimeFlowTracker()
        self.symbol_indicators = {}  # symbol -> {"rsi": float, "trend": str}
        self.symbol_volume_24h = {}
        self.current_prices = {}  # symbol -> float
        self.klines_cache = {}  # symbol -> tf -> timestamp -> close
        self.api_semaphore = asyncio.Semaphore(10)
        self.notifier = NotifierManager()

        self.watchdog = LoopWatchdog(self.notifier, server_name="TrendH_Papper")
        self.backup_manager = RuntimeBackupManager(self.notifier)
        self._last_universe_eval_ms: Dict[str, int] = {}
        self.universe_throttle_ms: int = 50

        # Менеджер параллельных вселенных (мульти-стратегия)
        self.universe_manager = UniverseManager(
            universes_cfg=UNIVERSES_CFG,
            default_enter_rules=ENTER_RULES,
            default_exit_rules=EXIT_RULES,
            get_slippage_ratio_fn=self.get_slippage_ratio,
            backup_manager=self.backup_manager
        )

        # Фасадный расчет всех индикаторов, требуемых активными вселенными
        combined_rules = self.universe_manager.get_combined_enter_rules()
        self.indicators_engine = IndicatorsEngine(combined_rules)

        # Ссылки для обратной совместимости (первая активная вселенная)
        first_univ = list(self.universe_manager.universes.values())[0] if self.universe_manager.universes else None
        self.state = first_univ.state if first_univ else None
        self.analytics = first_univ.analytics if first_univ else AnalyticsManager()
        self.entry_engine = first_univ.entry_engine if first_univ else EntrySignalEngine(ENTER_RULES)
        self.exit_engine = first_univ.exit_engine if first_univ else ExitSignalEngine(EXIT_RULES, ANALYTICS_CFG, self.get_slippage_ratio)

        self.price_stream = None
        self.stream_task = None
        self.tg_bot = None
        self.tg_task = None
        self.watchdog_task = None
        self.backup_task = None
        self.auto_closing_task = None
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
        log(" Pre-fetching klines history for all symbols...", level="INFO")
        history_size = cfg.get("klines_history_size", 300)
        tfs = self.indicators_engine.get_required_timeframes()
        all_syms = list(set(self.symbols + [self.btc_symbol]))

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
                            self.klines_cache[sym][tf][int(k[0])] = {
                                "ts": int(k[0]),
                                "open": float(k[1]),
                                "high": float(k[2]),
                                "low": float(k[3]),
                                "close": float(k[4]),
                                "volume": float(k[5]),
                                "taker_buy_volume": float(k[9]) if len(k) > 9 else 0.0,
                            }
                await asyncio.sleep(0.01)

        tasks = [_fetch(sym) for sym in all_syms]
        await asyncio.gather(*tasks)
        log(f" Klines history loaded for {len(all_syms)} symbols.", level="INFO")

        # Стартовый расчет индикаторов
        btc_dict = self.klines_cache.get(self.btc_symbol, {}).get("5m", {})
        btc_ts = sorted(btc_dict.keys())
        btc_closes = [btc_dict[t]["close"] for t in btc_ts[-history_size:]] if btc_ts else []

        for sym in self.symbols:
            if sym in self.klines_cache:
                klines_data = {}
                for tf, ts_dict in self.klines_cache[sym].items():
                    sorted_ts = sorted(ts_dict.keys())
                    if sorted_ts:
                        klines_data[tf] = [ts_dict[ts] for ts in sorted_ts[-history_size:]]
                if klines_data:
                    flow = self.flow_tracker.get_flow(sym)
                    self.symbol_indicators[sym] = self.indicators_engine.calculate(
                        klines_data, current_price=self.current_prices.get(sym),
                        btc_closes=btc_closes, realtime_flow=flow
                    )

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
                        self.klines_cache[symbol][tf][int(k[0])] = {
                            "ts": int(k[0]),
                            "open": float(k[1]),
                            "high": float(k[2]),
                            "low": float(k[3]),
                            "close": float(k[4]),
                            "volume": float(k[5]),
                            "taker_buy_volume": float(k[9]) if len(k) > 9 else 0.0,
                        }

                sorted_ts = sorted(self.klines_cache[symbol][tf].keys())
                for ts in sorted_ts[:-history_size]:
                    del self.klines_cache[symbol][tf][ts]

                if sorted_ts:
                    klines_data[tf] = [self.klines_cache[symbol][tf][ts] for ts in sorted_ts[-history_size:]]

            if not klines_data:
                return

            btc_dict = self.klines_cache.get(self.btc_symbol, {}).get("5m", {})
            btc_ts = sorted(btc_dict.keys())
            btc_closes = [btc_dict[t]["close"] for t in btc_ts[-history_size:]] if btc_ts else []
            flow = self.flow_tracker.get_flow(symbol)

            self.symbol_indicators[symbol] = self.indicators_engine.calculate(
                klines_data, current_price=self.current_prices.get(symbol),
                btc_closes=btc_closes, realtime_flow=flow
            )
        except Exception as e:
            log(f"[{symbol}] Error updating indicators: {e}", level="ERROR")

    def check_entry(self, symbol: str, side: str) -> bool:
        indicators = self.symbol_indicators.get(symbol)
        return self.entry_engine.check_signal(side, indicators) if indicators else False

    def check_exit(self, symbol: str, side: str, open_price: float, current_price: float) -> bool:
        indicators = self.symbol_indicators.get(symbol)
        if not indicators:
            return False
        return self.exit_engine.check_signal(
            side, symbol=symbol, trend=indicators.get("trend", "UNSTABLE"), open_price=open_price, current_price=current_price
        )

    async def on_tick(self, tick: 'HotPriceTick'):
        """WebSocket callback triggered instantly on every price change."""
        symbol = tick.symbol
        current_price = tick.price
        self.current_prices[symbol] = current_price

        self.flow_tracker.add_trade(symbol, current_price, tick.qty, tick.is_buyer_maker, tick.event_time_ms)
        if symbol == self.btc_symbol and symbol not in self.symbols:
            await asyncio.sleep(0)
            return

        now_ms = tick.event_time_ms if tick.event_time_ms > 0 else int(time.time() * 1000)
        last_eval = self._last_universe_eval_ms.get(symbol, 0)
        if now_ms - last_eval < self.universe_throttle_ms:
            return
        self._last_universe_eval_ms[symbol] = now_ms

        indicators = self.symbol_indicators.get(symbol)
        if not indicators:
            return

        flow = self.flow_tracker.get_flow(symbol)
        if flow.get("signals") is not None and flow.get("total_vol", 0.0) > 0:
            indicators["taker_flow"] = flow["signals"]

        cron_state = CronIntegration.get_symbol_state(symbol)
        allow_long = self.direction_mode in ("LONG", "HEDGE", "MONO")
        allow_short = self.direction_mode in ("SHORT", "HEDGE", "MONO")

        for side in ["LONG", "SHORT"]:
            if side == "LONG" and not allow_long:
                continue
            if side == "SHORT" and not allow_short:
                continue
            invest_size = cron_state.get(side, {}).get("invest_size", 0.0)
            self.universe_manager.process_tick(
                symbol=symbol,
                side=side,
                current_price=current_price,
                indicators=indicators,
                get_slippage_ratio_fn=self.get_slippage_ratio,
                is_paused=self.is_paused,
                invest_size=invest_size
            )
        await asyncio.sleep(0)

    async def close_all_positions(self):
        """Экстренное закрытие всех виртуальных позиций по рынку во всех вселенных."""
        closed_count = self.universe_manager.close_all_positions(self.current_prices, self.get_slippage_ratio)
        log(f" Close All: Успешно закрыто {closed_count} виртуальных позиций во всех вселенных.", level="INFO")

    async def indicators_daemon(self):
        """Фоновый процесс обновления индикаторов (скачивание свечей)."""
        log(" Запущен indicators_daemon.", level="INFO")
        while True:
            try:
                if self.symbols and not self.is_paused:
                    all_syms = list(set(self.symbols + [self.btc_symbol]))
                    tasks = [self.update_indicators(self.network.session, sym) for sym in all_syms]
                    if tasks:
                        await asyncio.gather(*tasks)
            except Exception as ex:
                log(f"Error in indicators_daemon: {ex}", level="ERROR")
                traceback.print_exc()
            await asyncio.sleep(INDICATORS_REFRESH_INTERVAL_SEC)

    async def volumes_daemon(self):
        """Фоновый процесс обновления объемов за 24 часа."""
        log(" Запущен volumes_daemon.", level="INFO")
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

    async def auto_closing_daemon(self):
        if not AUTO_CLOSING_CFG:
            return
        log("Запущен auto_closing_daemon.", level="INFO")
        while True:
            try:
                analytics_data = self.utils.read_json_file(self.utils.get_analytics_path()) if hasattr(self.utils, "get_analytics_path") else self.utils.read_json_file(ANALYTICS_DIR / "analytics.json")
                if analytics_data:
                    net_profit = float(analytics_data.get("net_profit_usdt", 0.0))
                    
                    neg_cfg = AUTO_CLOSING_CFG.get("negative", {})
                    neg_thresh = neg_cfg.get("threshold")
                    if neg_thresh is not None and net_profit <= float(neg_thresh):
                        log(f"AUTO-CLOSING (Negative): {net_profit} <= {neg_thresh}", level="WARNING")
                        asyncio.create_task(self.close_all_positions())
                        msg = f"ВНИМАНИЕ! AUTO-CLOSING\nДостигнут лимит убытка ({neg_thresh} USDT). Все позиции закрываются!"
                        asyncio.create_task(self.notifier.send_alert(msg) if not hasattr(self.notifier, "tg_bot") else self.notifier.tg_bot.send_message_to_all(msg))
                        
                    pos_cfg = AUTO_CLOSING_CFG.get("positive", {})
                    pos_thresh = pos_cfg.get("threshold")
                    if pos_thresh is not None and net_profit >= float(pos_thresh):
                        log(f"AUTO-CLOSING (Positive): {net_profit} >= {pos_thresh}", level="WARNING")
                        asyncio.create_task(self.close_all_positions())
                        msg = f"ОТЛИЧНО! AUTO-CLOSING\nДостигнут лимит профита ({pos_thresh} USDT). Все позиции закрываются!"
                        asyncio.create_task(self.notifier.send_alert(msg) if not hasattr(self.notifier, "tg_bot") else self.notifier.tg_bot.send_message_to_all(msg))
            except Exception as e:
                log(f"Error in auto_closing_daemon: {e}", level="ERROR")
            
            await asyncio.sleep(5)

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
                self.notifier.tg_bot = self.tg_bot
                self.tg_task = asyncio.create_task(self.tg_bot.start())
                log(" TelegramReceiver успешно запущен параллельно с ядром.", level="INFO")
            except Exception as e:
                log(f"Не удалось инициализировать TelegramReceiver: {e}", level="ERROR")

        log(" Бот успешно запущен (Paper Trading mode)", level="INFO")
        try:
            self.symbols = CronIntegration.get_symbols()
            if self.symbols:
                await self.init_klines_cache(session)
                stream_syms = list(set(self.symbols + [self.btc_symbol]))
                self.price_stream = BinanceHotPriceStream(stream_syms)
                self.stream_task = asyncio.create_task(self.price_stream.run(self.on_tick))
                log(f"Запущен HotPriceStream для {len(stream_syms)} пар (включая {self.btc_symbol}).", level="INFO")
                
            self.indicators_task = asyncio.create_task(self.indicators_daemon())
            self.volumes_task = asyncio.create_task(self.volumes_daemon())
            self.auto_closing_task = asyncio.create_task(self.auto_closing_daemon())
            
            self.watchdog_task = asyncio.create_task(self.watchdog.start())
            self.backup_task = asyncio.create_task(self.backup_manager.start())
                
            while True:
                self.watchdog.tick()
                await asyncio.sleep(MAIN_LOOP_DELAY_SEC)

        except KeyboardInterrupt:
            log("Остановка по Ctrl+C", level="INFO")
        except asyncio.CancelledError:
            log("Остановка (CancelledError)", level="INFO")
        except Exception as ex:
            log(f"Сбой выполнения: {ex}", level="ERROR")
            import traceback
            traceback.print_exc()
        finally:
            log("Завершение работы...", level="INFO")
            tasks_to_wait = []
            
            for task_name in ('tg_task', 'indicators_task', 'volumes_task', 'auto_closing_task', 'stream_task', 'watchdog_task', 'backup_task'):
                t = getattr(self, task_name, None)
                if t:
                    t.cancel()
                    tasks_to_wait.append(t)

            self.watchdog.stop()
            self.backup_manager.stop()
                
            if self.tg_bot:
                await self.tg_bot.stop()
            if self.price_stream:
                self.price_stream.stop()
                
            if tasks_to_wait:
                await asyncio.gather(*tasks_to_wait, return_exceptions=True)
                
            await self.network.shutdown_session()
            log("Работа завершена. Сессии закрыты.", level="INFO")

if __name__ == "__main__":
    try:
        asyncio.run(Main().run())
    except (KeyboardInterrupt, asyncio.exceptions.CancelledError):
        pass

## шпору не трогать!!
# source C:/Users/User/Desktop/My_Pro/HP_EliteBook_735_old/WORKSPACE/COMMON/.ssh-autostart.sh
# taskkill /F /IM python.exe