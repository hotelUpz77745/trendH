import json

with open("cfg.json", "r", encoding="utf-8") as f:
    cfg = json.load(f)

universes = cfg.get("universes", {})

renames = {
    "u_sh50_outsiders": ("u_sh50_alpha", "Shadow Harvester 50% (Alpha)", "Вход против застрявшей сетки cron3 (уровень 2+, ratio >= 0.5) на монетах с сильным трендовым импульсом Alpha Momentum (Grid Net <= 0)"),
    "u_sh40_outsiders": ("u_sh40_alpha", "Shadow Harvester 40% (Alpha)", "Ранний вход при 40% объема сетки cron3 на монетах с импульсом Alpha Momentum (Grid Net <= 0)"),
    "u_hvh_symbiosis_outsiders": ("u_hvh_symbiosis_alpha", "HVH Delta Symbiosis (Alpha)", "Флагманский симбиоз (1H тренд + 15m HVH всплеск + стресс сетки) на монетах Alpha Momentum"),
    "u_symb_harv_outsiders": ("u_symb_harv_alpha", "Symbiosis Harvester (Alpha)", "Жнец стресса сетки 40% с защитой Profit Stagnation Exit на монетах Alpha Momentum (Grid Net <= 0)"),
    "u15_4h_rsi1d_outsiders": ("u15_4h_rsi1d_alpha", "Breakout LuxAlgo 4H + 1D RSI (Alpha)", "Институциональный пробой уровней LuxAlgo на 4H с дневным RSI фильтром на монетах Alpha Momentum")
}

for old_id, (new_id, new_name, new_desc) in renames.items():
    if old_id in universes:
        data = universes.pop(old_id)
        data["name"] = new_name
        data["description"] = new_desc
        # Update mode if present
        if "enter_rules" in data and "grid_net_filter" in data["enter_rules"]:
            data["enter_rules"]["grid_net_filter"]["mode"] = "ALPHA_ONLY"
        universes[new_id] = data
        print(f"Renamed {old_id} -> {new_id} ({new_name})")

with open("cfg.json", "w", encoding="utf-8") as f:
    json.dump(cfg, f, ensure_ascii=False, indent=4)

print("cfg.json successfully updated with Alpha naming!")
