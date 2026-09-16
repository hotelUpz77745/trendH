# ============================================================
# FILE: cron_integration.py
# ROLE: Integrates configurations from external cron3Papper paths
# ============================================================
import os
import json
from c_log import log
from consts import cfg

class CronIntegration:
    @staticmethod
    def get_symbols() -> list[str]:
        try:
            data_sources = cfg.get("data_sources", {})
            
            # Check hardcoded list first
            hardcoded_symbols = data_sources.get("hardcoded_symbols", [])
            if hardcoded_symbols and isinstance(hardcoded_symbols, list) and len(hardcoded_symbols) > 0:
                return hardcoded_symbols
                
            symbols_path = data_sources.get("symbols_path")
            if not symbols_path or not os.path.exists(symbols_path):
                return []
                
            with open(symbols_path, "r", encoding="utf-8") as f:
                app_json = json.load(f)
            return app_json.get("symbols", [])
        except Exception as e:
            log(f"[CronIntegration] Error reading symbols: {e}", level="ERROR")
            return []

    @staticmethod
    def get_symbol_state(symbol: str) -> dict:
        """
        Reads the runtime state for a given symbol from cron3Papper.
        Returns a dict with position stats:
        {
            "LONG": {"invest_size": float, "volume": float, "enabled": bool},
            "SHORT": {"invest_size": float, "volume": float, "enabled": bool}
        }
        Volume represents the base asset quantity accumulated across grid layers.
        """
        result = {
            "LONG": {"invest_size": 0.0, "volume": 0.0, "enabled": False},
            "SHORT": {"invest_size": 0.0, "volume": 0.0, "enabled": False}
        }
        
        try:
            data_sources = cfg.get("data_sources", {})
            hardcoded_size = data_sources.get("hardcoded_size")
            
            # If hardcoded_size is provided and > 0, use it as default size
            if hardcoded_size is not None and float(hardcoded_size) > 0:
                size_val = float(hardcoded_size)
                result["LONG"] = {"invest_size": size_val, "volume": 0.0, "enabled": True}
                result["SHORT"] = {"invest_size": size_val, "volume": 0.0, "enabled": True}
                return result

            runtime_path = data_sources.get("runtime_path")
            if not runtime_path or not os.path.exists(runtime_path):
                return result
                
            file_path = os.path.join(runtime_path, f"{symbol}.json")
            if not os.path.exists(file_path):
                return result

            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            for side in ["LONG", "SHORT"]:
                if side in data:
                    side_data = data[side]
                    result[side]["enabled"] = side_data.get("enable", False)
                    result[side]["invest_size"] = side_data.get("invest_size", 0.0)
                    
                    # Accumulate volume based on grid logic with "is_active" flags
                    total_vol_pct = 0.0
                    grid = side_data.get("grid", {})
                    for key, val in grid.items():
                        if val.get("is_active", False):
                            total_vol_pct += val.get("volume", 0.0)
                            
                    # Calculate total size in USD
                    invest_size = side_data.get("invest_size", 0.0)
                    total_size_usd = (total_vol_pct / 100.0) * invest_size if total_vol_pct > 0 else 0.0
                    
                    # Override with hardcoded size if provided
                    if hardcoded_size is not None and hardcoded_size > 0:
                        total_size_usd = float(hardcoded_size)
                    
                    # Store calculated size
                    result[side]["invest_size"] = total_size_usd
                    
                    # Return raw data for analytics to process if needed
                    result[side]["raw_grid"] = grid
                    
        except Exception as e:
            log(f"[CronIntegration] Error reading state for {symbol}: {e}", level="ERROR")
            
        return result
