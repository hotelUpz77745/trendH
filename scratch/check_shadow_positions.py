import json

uids = ["u_shadow_harvester_50", "u_grid_shadow_50", "u_grid_pure_shadow"]
for uid in uids:
    try:
        with open(f"logs/data/state_{uid}.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            active = []
            for s, sides in data.items():
                for side, pos in sides.items():
                    if pos.get("is_active"):
                        active.append(f"{s} {side} @ {pos.get('open_price')} (size={pos.get('size')}, time={pos.get('open_time')})")
            print(f"=== {uid} ({len(active)} active) ===")
            for a in active:
                print("  ", a)
    except Exception as e:
        print(f"{uid}: error {e}")
