# ============================================================
# FILE: analytics.py
# ROLE: Paper Trading Analytics & Virtual Trade Ledger
# ============================================================

import asyncio
import json
import csv
import time
import os
from datetime import datetime, timezone
from pathlib import Path
from consts import ANALYTICS_DIR
from c_log import log
from ANALYTICS.metrics import AnalyticsMathEngine

class AnalyticsManager:
    """
    Ведет журнал сделок и статистику закрытых виртуальных позиций.
    """
    def __init__(self):
        self.log_file = ANALYTICS_DIR / "analytics.json"
        self.txt_file = ANALYTICS_DIR / "trades_ledger.txt"
        self._lock = asyncio.Lock()
        self._csv_lock = asyncio.Lock()
        self._ensure_files()

    def _ensure_files(self):
        if not self.log_file.exists():
            current_ms = int(time.time() * 1000)
            default_data = {
                "start_balance_usdt": 0.0,
                "first_trade_ts": current_ms,
                "cur_balance_usdt": 0.0,
                "total_trades": 0,
                "winning_trades": 0,
                "winrate_pct": 0.0,
                "realized_pnl_usdt": 0.0,
                "net_profit_usdt": 0.0,
                "unrealized_pnl_usdt": 0.0,
                "per_coin": {}
            }
            self.log_file.write_text(json.dumps(default_data, indent=4), encoding="utf-8")
        
        if not self.txt_file.exists():
            with open(self.txt_file, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerow(["Symbol", "Side", "Open Time", "Close Time", "PnL (USDT)", "Balance"])

    def _read_data(self) -> dict:
        if not self.log_file.exists():
            self._ensure_files()
            
        try:
            return json.loads(self.log_file.read_text(encoding="utf-8"))
        except Exception as e:
            log(f"Error reading analytics file: {e}", level="ERROR")
            return {}

    def _write_data(self, data: dict, mark_backup: bool = True):
        try:
            AnalyticsMathEngine.calculate(data)
            temp_file = self.log_file.with_suffix('.tmp')
            temp_file.write_text(json.dumps(data, indent=4), encoding="utf-8")
            os.replace(temp_file, self.log_file)
        except Exception as e:
            log(f"Error writing analytics file: {e}", level="ERROR")

    async def _append_to_csv(self, symbol: str, side: str, open_time: int, close_time: int, pnl: float, balance: float):
        async with self._csv_lock:
            try:
                def ts_to_str(ts_ms):
                    if not ts_ms:
                        return "Unknown"
                    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

                open_str = ts_to_str(open_time)
                close_str = ts_to_str(close_time)

                file_exists = self.txt_file.exists()
                if not file_exists:
                    with open(self.txt_file, mode="w", newline="", encoding="utf-8") as f:
                        writer = csv.writer(f, delimiter=';')
                        writer.writerow(["Symbol", "Side", "Open Time", "Close Time", "PnL", "Balance"])

                with open(self.txt_file, mode="a", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f, delimiter=';')
                    writer.writerow([symbol, side, open_str, close_str, round(pnl, 4), round(balance, 4)])
                    
            except Exception as e:
                log(f"Error appending to CSV: {e}", level="ERROR")

    def record_virtual_trade(self, symbol: str, side: str, pnl: float, comm: float, open_time_ms: int = 0):
        """Считает PNL и комиссии от каждой виртуальной сделки на лету."""
        asyncio.create_task(self._process_virtual_trade(symbol, side, pnl, comm, open_time_ms=open_time_ms))

    async def _process_virtual_trade(self, symbol: str, side: str, pnl: float, comm: float, open_time_ms: int = 0):
        async with self._lock:
            data = self._read_data()
            if not data:
                return
                
            net = pnl + comm
            data["realized_pnl_usdt"] = data.get("realized_pnl_usdt", 0.0) + pnl
            data["net_profit_usdt"] = data.get("net_profit_usdt", 0.0) + net
            data["cur_balance_usdt"] = data.get("cur_balance_usdt", 0.0) + net
            
            per_coin = data.setdefault("per_coin", {})
            coin_data = per_coin.setdefault(symbol, {
                "realized_pnl_usdt": 0.0, 
                "commission_usdt": 0.0,
                "win_count": 0, 
                "loss_count": 0,
                "trades": 0
            })
            
            coin_data["realized_pnl_usdt"] = coin_data.get("realized_pnl_usdt", 0.0) + pnl
            coin_data["commission_usdt"] = coin_data.get("commission_usdt", 0.0) + comm
            
            if pnl > 0:
                coin_data["win_count"] = coin_data.get("win_count", 0) + 1
                data["winning_trades"] = data.get("winning_trades", 0) + 1
            elif pnl < 0:
                coin_data["loss_count"] = coin_data.get("loss_count", 0) + 1
                
            if pnl != 0:
                coin_data["trades"] = coin_data.get("trades", 0) + 1
                data["total_trades"] = data.get("total_trades", 0) + 1
                
            self._write_data(data)
            
        if pnl != 0:
            now_ms = int(time.time() * 1000)
            ot = open_time_ms if open_time_ms > 0 else now_ms
            await self._append_to_csv(symbol, side, ot, now_ms, net, data.get("cur_balance_usdt", 0.0))
