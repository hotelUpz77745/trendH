import json
import math

cron_path = 'C:/Users/user/Desktop/My_Pro/HP_EliteBook_735_old/MY/HRON_3/cron3Papper/ANALYTICS/analytics.json'
trend_path = 'logs/analytics/analytics_u_shadow_harvester_50.json'

c_data = json.load(open(cron_path, encoding='utf-8')).get('per_coin', {})
t_data = json.load(open(trend_path, encoding='utf-8')).get('per_coin', {})

pairs = []
for sym, t_s in t_data.items():
    if t_s.get('trades', 0) > 0 and sym in c_data:
        c_net = c_data[sym].get('net_profit_usdt', c_data[sym].get('realized_pnl_net_usdt', 0))
        t_net = t_s.get('net_profit_usdt', 0)
        pairs.append((sym, c_net, t_net))

n = len(pairs)
mean_c = sum(p[1] for p in pairs) / n
mean_t = sum(p[2] for p in pairs) / n

cov = sum((p[1] - mean_c) * (p[2] - mean_t) for p in pairs)
var_c = sum((p[1] - mean_c) ** 2 for p in pairs)
var_t = sum((p[2] - mean_t) ** 2 for p in pairs)

r = cov / (math.sqrt(var_c) * math.sqrt(var_t)) if var_c > 0 and var_t > 0 else 0

print(f"Number of traded coins: {n}")
print(f"Pearson correlation (r): {r:.4f}")

# Inverse correlation strength
if r < -0.4:
    print("-> STRONG INVERSE CORRELATION CONFIRMED!")
elif r < -0.2:
    print("-> MODERATE INVERSE CORRELATION CONFIRMED!")
else:
    print(f"-> Correlation: {r:.2f}")

print("\nDetail pairs (Grid Net vs Trend Net):")
for sym, c_net, t_net in sorted(pairs, key=lambda x: x[1], reverse=True):
    print(f"  {sym:15} | Grid: {c_net:+7.2f}$ | Trend: {t_net:+7.2f}$")
