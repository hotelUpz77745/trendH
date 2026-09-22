import json

with open("cfg.json", "r", encoding="utf-8") as f:
    cfg = json.load(f)

universes = cfg.setdefault("universes", {})

# 1. u_sh50_outsiders
universes["u_sh50_outsiders"] = {
    "name": "Shadow Harvester 50% (Outsiders Only)",
    "description": "Вход против застрявшей сетки cron3 (уровень 2+, ratio >= 0.5) ТОЛЬКО на монетах-аутсайдерах с отрицательным PnL сетки (Grid Net <= 0)",
    "is_active": True,
    "enter_rules": {
        "grid_stress": {
            "is_active": True,
            "min_volume_ratio": 0.5,
            "min_filled_level": 2,
            "long_cond": "SHORT_GRID_STRESSED",
            "short_cond": "LONG_GRID_STRESSED"
        },
        "grid_net_filter": {
            "is_active": True,
            "mode": "OUTSIDERS_ONLY",
            "max_grid_net": 0.0
        }
    },
    "exit_rules": {
        "chandelier_exit": {"is_active": True, "length": 15, "atr_mult": 2.5},
        "time_stop": {"is_active": True, "max_seconds": 1200.0},
        "take_profit_ratio": {"value": 0.015},
        "stop_loss_ratio": {"value": 0.015},
        "grid_relief": {"is_active": True, "exit_on_position_close": True, "max_volume_ratio": 0.2}
    },
    "hedge_ratio": {"0": 1.0, "1": 1.0, "2": 0.75, "3": 0.75, "default": 0.5}
}

# 2. u_sh50_notop
universes["u_sh50_notop"] = {
    "name": "Shadow Harvester 50% (No Cash Cows)",
    "description": "Вход против застрявшей сетки cron3 при ratio >= 0.5 с баном топ-10 кэш-коров сетки (отсечение флэтовых ловушек)",
    "is_active": True,
    "enter_rules": {
        "grid_stress": {
            "is_active": True,
            "min_volume_ratio": 0.5,
            "min_filled_level": 2,
            "long_cond": "SHORT_GRID_STRESSED",
            "short_cond": "LONG_GRID_STRESSED"
        },
        "grid_net_filter": {
            "is_active": True,
            "mode": "EXCLUDE_TOP_CASH_COWS",
            "exclude_top_n": 10
        }
    },
    "exit_rules": {
        "chandelier_exit": {"is_active": True, "length": 15, "atr_mult": 2.5},
        "time_stop": {"is_active": True, "max_seconds": 1200.0},
        "take_profit_ratio": {"value": 0.015},
        "stop_loss_ratio": {"value": 0.015},
        "grid_relief": {"is_active": True, "exit_on_position_close": True, "max_volume_ratio": 0.2}
    },
    "hedge_ratio": {"0": 1.0, "1": 1.0, "2": 0.75, "3": 0.75, "default": 0.5}
}

# 3. u_sh40_outsiders
universes["u_sh40_outsiders"] = {
    "name": "Shadow Harvester 40% (Outsiders Only)",
    "description": "Ранний вход при 40% объема сетки cron3 ТОЛЬКО на монетах-аутсайдерах сетки (Grid Net <= 0)",
    "is_active": True,
    "enter_rules": {
        "grid_stress": {
            "is_active": True,
            "min_volume_ratio": 0.4,
            "min_filled_level": 2,
            "long_cond": "SHORT_GRID_STRESSED",
            "short_cond": "LONG_GRID_STRESSED"
        },
        "grid_net_filter": {
            "is_active": True,
            "mode": "OUTSIDERS_ONLY",
            "max_grid_net": 0.0
        }
    },
    "exit_rules": {
        "chandelier_exit": {"is_active": True, "length": 15, "atr_mult": 2.5},
        "time_stop": {"is_active": True, "max_seconds": 1200.0},
        "take_profit_ratio": {"value": 0.015},
        "stop_loss_ratio": {"value": 0.015},
        "grid_relief": {"is_active": True, "exit_on_position_close": True, "max_volume_ratio": 0.2}
    },
    "hedge_ratio": {"0": 1.0, "1": 1.0, "2": 0.75, "3": 0.75, "default": 0.5}
}

# 4. u_sh40_notop
universes["u_sh40_notop"] = {
    "name": "Shadow Harvester 40% (No Cash Cows)",
    "description": "Ранний вход при 40% объема сетки cron3 с баном топ-10 кэш-коров сетки",
    "is_active": True,
    "enter_rules": {
        "grid_stress": {
            "is_active": True,
            "min_volume_ratio": 0.4,
            "min_filled_level": 2,
            "long_cond": "SHORT_GRID_STRESSED",
            "short_cond": "LONG_GRID_STRESSED"
        },
        "grid_net_filter": {
            "is_active": True,
            "mode": "EXCLUDE_TOP_CASH_COWS",
            "exclude_top_n": 10
        }
    },
    "exit_rules": {
        "chandelier_exit": {"is_active": True, "length": 15, "atr_mult": 2.5},
        "time_stop": {"is_active": True, "max_seconds": 1200.0},
        "take_profit_ratio": {"value": 0.015},
        "stop_loss_ratio": {"value": 0.015},
        "grid_relief": {"is_active": True, "exit_on_position_close": True, "max_volume_ratio": 0.2}
    },
    "hedge_ratio": {"0": 1.0, "1": 1.0, "2": 0.75, "3": 0.75, "default": 0.5}
}

# 5. u_hvh_symbiosis_outsiders
universes["u_hvh_symbiosis_outsiders"] = {
    "name": "HVH Delta Symbiosis (Outsiders Only)",
    "description": "Флагманский симбиоз (1H тренд + 15m HVH всплеск + стресс сетки) ТОЛЬКО на аутсайдерах сетки (Grid Net <= 0)",
    "is_active": True,
    "enter_rules": {
        "trend_htf": {
            "is_active": True,
            "timeframe": "1h",
            "sma_fast": 10,
            "sma_slow": 30,
            "confirmation_candles": 2,
            "require_rising": True,
            "trend_positive": True,
            "long_cond": "UP",
            "short_cond": "DOWN"
        },
        "hvh": {
            "is_active": True,
            "timeframe": "15m",
            "min_volume_mult": 1.2,
            "window": 20,
            "long_cond": "HVH_LONG_ACTIVE",
            "short_cond": "HVH_SHORT_ACTIVE"
        },
        "grid_stress": {
            "is_active": True,
            "min_volume_ratio": 0.4,
            "min_filled_level": 2,
            "long_cond": "SHORT_GRID_STRESSED",
            "short_cond": "LONG_GRID_STRESSED"
        },
        "grid_net_filter": {
            "is_active": True,
            "mode": "OUTSIDERS_ONLY",
            "max_grid_net": 0.0
        }
    },
    "exit_rules": {
        "chandelier_exit": {"is_active": True, "length": 15, "atr_mult": 2.5},
        "grid_relief": {"is_active": True, "exit_on_position_close": True, "max_volume_ratio": 0.2}
    },
    "hedge_ratio": {"0": 1.0, "1": 1.0, "2": 0.75, "3": 0.75, "default": 0.5}
}

# 6. u_hvh_symbiosis_notop
universes["u_hvh_symbiosis_notop"] = {
    "name": "HVH Delta Symbiosis (No Cash Cows)",
    "description": "Симбиоз (1H тренд + 15m HVH + стресс сетки) с баном топ-10 кэш-коров сетки",
    "is_active": True,
    "enter_rules": {
        "trend_htf": {
            "is_active": True,
            "timeframe": "1h",
            "sma_fast": 10,
            "sma_slow": 30,
            "confirmation_candles": 2,
            "require_rising": True,
            "trend_positive": True,
            "long_cond": "UP",
            "short_cond": "DOWN"
        },
        "hvh": {
            "is_active": True,
            "timeframe": "15m",
            "min_volume_mult": 1.2,
            "window": 20,
            "long_cond": "HVH_LONG_ACTIVE",
            "short_cond": "HVH_SHORT_ACTIVE"
        },
        "grid_stress": {
            "is_active": True,
            "min_volume_ratio": 0.4,
            "min_filled_level": 2,
            "long_cond": "SHORT_GRID_STRESSED",
            "short_cond": "LONG_GRID_STRESSED"
        },
        "grid_net_filter": {
            "is_active": True,
            "mode": "EXCLUDE_TOP_CASH_COWS",
            "exclude_top_n": 10
        }
    },
    "exit_rules": {
        "chandelier_exit": {"is_active": True, "length": 15, "atr_mult": 2.5},
        "grid_relief": {"is_active": True, "exit_on_position_close": True, "max_volume_ratio": 0.2}
    },
    "hedge_ratio": {"0": 1.0, "1": 1.0, "2": 0.75, "3": 0.75, "default": 0.5}
}

# 7. u_symb_harv_outsiders
universes["u_symb_harv_outsiders"] = {
    "name": "Symbiosis Harvester (Outsiders Only)",
    "description": "Жнец стресса сетки 40% с защитой Profit Stagnation Exit ТОЛЬКО на монетах-аутсайдерах сетки (Grid Net <= 0)",
    "is_active": True,
    "enter_rules": {
        "grid_stress": {
            "is_active": True,
            "min_volume_ratio": 0.4,
            "min_filled_level": 2,
            "long_cond": "SHORT_GRID_STRESSED",
            "short_cond": "LONG_GRID_STRESSED"
        },
        "grid_net_filter": {
            "is_active": True,
            "mode": "OUTSIDERS_ONLY",
            "max_grid_net": 0.0
        }
    },
    "exit_rules": {
        "chandelier_exit": {"is_active": True, "length": 15, "atr_mult": 2.5},
        "profit_stagnation": {
            "is_active": True,
            "be_trigger_ratio": 0.028,
            "be_buffer_ratio": 0.003,
            "min_profit_ratio": 0.05,
            "stagnation_seconds": 1800.0,
            "progress_threshold": 0.005
        },
        "grid_relief": {"is_active": True, "exit_on_position_close": True, "max_volume_ratio": 0.2}
    },
    "hedge_ratio": {"0": 1.0, "1": 1.0, "2": 0.75, "3": 0.75, "default": 0.5}
}

# 8. u_symb_harv_notop
universes["u_symb_harv_notop"] = {
    "name": "Symbiosis Harvester (No Cash Cows)",
    "description": "Жнец стресса сетки 40% с защитой Profit Stagnation Exit и баном топ-10 кэш-коров сетки",
    "is_active": True,
    "enter_rules": {
        "grid_stress": {
            "is_active": True,
            "min_volume_ratio": 0.4,
            "min_filled_level": 2,
            "long_cond": "SHORT_GRID_STRESSED",
            "short_cond": "LONG_GRID_STRESSED"
        },
        "grid_net_filter": {
            "is_active": True,
            "mode": "EXCLUDE_TOP_CASH_COWS",
            "exclude_top_n": 10
        }
    },
    "exit_rules": {
        "chandelier_exit": {"is_active": True, "length": 15, "atr_mult": 2.5},
        "profit_stagnation": {
            "is_active": True,
            "be_trigger_ratio": 0.028,
            "be_buffer_ratio": 0.003,
            "min_profit_ratio": 0.05,
            "stagnation_seconds": 1800.0,
            "progress_threshold": 0.005
        },
        "grid_relief": {"is_active": True, "exit_on_position_close": True, "max_volume_ratio": 0.2}
    },
    "hedge_ratio": {"0": 1.0, "1": 1.0, "2": 0.75, "3": 0.75, "default": 0.5}
}

# 9. u15_4h_rsi1d_std
universes["u15_4h_rsi1d_std"] = {
    "name": "Breakout LuxAlgo 4H + 1D RSI (Standard)",
    "description": "Институциональный пробой уровней LuxAlgo на 4H таймфрейме с дневным фильтром RSI (LONG < 70, SHORT > 30) и сайзингом сетки",
    "is_active": True,
    "enter_rules": {
        "trend_htf": {
            "is_active": True,
            "timeframe": "4h",
            "sma_fast": 10,
            "sma_slow": 30,
            "confirmation_candles": 2,
            "require_rising": True,
            "trend_positive": True,
            "long_cond": "UP",
            "short_cond": "DOWN"
        },
        "sr_levels": {
            "is_active": True,
            "timeframe": "4h",
            "swing_len": 15,
            "window": 100,
            "margin": 2.0,
            "thickness_k": 0.17,
            "max_zones": 10,
            "level_mode": "latest",
            "breakout_edge": "h",
            "long_cond": "BREAKOUT_LONG",
            "short_cond": "BREAKOUT_SHORT"
        },
        "rsi_1d": {
            "is_active": True,
            "timeframe": "1d",
            "period": 14
        },
        "daily_rsi": {
            "is_active": True,
            "timeframe": "1d",
            "max_rsi_long": 70.0,
            "min_rsi_short": 30.0
        },
        "taker_flow": {
            "is_active": True,
            "timeframe": "15m",
            "min_buy_ratio": 0.6,
            "max_buy_ratio": 0.4,
            "long_cond": "TAKER_BUY_DOMINANT",
            "short_cond": "TAKER_SELL_DOMINANT"
        }
    },
    "exit_rules": {
        "chandelier_exit": {"is_active": True, "length": 15, "atr_mult": 2.5},
        "time_stop": {"is_active": True, "max_seconds": 1800.0},
        "breakeven_ratchet": {"is_active": True, "trigger_ratio": 0.025, "buffer_ratio": 0.003},
        "stop_loss_ratio": {"value": 0.025}
    },
    "hedge_ratio": {"0": 1.0, "1": 1.0, "2": 0.75, "3": 0.75, "default": 0.5}
}

# 10. u15_4h_rsi1d_outsiders
universes["u15_4h_rsi1d_outsiders"] = {
    "name": "Breakout LuxAlgo 4H + 1D RSI (Outsiders Only)",
    "description": "Институциональный пробой уровней LuxAlgo на 4H с дневным RSI фильтром ТОЛЬКО на аутсайдерах сетки (Grid Net <= 0)",
    "is_active": True,
    "enter_rules": {
        "trend_htf": {
            "is_active": True,
            "timeframe": "4h",
            "sma_fast": 10,
            "sma_slow": 30,
            "confirmation_candles": 2,
            "require_rising": True,
            "trend_positive": True,
            "long_cond": "UP",
            "short_cond": "DOWN"
        },
        "sr_levels": {
            "is_active": True,
            "timeframe": "4h",
            "swing_len": 15,
            "window": 100,
            "margin": 2.0,
            "thickness_k": 0.17,
            "max_zones": 10,
            "level_mode": "latest",
            "breakout_edge": "h",
            "long_cond": "BREAKOUT_LONG",
            "short_cond": "BREAKOUT_SHORT"
        },
        "rsi_1d": {
            "is_active": True,
            "timeframe": "1d",
            "period": 14
        },
        "daily_rsi": {
            "is_active": True,
            "timeframe": "1d",
            "max_rsi_long": 70.0,
            "min_rsi_short": 30.0
        },
        "grid_net_filter": {
            "is_active": True,
            "mode": "OUTSIDERS_ONLY",
            "max_grid_net": 0.0
        },
        "taker_flow": {
            "is_active": True,
            "timeframe": "15m",
            "min_buy_ratio": 0.6,
            "max_buy_ratio": 0.4,
            "long_cond": "TAKER_BUY_DOMINANT",
            "short_cond": "TAKER_SELL_DOMINANT"
        }
    },
    "exit_rules": {
        "chandelier_exit": {"is_active": True, "length": 15, "atr_mult": 2.5},
        "time_stop": {"is_active": True, "max_seconds": 1800.0},
        "breakeven_ratchet": {"is_active": True, "trigger_ratio": 0.025, "buffer_ratio": 0.003},
        "stop_loss_ratio": {"value": 0.025}
    },
    "hedge_ratio": {"0": 1.0, "1": 1.0, "2": 0.75, "3": 0.75, "default": 0.5}
}

# 11. u_jem_matrix_harvest
universes["u_jem_matrix_harvest"] = {
    "name": "Jem Matrix Harvest (Institutional 3-Tier)",
    "description": "Авторский институциональный жнец Jem: синхронизация 3 уровней (4H тренд + 1D RSI + стресс сетки 40% на аутсайдерах + 15m HVH) с выходом по Stagnation Lock (+0.3% БУ при +2.8%, выход при застое > +5% за 30 мин)",
    "is_active": True,
    "enter_rules": {
        "trend_htf": {
            "is_active": True,
            "timeframe": "4h",
            "sma_fast": 10,
            "sma_slow": 30,
            "confirmation_candles": 2,
            "require_rising": True,
            "trend_positive": True,
            "long_cond": "UP",
            "short_cond": "DOWN"
        },
        "rsi_1d": {
            "is_active": True,
            "timeframe": "1d",
            "period": 14
        },
        "daily_rsi": {
            "is_active": True,
            "timeframe": "1d",
            "max_rsi_long": 70.0,
            "min_rsi_short": 30.0
        },
        "grid_stress": {
            "is_active": True,
            "min_volume_ratio": 0.4,
            "min_filled_level": 2,
            "long_cond": "SHORT_GRID_STRESSED",
            "short_cond": "LONG_GRID_STRESSED"
        },
        "grid_net_filter": {
            "is_active": True,
            "mode": "OUTSIDERS_ONLY",
            "max_grid_net": 0.0
        },
        "hvh": {
            "is_active": True,
            "timeframe": "15m",
            "min_volume_mult": 1.2,
            "window": 20,
            "long_cond": "HVH_LONG_ACTIVE",
            "short_cond": "HVH_SHORT_ACTIVE"
        },
        "taker_flow": {
            "is_active": True,
            "timeframe": "15m",
            "min_buy_ratio": 0.6,
            "max_buy_ratio": 0.4,
            "long_cond": "TAKER_BUY_DOMINANT",
            "short_cond": "TAKER_SELL_DOMINANT"
        }
    },
    "exit_rules": {
        "chandelier_exit": {"is_active": True, "length": 15, "atr_mult": 2.8},
        "profit_stagnation": {
            "is_active": True,
            "be_trigger_ratio": 0.028,
            "be_buffer_ratio": 0.003,
            "min_profit_ratio": 0.05,
            "stagnation_seconds": 1800.0,
            "progress_threshold": 0.005
        },
        "grid_relief": {"is_active": True, "exit_on_position_close": True, "max_volume_ratio": 0.2}
    },
    "hedge_ratio": {"0": 1.0, "1": 1.0, "2": 0.75, "3": 0.75, "default": 0.5}
}

# 12. u_jem_symbiotic_quantum
universes["u_jem_symbiotic_quantum"] = {
    "name": "Jem Quantum Symbiosis (Trend-First Engine)",
    "description": "Институциональный дельта-хеджер Jem Quantum: нацелен на режим FOR_TRENDH_FIRSTABLE. Активируется только при перекосе сетки >=50% на монетах с отрицательным Net PnL сетки, сопровождает вынос до полного исчерпания тренда с Breakeven Ratchet (+2.5%) и снятием при разгрузке сетки",
    "is_active": True,
    "enter_rules": {
        "trend_htf": {
            "is_active": True,
            "timeframe": "1h",
            "sma_fast": 10,
            "sma_slow": 30,
            "confirmation_candles": 2,
            "require_rising": True,
            "trend_positive": True,
            "long_cond": "UP",
            "short_cond": "DOWN"
        },
        "grid_stress": {
            "is_active": True,
            "min_volume_ratio": 0.5,
            "min_filled_level": 2,
            "long_cond": "SHORT_GRID_STRESSED",
            "short_cond": "LONG_GRID_STRESSED"
        },
        "grid_net_filter": {
            "is_active": True,
            "mode": "OUTSIDERS_ONLY",
            "max_grid_net": 0.0
        },
        "volatility_squeeze": {
            "is_active": True,
            "timeframe": "15m",
            "bb_period": 20,
            "bb_mult": 2.0,
            "kc_period": 20,
            "kc_mult": 1.5,
            "long_cond": "SQUEEZE_OFF_EXPANSION",
            "short_cond": "SQUEEZE_OFF_EXPANSION"
        }
    },
    "exit_rules": {
        "chandelier_exit": {"is_active": True, "length": 15, "atr_mult": 3.0},
        "profit_stagnation": {
            "is_active": True,
            "be_trigger_ratio": 0.028,
            "be_buffer_ratio": 0.003,
            "min_profit_ratio": 0.05,
            "stagnation_seconds": 1800.0,
            "progress_threshold": 0.005
        },
        "grid_relief": {"is_active": True, "exit_on_position_close": True, "max_volume_ratio": 0.2}
    },
    "hedge_ratio": {"0": 1.0, "1": 1.0, "2": 0.75, "3": 0.75, "default": 0.5}
}

with open("cfg.json", "w", encoding="utf-8") as f:
    json.dump(cfg, f, ensure_ascii=False, indent=4)

print(f"Successfully updated cfg.json! Total universes now: {len(universes)}")
