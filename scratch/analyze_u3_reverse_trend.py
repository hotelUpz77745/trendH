import re
import csv
import json
from pathlib import Path
from collections import defaultdict

# 1. Analyze trades_ledger_u3_reverse_trend.txt
ledger_p = Path("logs/analytics/trades_ledger_u3_reverse_trend.txt")
trades = []
if ledger_p.exists():
    with open(ledger_p, "r", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter=';')
        header = next(reader, None)
        for row in reader:
            if row and len(row) >= 5:
                sym, side, o_t, c_t, pnl_s = row[0], row[1], row[2], row[3], row[4]
                try:
                    pnl = float(pnl_s)
                    trades.append({
                        "sym": sym, "side": side, "open_time": o_t, "close_time": c_t, "pnl": pnl
                    })
                except ValueError:
                    pass

print(f"=== TRADES LEDGER ANALYSIS ({len(trades)} trades) ===")
total_pnl = sum(t["pnl"] for t in trades)
wins = [t for t in trades if t["pnl"] > 0]
losses = [t for t in trades if t["pnl"] <= 0]
winrate = (len(wins) / len(trades) * 100) if trades else 0.0
gross_profit = sum(t["pnl"] for t in wins)
gross_loss = abs(sum(t["pnl"] for t in losses))
profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 999.0
avg_win = (gross_profit / len(wins)) if wins else 0.0
avg_loss = (gross_loss / len(losses)) if losses else 0.0

print(f"Total Net PnL: {total_pnl:+.2f}$")
print(f"Winrate: {winrate:.1f}% ({len(wins)} W / {len(losses)} L)")
print(f"Profit Factor: {profit_factor:.2f}")
print(f"Avg Win: +{avg_win:.2f}$ | Avg Loss: -{avg_loss:.2f}$ | Ratio: {avg_win/avg_loss if avg_loss else 0:.2f}x")

# Side breakdown
long_trades = [t for t in trades if t["side"] == "LONG"]
short_trades = [t for t in trades if t["side"] == "SHORT"]
print(f"\n--- SIDE BREAKDOWN ---")
print(f"LONG : {len(long_trades):3} trades | PnL: {sum(t['pnl'] for t in long_trades):+7.2f}$ | WR: {sum(1 for t in long_trades if t['pnl']>0)/len(long_trades)*100 if long_trades else 0:.1f}%")
print(f"SHORT: {len(short_trades):3} trades | PnL: {sum(t['pnl'] for t in short_trades):+7.2f}$ | WR: {sum(1 for t in short_trades if t['pnl']>0)/len(short_trades)*100 if short_trades else 0:.1f}%")

# Coin breakdown
by_coin = defaultdict(list)
for t in trades:
    by_coin[t["sym"]].append(t)

coin_stats = []
for sym, ctrades in by_coin.items():
    cpnl = sum(t["pnl"] for t in ctrades)
    cwins = sum(1 for t in ctrades if t["pnl"] > 0)
    cwr = (cwins / len(ctrades) * 100) if ctrades else 0.0
    coin_stats.append((sym, len(ctrades), cpnl, cwr))

coin_stats.sort(key=lambda x: x[2], reverse=True)

print(f"\n--- TOP 10 PROFITABLE COINS ---")
for sym, cnt, cpnl, cwr in coin_stats[:10]:
    print(f"{sym:15} | {cnt:2} trades | PnL: {cpnl:+6.2f}$ | WR: {cwr:5.1f}%")

print(f"\n--- TOP 10 LOSING COINS ---")
for sym, cnt, cpnl, cwr in coin_stats[-10:]:
    print(f"{sym:15} | {cnt:2} trades | PnL: {cpnl:+6.2f}$ | WR: {cwr:5.1f}%")

# 2. Analyze Exit Reasons in all.log
log_p = Path("logs/all.log")
exit_reasons = defaultdict(int)
exit_pnl_by_reason = defaultdict(float)

if log_p.exists():
    pat = re.compile(r"\[SIGNAL EXIT\]\s*\[u3_reverse_trend\]\[(.*?)\]\[(.*?)\]\s*Выход\s*\[(.*?)\]!.*?PnL:\s*([+-]?[\d\.]+)%\s*\(([+-]?[\d\.]+)\$\)")
    with open(log_p, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if "[SIGNAL EXIT]" in line and "[u3_reverse_trend]" in line:
                m = pat.search(line)
                if m:
                    sym, side, reason, pnl_pct, pnl_usd = m.groups()
                    exit_reasons[reason] += 1
                    exit_pnl_by_reason[reason] += float(pnl_usd)

print(f"\n--- EXIT REASONS IN LOGS ---")
for r, cnt in sorted(exit_reasons.items(), key=lambda x: x[1], reverse=True):
    pnl = exit_pnl_by_reason[r]
    print(f"Reason: {r:20} | Count: {cnt:3} | Total PnL: {pnl:+7.2f}$")
