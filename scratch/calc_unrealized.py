import json
import urllib.request

symbols = ['GUSDT', 'ZAMAUSDT', 'ENAUSDT', 'PIEVERSEUSDT', 'STXUSDT', 'FFUSDT', 'CFGUSDT', 'JUPUSDT', 'VVVUSDT', 'XPLUSDT', '1000PEPEUSDT', 'FARTCOINUSDT', 'PENGUUSDT', 'FORMUSDT']

url = 'https://fapi.binance.com/fapi/v1/ticker/price'
price_map = {}
try:
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read().decode())
    price_map = {item['symbol']: float(item['price']) for item in data}
except Exception as e:
    print(f"Binance fetch error: {e}")

# If binance direct fails or some coins missing, check logs/all.log or state
with open('logs/data/state_u_grid_pure_shadow.json', 'r', encoding='utf-8') as f:
    state = json.load(f)

results = []
total_unreal = 0.0

for sym in symbols:
    sides = state.get(sym, {})
    for side, pos in sides.items():
        if pos.get('is_active') and pos.get('open_price', 0) > 0:
            open_p = pos['open_price']
            size = pos['size']
            cur_p = price_map.get(sym, open_p)
            ratio = (cur_p - open_p if side == 'LONG' else open_p - cur_p) / open_p
            unreal = ratio * size
            pnl_pct = ratio * 100
            total_unreal += unreal
            results.append((sym, side, unreal, pnl_pct, open_p, cur_p, size))

results.sort(key=lambda x: x[2], reverse=True)
print(f"Total Calculated Unrealized PnL: {total_unreal:+.2f}$\n")
print(f"{'Coin':15} | {'Side':5} | {'Unrealized PnL':14} | {'PnL %':8} | {'Entry':10} | {'Current':10} | {'Size':7}")
print("-" * 80)
for sym, side, unreal, pnl_pct, open_p, cur_p, size in results:
    print(f"{sym:15} | {side:5} | {unreal:+10.2f}$    | {pnl_pct:+7.2f}% | {open_p:10.5g} | {cur_p:10.5g} | {size:6.1f}$")
