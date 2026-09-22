import json

for name in ['u_grid_shadow_be', 'u_grid_shadow_stagnation', 'u_grid_pure_shadow']:
    an_path = f'logs/analytics/analytics_{name}.json'
    try:
        with open(an_path, 'r', encoding='utf-8') as f:
            an = json.load(f)
        print(f"=== {name} ===")
        print(f"Net: {an.get('net_profit_usdt', 0):+.2f}$ | Unrealized: {an.get('unrealized_pnl_usdt', 0):+.2f}$ | Trades: {an.get('total_trades', 0)} | WR: {an.get('winrate_pct', 0):.1f}%")
        for sym, s in sorted(an.get('per_coin', {}).items(), key=lambda x: x[1].get('net_profit_usdt', 0)):
            tr = s.get('trades', 0)
            if tr > 0:
                print(f"  {sym:15}: net={s.get('net_profit_usdt', 0):+.2f}$ | trades={tr:2d} (WR={s.get('winrate_pct', 0):.1f}%) | real={s.get('realized_pnl_usdt', 0):+.2f}$ | comm={s.get('commission_usdt', 0):.2f}$")
        print()
    except Exception as e:
        print(f"Error {name}: {e}")
