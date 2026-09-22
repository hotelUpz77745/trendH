import json
import glob
import os
import sys

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

analytics_files = glob.glob("logs/analytics/analytics_*.json")
results = []

for fpath in analytics_files:
    uid = os.path.basename(fpath).replace("analytics_", "").replace(".json", "")
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
            net_profit = data.get("net_profit_usdt", 0.0)
            realized_gross = data.get("realized_pnl_usdt", 0.0)
            comm = abs(realized_gross - net_profit)
            trades = data.get("total_trades", 0)
            wins = data.get("winning_trades", 0)
            wr = data.get("winrate_pct", (wins / trades * 100.0) if trades > 0 else 0.0)
            dd = data.get("max_drawdown_usdt", 0.0)
            upnl = data.get("unrealized_pnl_usdt", 0.0)
            
            # Check open positions in state
            state_file = f"logs/data/state_{uid}.json"
            open_positions = []
            if os.path.exists(state_file):
                with open(state_file, "r", encoding="utf-8") as sf:
                    sdata = json.load(sf)
                    for s, sides in sdata.items():
                        for side, pos in sides.items():
                            if pos.get("is_active"):
                                open_positions.append({
                                    "symbol": s,
                                    "side": side,
                                    "open_price": pos.get("open_price", 0.0),
                                    "size": pos.get("size", 0.0)
                                })
                                
            results.append({
                "uid": uid,
                "net": net_profit,
                "gross": realized_gross,
                "comm": comm,
                "wr": wr,
                "trades": trades,
                "wins": wins,
                "dd": dd,
                "upnl": upnl,
                "open_count": len(open_positions),
                "open_positions": open_positions,
                "per_coin": data.get("per_coin", {})
            })
    except Exception as e:
        print(f"Error loading {uid}: {e}")

results.sort(key=lambda x: x["net"], reverse=True)

print("=" * 115)
print("                                 📊 СВОДНЫЙ ЛИДЕРБОРД ВСЕХ СТРАТЕГИЙ TRENDH 📊")
print("=" * 115)
print(f"{'#':2} | {'Стратегия':25} | {'Net PnL':9} | {'Комса':8} | {'WinRate':14} | {'Max DD':8} | {'uPnL':8} | {'Откр'}")
print("-" * 115)

for idx, r in enumerate(results, 1):
    med = "🥇 " if idx == 1 else "🥈 " if idx == 2 else "🥉 " if idx == 3 else f"{idx:2}. "
    net_str = f"{r['net']:+7.2f}$"
    comm_str = f"-{r['comm']:6.2f}$"
    wr_str = f"{r['wr']:5.1f}% ({r['wins']}/{r['trades']})"
    dd_str = f"-{abs(r['dd']):6.2f}$"
    upnl_str = f"{r['upnl']:+6.2f}$"
    print(f"{med}{r['uid']:25} | {net_str:9} | {comm_str:8} | {wr_str:14} | {dd_str:8} | {upnl_str:8} | {r['open_count']}")

print("=" * 115)

# Breakdown of the 3 key variants of Shadow Harvester 50
print("\n" + "=" * 115)
print("             ⚔️ СРАВНИТЕЛЬНЫЙ АНАЛИЗ: ТРИ ВАРИАЦИИ ЖНЕЦА 50% (SHORT vs MEDIUM vs WIDE) ⚔️")
print("=" * 115)

comp_uids = ["u_shadow_harvester_50", "u_shadow_harvester_mid", "u_shadow_harvester_wide", "u_grid_shadow_50"]
for cu in comp_uids:
    r = next((x for x in results if x["uid"] == cu), None)
    if not r:
        continue
    label = {
        "u_shadow_harvester_50": "1. SHADOW_HARVESTER_50 (Скальп-трейлинг: 2.5% -> BE, 1.8% trail)",
        "u_shadow_harvester_mid": "2. SHADOW_HARVESTER_MID (Свинг-трейлинг: 4.5% -> BE, 2.5% trail)",
        "u_shadow_harvester_wide": "3. SHADOW_HARVESTER_WIDE (Трендовый трейлинг: 7.0% -> BE, 3.5% trail)",
        "u_grid_shadow_50": "4. GRID_SHADOW_50 (Чистый хэдж без трейлинга, выход по сетке)"
    }.get(cu, cu)
    
    print(f"\n🔹 {label}:")
    print(f"   • Чистый Net PnL: {r['net']:+.2f}$ (Грязный: {r['gross']:+.2f}$, Комиссия бирже: -{r['comm']:.2f}$)")
    print(f"   • Сделок закрыто: {r['trades']} (Винрейт: {r['wr']:.1f}%, Побед: {r['wins']})")
    print(f"   • Максимальная просадка: -{abs(r['dd']):.2f}$")
    print(f"   • Плавающий uPnL в открытых: {r['upnl']:+.2f}$ ({r['open_count']} открытых)")
    
    # Top 3 coins
    pcoin = r.get("per_coin", {})
    sorted_coins = sorted(pcoin.items(), key=lambda x: x[1].get("net_profit_usdt", 0), reverse=True)
    top_str = ", ".join([f"{s}: {c.get('net_profit_usdt', 0):+.2f}$ ({c.get('trades', 0)} тр)" for s, c in sorted_coins[:4]])
    print(f"   • Топ-монеты: {top_str}")

print("\n" + "=" * 115)
