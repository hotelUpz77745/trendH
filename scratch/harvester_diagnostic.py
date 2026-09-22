import json

for name in ['u_shadow_harvester_50', 'u_shadow_harvester_mid', 'u_shadow_harvester_wide']:
    path = f'logs/analytics/analytics_{name}.json'
    try:
        with open(path, 'r', encoding='utf-8') as f:
            d = json.load(f)
    except Exception as e:
        print(f"Error loading {name}: {e}")
        continue

    per_coin = d.get('per_coin', {})
    items = []
    for sym, stats in per_coin.items():
        net = stats.get('net_profit_usdt', 0.0)
        trades = stats.get('trades', 0)
        wr = stats.get('winrate_pct', 0.0)
        comm = stats.get('commission_usdt', 0.0)
        real = stats.get('realized_pnl_usdt', 0.0)
        items.append((sym, net, trades, wr, comm, real))
    
    items.sort(key=lambda x: x[1])
    total_comm = sum(x[4] for x in items)
    net_profit = d.get('net_profit_usdt', 0.0)
    total_trades = d.get('total_trades', 0)
    cur_bal = d.get('cur_balance_usdt', 0.0)
    dd = d.get('max_drawdown_usdt', 0.0)

    print(f"=== {name} ===")
    print(f"Net: {net_profit:+.2f}$ | Bal: {cur_bal:.2f}$ | DD: {dd:.2f}$ | Trades: {total_trades} | Comm: {total_comm:.2f}$")
    print("Worst 6 coins:")
    for sym, net, tr, wr, c, r in items[:6]:
        print(f"  {sym:15}: Net={net:+6.2f}$ | Trades={tr:2d} (WR={wr:4.1f}%) | Real={r:+6.2f}$ | Comm={c:6.2f}$")
    print("Best 6 coins:")
    for sym, net, tr, wr, c, r in items[-6:]:
        print(f"  {sym:15}: Net={net:+6.2f}$ | Trades={tr:2d} (WR={wr:4.1f}%) | Real={r:+6.2f}$ | Comm={c:6.2f}$")
    
    # Check positive vs negative coin counts
    pos_coins = [x for x in items if x[1] > 0]
    neg_coins = [x for x in items if x[1] < 0]
    pos_sum = sum(x[1] for x in pos_coins)
    neg_sum = sum(x[1] for x in neg_coins)
    print(f"Coin Summary: {len(pos_coins)} winners (+{pos_sum:.2f}$) vs {len(neg_coins)} losers ({neg_sum:.2f}$)")
    print()
