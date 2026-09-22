import json
import urllib.request
import os

# Load open positions
with open('logs/data/state_u_shadow_harvester_50.json', 'r', encoding='utf-8') as f:
    state = json.load(f)

# Fetch current prices from Binance Futures
url = "https://fapi.binance.com/fapi/v1/ticker/price"
try:
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=5) as resp:
        prices = {item['symbol']: float(item['price']) for item in json.loads(resp.read().decode('utf-8'))}
except Exception as e:
    print(f"Error fetching prices: {e}")
    prices = {}

# Load Cron runtime to see what Cron is holding
cron_runtime_dir = "C:/Users/user/Desktop/My_Pro/HP_EliteBook_735_old/MY/HRON_3/cron3Papper/CFG/runtime"

print(f"{'Symbol':<12} | {'Side':<5} | {'Open Price':<10} | {'Cur Price':<10} | {'Size ($)':<8} | {'Unrealized PnL':<15} | {'Cron Side & Size'}")
print("-" * 90)

total_unrealized = 0.0
for sym, sides in state.items():
    for side, pos in sides.items():
        if pos.get('is_active'):
            open_p = pos.get('open_price', 0.0)
            size = pos.get('size', 0.0)
            cur_p = prices.get(sym, open_p)
            if side == 'LONG':
                pnl = (cur_p - open_p) / open_p * size if open_p > 0 else 0.0
            else:
                pnl = (open_p - cur_p) / open_p * size if open_p > 0 else 0.0
            total_unrealized += pnl
            
            # Check cron state
            cron_file = f"{cron_runtime_dir}/{sym.lower()}.json"
            cron_info = "N/A"
            if os.path.exists(cron_file):
                with open(cron_file, 'r', encoding='utf-8') as cf:
                    cdata = json.load(cf)
                # Check which side is active or grid depth
                long_en = cdata.get('LONG', {}).get('enable', False)
                short_en = cdata.get('SHORT', {}).get('enable', False)
                cron_info = f"L_en:{long_en}, S_en:{short_en}"
                
            print(f"{sym:<12} | {side:<5} | {open_p:<10.5f} | {cur_p:<10.5f} | {size:<8.1f} | {pnl:>+14.2f}$ | {cron_info}")

print("-" * 90)
print(f"Total Current Unrealized: {total_unrealized:>+14.2f}$")
