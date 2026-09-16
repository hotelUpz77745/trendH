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
    ANALYTICS_CFG,
    PAPER_TRADING_CFG,
    TG_ENABLED,
    TG_TOKEN,
    CFG_PATH,
    ANALYTICS_DIR,
    DATA_DIR
)


class BotState:
    def __init__(self):
        # symbol -> {"LONG": PositionState, "SHORT": PositionState}
        self.positions: Dict[str, Dict[str, PositionState]] = {}
        self.backup_manager = None

    def get_state_path(self):
        from consts import DATA_DIR
        return DATA_DIR / "state.json"

    def load_state(self):
        path = self.get_state_path()
        if not path.exists():
            return
        try:
            import json
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            for sym, sides in data.items():
                if sym not in self.positions:
                    self.positions[sym] = {
                        "LONG": PositionState(symbol=sym, side="LONG"),
                        "SHORT": PositionState(symbol=sym, side="SHORT")
                    }
                for side, pos_dict in sides.items():
                    if pos_dict.get("is_active"):
                        pos = self.positions[sym][side]
                        pos.is_active = True
                        pos.open_price = float(pos_dict.get("open_price", 0.0))
                        pos.size = float(pos_dict.get("size", 0.0))
                        pos.open_time_ms = int(pos_dict.get("open_time_ms", 0))
            log(f"Успешно загружен стейт из {path.name}", level="INFO")
        except Exception as e:
            log(f"Ошибка загрузки стейта: {e}", level="ERROR")

    def save_state(self):
        path = self.get_state_path()
        try:
            import json
            data = {}
            for sym, sides in self.positions.items():
                data[sym] = {
                    "LONG": sides["LONG"].__dict__,
                    "SHORT": sides["SHORT"].__dict__
                }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            if self.backup_manager:
                self.backup_manager.mark_changed()
        except Exception as e:
            log(f"Ошибка сохранения стейта: {e}", level="ERROR")

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
        self.save_state()

    def close_position(self, symbol: str, side: str):
        if symbol in self.positions and side in self.positions[symbol]:
            self.positions[symbol][side].reset()
            self.save_state()

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
        self.watchdog_task = None
        self.backup_task = None
        self.auto_closing_task = None
        self.is_paused = not cfg.get("auto_start", True)
        self.direction_mode = DIRECTION_MODE
        
        self.watchdog = LoopWatchdog(self.notifier)
        self.backup_manager = RuntimeBackupManager(self.notifier)
        self.state.backup_manager = self.backup_manager
        self.state.load_state()

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
        log(f" Klines history loaded for {len(self.symbols)} symbols.", level="INFO")
        
        # Рассчитываем стартовые индикаторы для всех символов сразу
        for sym in self.symbols:
            if sym in self.klines_cache:
                klines_data = {}
                for tf, ts_dict in self.klines_cache[sym].items():
                    sorted_ts = sorted(ts_dict.keys())
                    if sorted_ts:
                        klines_data[tf] = [ts_dict[ts] for ts in sorted_ts[-history_size:]]
                if klines_data:
                    self.symbol_indicators[sym] = self.indicators_engine.calculate(klines_data)

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
                    fee_ratio = ANALYTICS_CFG.get("taker_fee_ratio", 0) * 2
                    slippage_ratio = self.get_slippage_ratio(symbol) * 2
                    fee_slip_ratio = fee_ratio + slippage_ratio
                    
                    if side == "LONG":
                        pnl_ratio = (current_price - pos.open_price) / pos.open_price
                    else:
                        pnl_ratio = (pos.open_price - current_price) / pos.open_price
                        
                    pnl_usd = (pnl_ratio * pos.size)
                    comm_usd = -(fee_slip_ratio * pos.size)
                    pnl_pct = pnl_ratio * 100
                    
                    log(f"🎯 [SIGNAL EXIT] [{symbol}][{side}] Выход по сигналу! Вход: {pos.open_price:.4f} → Выход: {current_price:.4f} | PnL: {pnl_pct:+.2f}% ({pnl_usd:+.2f}$)", level="INFO")
                    self.analytics.record_virtual_trade(symbol, side, pnl_usd, comm_usd)
                    self.state.close_position(symbol, side)
                    log(f"🔴 [POSITION CLOSED] [{symbol}][{side}] Закрыта позиция. PnL: {pnl_usd:.4f}$, комиссия/проскальзывание: {comm_usd:.4f}$", level="INFO")
            else:
                # Check entry
                if not self.is_paused and self.check_entry(symbol, side):
                    cron_state = CronIntegration.get_symbol_state(symbol)
                    invest_size = cron_state.get(side, {}).get("invest_size", 0.0)
                    rsi_val = indicators.get("rsi_value")
                    rsi_str = f"{rsi_val:.1f}" if rsi_val is not None else "N/A"
                    log(f"🎯 [SIGNAL ENTRY] [{symbol}][{side}] Сигнал на вход! Trend: {indicators['trend']}, RSI: {rsi_str} ({','.join(indicators['rsi'])}), Цена: {current_price}", level="INFO")
                    if invest_size > 0:
                        log(f"🟢 [POSITION OPEN] [{symbol}][{side}] Открытие позиции. Цена: {current_price}, Размер: {invest_size}$", level="INFO")
                        self.state.open_position(symbol, side, current_price, invest_size)
                    else:
                        log(f"⚠️ [SIGNAL SKIPPED] [{symbol}][{side}] Сигнал есть, но invest_size={invest_size}$ (вход пропущен)", level="WARNING")

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
                
        log(f" Close All: Успешно закрыто {closed_count} виртуальных позиций.", level="INFO")

    async def indicators_daemon(self):
        """Фоновый процесс обновления индикаторов (скачивание свечей)."""
        log(" Запущен indicators_daemon.", level="INFO")
        while True:
            try:
                if self.symbols and not self.is_paused:
                    tasks = [self.update_indicators(self.network.session, sym) for sym in self.symbols]
                    if tasks:
                        await asyncio.gather(*tasks)

                    # Логирование показателей тренда и RSI по всем отслеживаемым парам
                    signal_summary = {"LONG": [], "SHORT": [], "NONE": 0}
                    for sym in self.symbols:
                        ind = self.symbol_indicators.get(sym)
                        if not ind:
                            continue
                        trend = ind.get("trend", "UNSTABLE")
                        rsi_val = ind.get("rsi_value")
                        rsi_str = f"{rsi_val:.1f}" if rsi_val is not None else "N/A"
                        rsi_states = ind.get("rsi", [])
                        
                        has_long = self.check_entry(sym, "LONG")
                        has_short = self.check_entry(sym, "SHORT")
                        
                        if has_long:
                            sig_label = "🟢 [LONG]"
                            signal_summary["LONG"].append(sym)
                        elif has_short:
                            sig_label = "🔴 [SHORT]"
                            signal_summary["SHORT"].append(sym)
                        else:
                            sig_label = "⚪ [-]"
                            signal_summary["NONE"] += 1
                            
                        log(f"📊 [IND] {sym:<12} | Trend: {trend:<8} | RSI: {rsi_str:>5} ({','.join(rsi_states)}) | Sig: {sig_label}", level="INFO")
                        
                    longs_str = ", ".join(signal_summary["LONG"]) if signal_summary["LONG"] else "нет"
                    shorts_str = ", ".join(signal_summary["SHORT"]) if signal_summary["SHORT"] else "нет"
                    log(f"📊 [IND SUMMARY] Обновлено {len(self.symbols)} пар. Сигналы входа: LONG [{len(signal_summary['LONG'])}]: {longs_str} | SHORT [{len(signal_summary['SHORT'])}]: {shorts_str} | Без сигнала: {signal_summary['NONE']}", level="INFO")
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
                self.tg_task = asyncio.create_task(self.tg_bot.start())
                log(" TelegramReceiver успешно запущен параллельно с ядром.", level="INFO")
            except Exception as e:
                log(f"Не удалось инициализировать TelegramReceiver: {e}", level="ERROR")

        log(" Бот успешно запущен (Paper Trading mode)", level="INFO")
        try:
            self.symbols = CronIntegration.get_symbols()
            if self.symbols:
                await self.init_klines_cache(session)
                self.price_stream = BinanceHotPriceStream(self.symbols)
                self.stream_task = asyncio.create_task(self.price_stream.run(self.on_tick))
                log(f"Запущен HotPriceStream для {len(self.symbols)} пар.", level="INFO")
                
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
            
            if self.tg_task:
                self.tg_task.cancel()
                tasks_to_wait.append(self.tg_task)
            if hasattr(self, 'indicators_task') and self.indicators_task:
                self.indicators_task.cancel()
                tasks_to_wait.append(self.indicators_task)
            if hasattr(self, 'volumes_task') and self.volumes_task:
                self.volumes_task.cancel()
                tasks_to_wait.append(self.volumes_task)
            if hasattr(self, 'auto_closing_task') and self.auto_closing_task:
                self.auto_closing_task.cancel()
                tasks_to_wait.append(self.auto_closing_task)
            if self.stream_task:
                self.stream_task.cancel()
                tasks_to_wait.append(self.stream_task)
                
            self.watchdog.stop()
            if self.watchdog_task:
                self.watchdog_task.cancel()
                tasks_to_wait.append(self.watchdog_task)
                
            self.backup_manager.stop()
            if self.backup_task:
                self.backup_task.cancel()
                tasks_to_wait.append(self.backup_task)
                
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