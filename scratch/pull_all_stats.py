import json
import glob
import os

files = glob.glob('logs/analytics/analytics_*.json')
results = []

for f in files:
    uid = os.path.basename(f).replace('analytics_', '').replace('.json', '')
    try:
        with open(f, 'r', encoding='utf-8') as fh:
            d = json.load(fh)
        net = d.get('net_profit_usdt', 0.0)
        real = d.get('realized_pnl_usdt', 0.0)
        bal = d.get('cur_balance_usdt', 0.0)
        dd = d.get('max_drawdown_usdt', 0.0)
        trades = d.get('total_trades', 0)
        wr = d.get('winrate_pct', 0.0)
        unreal = d.get('unrealized_pnl_usdt', 0.0)
        comm = real - net
        rec = round(net / dd, 2) if dd > 0 else 0.0
        results.append({
            'uid': uid, 'net': net, 'real': real, 'comm': comm,
            'bal': bal, 'dd': dd, 'trades': trades, 'wr': wr,
            'unreal': unreal, 'rec': rec
        })
    except Exception as e:
        pass

results.sort(key=lambda x: x['net'], reverse=True)
print(f"Total strategies analyzed: {len(results)}\n")
header = f"{'UID':30} | {'Net PnL':9} | {'WR (%)':7} | {'Trades':6} | {'DD':7} | {'Comm':7} | {'Unreal':7} | {'Rec':5}"
print(header)
print("-" * len(header))
for r in results:
    print(f"{r['uid']:30} | {r['net']:>+8.2f}$ | {r['wr']:6.1f}% | {r['trades']:6d} | {r['dd']:6.1f}$ | {r['comm']:6.1f}$ | {r['unreal']:>+6.1f}$ | {r['rec']:5.2f}")
