import glob
import json
import os

print("=== PIEVERSEUSDT ACROSS ALL STRATEGIES ===")
for fpath in glob.glob("logs/analytics/analytics_*.json"):
    uid = os.path.basename(fpath).replace("analytics_", "").replace(".json", "")
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
            pcoins = data.get("per_coin", {})
            if "PIEVERSEUSDT" in pcoins:
                c = pcoins["PIEVERSEUSDT"]
                net = c.get("net_profit_usdt", 0.0)
                trades = c.get("trades", 0)
                wr = c.get("winrate_pct", 0.0)
                print(f"{uid:25} | PnL: {net:+7.2f}$ | Trades: {trades:3} | WR: {wr:4.1f}%")
    except Exception as e:
        pass
