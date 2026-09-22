#!/usr/bin/env python3
# ============================================================
# FILE: scratch/reset_cron3_analytics_with_backup.py
# ROLE: Безопасный сброс аналитики cron3Papper + автобэкап
# ============================================================
"""
Сбрасывает реализованный PnL каждой монеты в analytics.json сеточника
(cron3Papper) до нулей — для получения чистой объективной картины
без накопленного исторического балласта.

Перед сбросом автоматически архивирует:
  * analytics.json  ->  ANALYTICS/backups/analytics_epoch{N}_{YYYYMMDD_HHMMSS}.json
  * trades_ledger.txt -> ANALYTICS/backups/trades_ledger_epoch{N}_{YYYYMMDD_HHMMSS}.txt

НИКОГДА не трогает CFG/runtime -- активный бот (PID 15256) работает непрерывно.
"""

import json
import shutil
import datetime
import pathlib
import sys

# --- Пути ----------------------------------------------------------------
CRON3_DIR   = pathlib.Path(r"C:/Users/user/Desktop/My_Pro/HP_EliteBook_735_old/MY/HRON_3/cron3Papper")
ANALYTICS_F = CRON3_DIR / "ANALYTICS" / "analytics.json"
LEDGER_F    = CRON3_DIR / "ANALYTICS" / "trades_ledger.txt"
BACKUP_DIR  = CRON3_DIR / "ANALYTICS" / "backups"

# --- Поля живых позиций, которые СОХРАНЯЕМ при сбросе --------------------
LIVE_FIELDS = ("long_unrealized", "short_unrealized", "long_amt", "short_amt", "max_position_size")

# --- Шаблон обнулённой записи монеты -------------------------------------
RESET_COIN_TEMPLATE = {
    "current_drawdown": 0.0,
    "realized_pnl_usdt": 0.0,
    "realized_pnl_net_usdt": 0.0,
    "commission_usdt": 0.0,
    "funding_usdt": 0.0,
    "net_profit_usdt": 0.0,
    "win_count": 0,
    "loss_count": 0,
    "max_drawdown": 0.0,
    "min_drawdown": 0.0,
    "MDME": 0.0,
    "epoch_state": {},
    "max_net_profit": 0.0,
    "min_net_profit": 0.0,
    "avg_daily_profit": 0.0,
    "risk_reward_ratio": 0.0,
    "max_position_size": 0.0,
    "DRME": 0.0,
    "trades": 0,
}


def _detect_epoch_number() -> int:
    """Определяет номер следующей эпохи по количеству уже существующих бэкапов."""
    if not BACKUP_DIR.exists():
        return 1
    return len(list(BACKUP_DIR.glob("analytics_epoch*.json"))) + 1


def _backup(epoch: int) -> None:
    """Создаёт timestamped-бэкап analytics.json и trades_ledger.txt."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    for src, name_tmpl in [
        (ANALYTICS_F, f"analytics_epoch{epoch}_{ts}.json"),
        (LEDGER_F,    f"trades_ledger_epoch{epoch}_{ts}.txt"),
    ]:
        if src.exists() and src.stat().st_size > 10:
            dst = BACKUP_DIR / name_tmpl
            shutil.copy2(src, dst)
            print(f"  Бэкап: {dst.name}  ({src.stat().st_size // 1024} KB)")


def _reset_analytics(data: dict) -> dict:
    """
    Обнуляет PnL-счётчики каждой монеты, сохраняя живые позиции
    (long_unrealized, short_unrealized, long_amt, short_amt).
    """
    new_per_coin = {}
    for coin, coin_data in data.get("per_coin", {}).items():
        entry = dict(RESET_COIN_TEMPLATE)
        for field in LIVE_FIELDS:
            if field in coin_data:
                entry[field] = coin_data[field]
        new_per_coin[coin] = entry

    now_ms = int(datetime.datetime.now().timestamp() * 1000)
    return {
        "start_balance_usdt": 0.0,
        "first_trade_ts": now_ms,
        "cur_balance_usdt": 0.0,
        "total_trades": 0,
        "winning_trades": 0,
        "winrate_pct": 0.0,
        "realized_pnl_usdt": 0.0,
        "net_profit_usdt": 0.0,
        "unrealized_pnl_usdt": data.get("unrealized_pnl_usdt", 0.0),
        "per_coin": new_per_coin,
    }


def main():
    print("=" * 62)
    print("  cron3Papper -- Сброс аналитики с автобэкапом")
    print("=" * 62)

    if not ANALYTICS_F.exists():
        print(f"ОШИБКА: Файл не найден: {ANALYTICS_F}")
        sys.exit(1)

    with open(ANALYTICS_F, "r", encoding="utf-8") as f:
        old_data = json.load(f)

    coins_count  = len(old_data.get("per_coin", {}))
    total_trades = old_data.get("total_trades", 0)
    realized_pnl = old_data.get("realized_pnl_usdt", 0.0)
    print(f"\nТекущая аналитика:")
    print(f"  Монет: {coins_count} | Сделок: {total_trades} | Реализованный PnL: {realized_pnl:+.2f}$")

    epoch = _detect_epoch_number()
    print(f"\nСоздаём бэкап (Эпоха #{epoch})...")
    _backup(epoch)

    print(f"\nСбрасываем аналитику (live-позиции сохранены)...")
    new_data = _reset_analytics(old_data)
    with open(ANALYTICS_F, "w", encoding="utf-8") as f:
        json.dump(new_data, f, indent=4, ensure_ascii=False)

    print(f"\nГотово! Монет в новой эпохе: {len(new_data['per_coin'])}")
    print(f"Бэкапы: {BACKUP_DIR}")
    print("=" * 62)


if __name__ == "__main__":
    main()
