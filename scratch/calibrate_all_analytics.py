import json
from pathlib import Path

an_dir = Path("logs/analytics")
calibrated = []

for p in sorted(an_dir.glob("analytics_*.json")):
    try:
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)
        uid = p.stem.replace("analytics_", "")
        changed = False

        start_bal = d.get("start_balance_usdt")
        if start_bal is None or start_bal <= 0:
            if uid != "all":
                d["start_balance_usdt"] = 200.0
                start_bal = 200.0
                changed = True

        peak = d.get("peak_balance_usdt")
        min_bal = d.get("min_balance_usdt")
        net = float(d.get("net_profit_usdt", 0.0))
        realized = float(d.get("realized_pnl_usdt", 0.0))
        unrealized = float(d.get("unrealized_pnl_usdt", 0.0))
        live_equity = (start_bal or 200.0) + (realized + unrealized)

        # Check for 1000$ ghost peak
        if uid != "all" and peak is not None and peak >= 800.0 and (start_bal or 200.0) <= 300.0:
            # The peak was recorded under 1000$ start balance
            old_profit = peak - 1000.0
            new_peak = round(start_bal + max(0.0, old_profit), 4)
            d["peak_balance_usdt"] = new_peak
            
            # Recalibrate min_balance if it was also from 1000$ base
            if min_bal is not None and min_bal >= 800.0:
                d["min_balance_usdt"] = round(start_bal - (1000.0 - min_bal), 4)
                min_bal = d["min_balance_usdt"]
            
            # Recalculate max_dd
            if min_bal is not None:
                new_max_dd = round(max(0.0, new_peak - min_bal), 4)
            else:
                new_max_dd = round(max(0.0, new_peak - live_equity), 4)
            d["max_drawdown_usdt"] = new_max_dd
            d["current_drawdown_usdt"] = round(max(0.0, new_peak - live_equity), 4)
            changed = True
            calibrated.append((uid, peak, new_peak, new_max_dd))

        if changed:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(d, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Error processing {p.name}: {e}")

print(f"Calibrated {len(calibrated)} files:")
for item in calibrated:
    print(f"  {item[0]:30}: old_peak={item[1]} -> new_peak={item[2]} | max_dd={item[3]}")
