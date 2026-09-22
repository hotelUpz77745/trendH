import json
import os

cron_path = "C:/Users/user/Desktop/My_Pro/HP_EliteBook_735_old/MY/HRON_3/cron3Papper/ANALYTICS/analytics.json"
trend_path = "logs/analytics/analytics_u_shadow_harvester_50.json"
trend_symb_path = "logs/analytics/analytics_u_hvh_delta_symbiosis.json"

try:
    with open(cron_path, "r", encoding="utf-8") as f:
        cron_data = json.load(f)
except Exception as e:
    print(f"Error loading cron analytics: {e}")
    cron_data = {}

try:
    with open(trend_path, "r", encoding="utf-8") as f:
        trend_data = json.load(f)
except Exception as e:
    print(f"Error loading trend analytics: {e}")
    trend_data = {}

cron_per_coin = cron_data.get("per_coin", {})
trend_per_coin = trend_data.get("per_coin", {})

print(f"Total coins in cron3Papper: {len(cron_per_coin)}")
print(f"Total coins in harvester_50: {len(trend_per_coin)}")

# Correlation study
merged = []
for sym, c_stats in cron_per_coin.items():
    c_net = c_stats.get("net_profit_usdt", c_stats.get("realized_pnl_net_usdt", 0.0))
    c_trades = c_stats.get("trades", 0)
    c_drme = c_stats.get("DRME", 0.0)
    c_mdme = c_stats.get("MDME", 0.0)
    
    t_stats = trend_per_coin.get(sym, {})
    t_net = t_stats.get("net_profit_usdt", 0.0)
    t_trades = t_stats.get("trades", 0)
    t_wr = t_stats.get("winrate_pct", 0.0)
    
    merged.append({
        "symbol": sym,
        "cron_net": c_net,
        "cron_trades": c_trades,
        "cron_drme": c_drme,
        "trend_net": t_net,
        "trend_trades": t_trades,
        "trend_wr": t_wr
    })

# Sort by cron_net
merged_by_cron = sorted(merged, key=lambda x: x["cron_net"], reverse=True)

print("\n=== TOP 10 COINS WITH HIGHEST CRON NET PROFIT (Grid Cash Cows) ===")
print(f"{'Coin':15} | {'Grid Net':10} | {'Grid Tr':7} | {'Trend Net':10} | {'Trend Tr':8} | {'Trend WR':8}")
print("-" * 75)
for m in merged_by_cron[:10]:
    print(f"{m['symbol']:15} | {m['cron_net']:+9.2f}$ | {m['cron_trades']:7d} | {m['trend_net']:+9.2f}$ | {m['trend_trades']:8d} | {m['trend_wr']:7.1f}%")

print("\n=== BOTTOM 10 COINS WITH LOWEST CRON NET PROFIT (Grid Losers / Drawdown) ===")
print(f"{'Coin':15} | {'Grid Net':10} | {'Grid Tr':7} | {'Trend Net':10} | {'Trend Tr':8} | {'Trend WR':8}")
print("-" * 75)
for m in merged_by_cron[-10:]:
    print(f"{m['symbol']:15} | {m['cron_net']:+9.2f}$ | {m['cron_trades']:7d} | {m['trend_net']:+9.2f}$ | {m['trend_trades']:8d} | {m['trend_wr']:7.1f}%")

# Let's test the User's Theory:
# "What if TrendH ONLY traded coins where Grid Net < 0 (or Grid Net <= 0)?"
traded = [m for m in merged if m["trend_trades"] > 0]
rule_all = sum(m["trend_net"] for m in traded)
rule_grid_neg = sum(m["trend_net"] for m in traded if m["cron_net"] <= 0)
rule_grid_pos = sum(m["trend_net"] for m in traded if m["cron_net"] > 0)

count_neg = len([m for m in traded if m["cron_net"] <= 0])
count_pos = len([m for m in traded if m["cron_net"] > 0])

print("\n=== USER THEORY BACKTEST: Filter TrendH by Grid Net Sign ===")
print(f"Base Harvester 50 (All traded coins): {rule_all:+.2f}$ ({len(traded)} coins)")
print(f"Rule 1: Trade ONLY when Grid Net <= 0 : {rule_grid_neg:+.2f}$ ({count_neg} coins)")
print(f"Rule 2: Traded when Grid Net > 0      : {rule_grid_pos:+.2f}$ ({count_pos} coins)")
