import json
import os

# 1. Load Shadow Harvester 50
with open('logs/analytics/analytics_u_shadow_harvester_50.json', 'r', encoding='utf-8') as f:
    sh50 = json.load(f)

# 2. Load Cron Analytics
with open('C:/Users/user/Desktop/My_Pro/HP_EliteBook_735_old/MY/HRON_3/cron3Papper/ANALYTICS/analytics.json', 'r', encoding='utf-8') as f:
    cron = json.load(f)

sh_coins = sh50.get('per_coin', {})
cron_coins = cron.get('per_coin', {})

print(f"=== U_SHADOW_HARVESTER_50 OVERVIEW ===")
print(f"Total Trades: {sh50.get('total_trades')} | WinRate: {sh50.get('winrate_pct'):.1f}% | Realized: {sh50.get('realized_pnl_usdt', 0):+.2f}$ | Net: {sh50.get('net_profit_usdt', 0):+.2f}$ | Unrealized: {sh50.get('unrealized_pnl_usdt', 0):+.2f}$")
print(f"Max DD: {sh50.get('max_drawdown_usdt', 0):.2f}$ | Peak: {sh50.get('peak_balance_usdt', 0):.2f}$ | Current DD: {sh50.get('current_drawdown_usdt', 0):.2f}$")
print()

table = []
for sym, sc in sh_coins.items():
    cc = cron_coins.get(sym, {})
    sh_net = float(sc.get('net_profit_usdt', 0.0))
    sh_real = float(sc.get('realized_pnl_net_usdt', 0.0))
    sh_wr = float(sc.get('winrate_pct', 0.0))
    sh_tr = int(sc.get('trades', 0))
    
    cr_net = float(cc.get('net_profit_usdt', 0.0))
    cr_real = float(cc.get('realized_pnl_net_usdt', 0.0))
    cr_dd = float(cc.get('current_drawdown', 0.0))
    cr_max_dd = float(cc.get('max_drawdown', 0.0))
    cr_drme = float(cc.get('DRME', 0.0))
    cr_rr = float(cc.get('risk_reward_ratio', 0.0))
    
    comb_net = cr_net + sh_net
    table.append((sym, sh_net, sh_wr, sh_tr, cr_net, cr_real, cr_dd, cr_drme, cr_rr, comb_net))

table.sort(key=lambda x: x[1], reverse=True)

print(f"{'Symbol':<14} | {'SH50 Net':<9} | {'SH50 WR':<8} | {'SH50 Tr':<7} | {'Cron Net':<9} | {'Cron Real':<9} | {'Cron CurDD':<10} | {'DRME':<6} | {'R/R':<5} | {'Comb Net':<9}")
print("-" * 105)
for sym, sh_net, sh_wr, sh_tr, cr_net, cr_real, cr_dd, cr_drme, cr_rr, comb_net in table:
    print(f"{sym:<14} | {sh_net:>+8.2f}$ | {sh_wr:>6.1f}% | {sh_tr:>7} | {cr_net:>+8.2f}$ | {cr_real:>+8.2f}$ | {cr_dd:>+9.2f}$ | {cr_drme:>6.3f} | {cr_rr:>5.2f} | {comb_net:>+8.2f}$")

# Also check open positions in SH50
print("\n=== OPEN POSITIONS IN LOGS/DATA OR ACTIVE POSITIONS ===")
pos_file = "logs/data/positions_u_shadow_harvester_50.json"
if os.path.exists(pos_file):
    with open(pos_file, "r", encoding="utf-8") as f:
        pos_data = json.load(f)
    print(f"Open positions count: {len(pos_data)}")
    for p in pos_data:
        print(p)
else:
    print(f"No positions file at {pos_file}, checking logs/data:")
    if os.path.exists("logs/data"):
        print(os.listdir("logs/data"))
