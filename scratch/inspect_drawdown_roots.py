import json
from pathlib import Path

uids = [
    'u_shadow_harvester_wide',
    'u_grid_shadow_stagnation',
    'u_grid_pure_shadow',
    'u_grid_shadow_50',
    'u_shadow_harvester_50',
    'u_grid_stress_base'
]

print(f"{'Universe':26} | {'Start':6} | {'Peak':8} | {'Min':8} | {'Net Real':9} | {'Unreal':8} | {'Max DD':8}")
print("-" * 90)

for uid in uids:
    p = Path(f'logs/analytics/analytics_{uid}.json')
    if not p.exists():
        continue
    with open(p, 'r', encoding='utf-8') as f:
        an = json.load(f)
    start = an.get('start_balance_usdt', 0)
    peak = an.get('peak_balance_usdt', 0)
    min_b = an.get('min_balance_usdt', 0)
    net_real = an.get('net_profit_usdt', 0)
    unreal = an.get('unrealized_pnl_usdt', 0)
    max_dd = an.get('max_drawdown_usdt', 0)
    print(f"{uid:26} | {start:6.1f} | {peak:8.2f} | {min_b:8.2f} | {net_real:+9.2f} | {unreal:+8.2f} | {max_dd:8.2f}")
