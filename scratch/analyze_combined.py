import os
import json

cron_path = "C:/Users/user/Desktop/My_Pro/HP_EliteBook_735_old/MY/HRON_3/cron3Papper/ANALYTICS/analytics.json"
with open(cron_path, "r", encoding="utf-8") as f:
    cron = json.load(f).get("per_coin", {})

target_strats = [
    "u_shadow_harvester_50",
    "u_shadow_harvester_40",
    "u_delta_harvester",
    "u_delta_sniper_15m",
    "u_hvh_delta_symbiosis",
]

th_agg = {}
for s in target_strats:
    fpath = f"logs/analytics/analytics_{s}.json"
    if os.path.exists(fpath):
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f).get("per_coin", {})
        for sym, c in data.items():
            if sym not in th_agg:
                th_agg[sym] = {"net": 0.0, "trades": 0, "wins": 0, "by_strat": {}}
            net = float(c.get("net_profit_usdt", 0.0))
            trades = int(c.get("trades", 0))
            wins = int(c.get("win_count", 0))
            th_agg[sym]["net"] += net
            th_agg[sym]["trades"] += trades
            th_agg[sym]["wins"] += wins
            th_agg[sym]["by_strat"][s] = net

coins = set(cron.keys()) | set(th_agg.keys())
table = []
for sym in coins:
    g = cron.get(sym, {})
    g_net = float(g.get("net_profit_usdt", 0.0))
    g_real = float(g.get("realized_pnl_net_usdt", 0.0))
    drme = float(g.get("DRME", 0.0))
    th = th_agg.get(sym, {"net": 0.0, "trades": 0, "wins": 0, "by_strat": {}})
    th_net = th["net"]
    trades = th["trades"]
    wr = (th["wins"] / trades * 100) if trades > 0 else 0
    comb_net = g_net + th_net
    table.append((sym, g_net, g_real, th_net, comb_net, wr, trades, drme, th.get("by_strat", {})))

table.sort(key=lambda x: x[4], reverse=True)
print(f"{'Symbol':<14} | {'Grid Net':<9} | {'TrendH Net':<11} | {'Comb Net':<9} | {'WR%':<5} | {'Trades':<6} | {'DRME':<6} | {'Strats'}")
print("-" * 95)
for sym, g_net, g_real, th_net, comb, wr, tr, drme, strats in table[:15]:
    strats_str = ", ".join(f"{k}:{v:+.1f}" for k, v in strats.items() if abs(v) > 0.01)
    print(f"{sym:<14} | {g_net:>8.2f}$ | {th_net:>10.2f}$ | {comb:>8.2f}$ | {wr:>4.0f}% | {tr:>6} | {drme:>6.3f} | {strats_str}")

print("\n--- BOTTOM 10 BY COMBINED NET ---")
for sym, g_net, g_real, th_net, comb, wr, tr, drme, strats in table[-10:]:
    strats_str = ", ".join(f"{k}:{v:+.1f}" for k, v in strats.items() if abs(v) > 0.01)
    print(f"{sym:<14} | {g_net:>8.2f}$ | {th_net:>10.2f}$ | {comb:>8.2f}$ | {wr:>4.0f}% | {tr:>6} | {drme:>6.3f} | {strats_str}")
