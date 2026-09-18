# ============================================================
# FILE: ANALYTICS/plotter.py
# ROLE: Equity curve generator, portfolio consolidation and per-coin visualizer
# ============================================================

import csv
import json
import glob
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    plt = None
    MATPLOTLIB_AVAILABLE = False

from consts import ANALYTICS_DIR

IMAGES_DIR = ANALYTICS_DIR / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

CSV_FILE = ANALYTICS_DIR / "trades_ledger.txt"
JSON_FILE = ANALYTICS_DIR / "analytics.json"
PLOT_FILE = IMAGES_DIR / "equity_curve.png"


def consolidate_portfolio_ledger() -> Path:
    """
    Агрегирует все закрытые сделки из всех trades_ledger_<uid>.txt в единый хронологический
    журнал портфеля trades_ledger_all.txt и trades_ledger.txt с расчетом совокупного баланса.
    """
    files = [
        f for f in glob.glob(str(ANALYTICS_DIR / "trades_ledger_*.txt"))
        if not f.endswith("all.txt") and not f.endswith("default.txt")
    ]
    all_trades: List[Dict[str, Any]] = []

    start_bal = 0.0
    all_json = ANALYTICS_DIR / "analytics_all.json"
    if not all_json.exists():
        all_json = ANALYTICS_DIR / "analytics.json"
    if all_json.exists():
        try:
            with open(all_json, "r", encoding="utf-8") as jf:
                start_bal = float(json.load(jf).get("start_balance_usdt", 0.0))
        except Exception:
            pass

    for f in files:
        uid = Path(f).stem.replace("trades_ledger_", "")
        if not uid or uid in ("all", "default"):
            continue
        try:
            with open(f, mode="r", encoding="utf-8") as fp:
                reader = csv.reader(fp, delimiter=';')
                header = next(reader, None)
                if not header:
                    continue

                pnl_idx = 4
                for i, h in enumerate(header):
                    if "pnl" in h.lower():
                        pnl_idx = i
                        break
                close_idx = 3
                for i, h in enumerate(header):
                    if "close" in h.lower():
                        close_idx = i
                        break
                open_idx = 2
                for i, h in enumerate(header):
                    if "open" in h.lower():
                        open_idx = i
                        break

                for row in reader:
                    if len(row) > max(close_idx, pnl_idx):
                        try:
                            dt = datetime.strptime(row[close_idx], "%Y-%m-%d %H:%M:%S")
                            pnl = float(row[pnl_idx])
                            all_trades.append({
                                "dt": dt,
                                "symbol": row[0],
                                "side": row[1] if len(row) > 1 else "N/A",
                                "open_time": row[open_idx] if len(row) > open_idx else "",
                                "close_time": row[close_idx],
                                "pnl": pnl,
                                "uid": uid
                            })
                        except Exception:
                            pass
        except Exception:
            pass

    # Сортируем все сделки строго хронологически по времени закрытия
    all_trades.sort(key=lambda x: x["dt"])

    out_all = ANALYTICS_DIR / "trades_ledger_all.txt"
    out_def = ANALYTICS_DIR / "trades_ledger.txt"

    cur_bal = start_bal
    rows: List[List[Any]] = []
    for t in all_trades:
        cur_bal = round(cur_bal + t["pnl"], 4)
        rows.append([t["symbol"], t["side"], t["open_time"], t["close_time"], t["pnl"], cur_bal, t["uid"]])

    header = ["Symbol", "Side", "Open Time", "Close Time", "PnL (USDT)", "Balance", "Strategy"]
    for p in (out_all, out_def):
        try:
            with open(p, mode="w", newline="", encoding="utf-8") as fp:
                w = csv.writer(fp, delimiter=';')
                w.writerow(header)
                for r in rows:
                    w.writerow(r)
        except Exception as e:
            print(f"[ANALYTICS] Error writing consolidated ledger {p}: {e}")

    return out_all


def generate_equity_curve(universe_id: str = "default") -> str:
    """
    Строит график эквити (Equity Curve) для указанной вселенной или совокупного портфеля [ALL].
    Возвращает абсолютный путь к сгенерированному PNG-файлу.
    """
    if not MATPLOTLIB_AVAILABLE or plt is None:
        return ""

    uid = (universe_id or "default").lower()
    suffix = f"_{uid}" if uid and uid != "default" else ""
    csv_file = ANALYTICS_DIR / f"trades_ledger{suffix}.txt"
    json_file = ANALYTICS_DIR / f"analytics{suffix}.json"
    plot_file = IMAGES_DIR / f"equity_curve{suffix}.png"

    # Для сводного портфеля всегда консолидируем актуальные данные из всех вселенных
    if uid in ("all", "default"):
        csv_file = consolidate_portfolio_ledger()
        if not json_file.exists():
            json_file = ANALYTICS_DIR / "analytics_all.json"
        if not json_file.exists():
            json_file = ANALYTICS_DIR / "analytics.json"
    elif not csv_file.exists():
        return ""

    start_balance = 0.0
    if json_file.exists():
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                start_balance = float(data.get("start_balance_usdt", 0.0))
        except Exception:
            pass

    times: List[Any] = []
    balances: List[float] = []
    current_balance = start_balance

    try:
        with open(csv_file, mode="r", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter=";")
            header = next(reader, None)
            if not header:
                return ""

            bal_idx = -1
            for i, h in enumerate(header):
                if "balance" in h.lower():
                    bal_idx = i
                    break
            has_balance_col = bal_idx != -1

            pnl_idx = 4
            for i, h in enumerate(header):
                if "pnl" in h.lower():
                    pnl_idx = i
                    break

            close_idx = 3
            for i, h in enumerate(header):
                if "close" in h.lower():
                    close_idx = i
                    break

            for row in reader:
                if len(row) <= close_idx:
                    continue

                t_str = row[close_idx]
                try:
                    dt = datetime.strptime(t_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue

                try:
                    if has_balance_col and len(row) > bal_idx and row[bal_idx].strip() != "":
                        current_balance = float(row[bal_idx])
                    else:
                        pnl = float(row[pnl_idx])
                        current_balance += pnl
                except ValueError:
                    continue

                times.append(dt)
                balances.append(current_balance)

    except Exception as e:
        print(f"Error reading CSV for plot: {e}")
        return ""

    if not times:
        return ""

    # Добавляем точку начального баланса за 1 час до первой сделки
    times.insert(0, times[0] - timedelta(hours=1))
    balances.insert(0, start_balance)

    # Статистика для графика
    final_balance = balances[-1]
    net_pnl = final_balance - start_balance
    pnl_pct = (net_pnl / start_balance * 100.0) if start_balance > 0 else 0.0
    total_trades = len(balances) - 1

    # Цветовая гамма: стильный dark mode
    accent_color = "#00E676" if net_pnl >= 0 else "#FF5252"
    fill_color = "#00E676" if net_pnl >= 0 else "#FF5252"

    fig, ax = plt.subplots(figsize=(10, 5.5), facecolor="#0F172A")
    ax.set_facecolor("#1E293B")

    # Линия баланса и заливка под графиком
    ax.plot(times, balances, color=accent_color, linewidth=2.2, label="Balance (USDT)", zorder=3)
    ax.fill_between(times, balances, min(balances), color=fill_color, alpha=0.15, zorder=2)

    # Горизонтальная линия начального баланса
    ax.axhline(y=start_balance, color="#94A3B8", linestyle=":", linewidth=1.2, alpha=0.6, label="Start Balance", zorder=2)

    # Настройка границ Y
    min_b = min(balances)
    max_b = max(balances)
    spread = max_b - min_b
    pad = 1.0 if spread < 5 else (5.0 if spread < 20 else 10.0)
    ax.set_ylim(min_b - pad, max_b + pad)

    title_text = f"Equity Curve [{uid.upper()}]" if uid != "default" else "Equity Curve [ALL]"
    subtitle_text = f"Start: ${start_balance:.2f} | Current: ${final_balance:.2f} | PnL: {net_pnl:+.2f}$ ({pnl_pct:+.2f}%) | Trades: {total_trades}"

    ax.set_title(f"{title_text}\n{subtitle_text}", fontsize=13, color="#F8FAFC", fontweight="bold", pad=12)
    ax.set_xlabel("Date", fontsize=11, color="#CBD5E1", labelpad=8)
    ax.set_ylabel("Balance (USDT)", fontsize=11, color="#CBD5E1", labelpad=8)

    ax.tick_params(axis="x", colors="#94A3B8", rotation=35)
    ax.tick_params(axis="y", colors="#94A3B8")

    # Стильная сетка
    ax.grid(True, linestyle="--", alpha=0.25, color="#64748B", zorder=1)

    # Границы графика
    for spine in ax.spines.values():
        spine.set_color("#334155")

    ax.legend(facecolor="#1E293B", edgecolor="#334155", labelcolor="#F8FAFC", loc="upper left")

    plt.tight_layout()

    # Сохраняем файл
    plt.savefig(plot_file, dpi=120, facecolor=fig.get_facecolor(), edgecolor="none")

    # Для сводного портфеля синхронизируем оба файла: equity_curve_all.png и equity_curve.png
    if uid in ("all", "default"):
        alt_file = IMAGES_DIR / "equity_curve.png" if uid == "all" else IMAGES_DIR / "equity_curve_all.png"
        try:
            plt.savefig(alt_file, dpi=120, facecolor=fig.get_facecolor(), edgecolor="none")
        except Exception:
            pass

    plt.close(fig)
    return str(plot_file)


def generate_coin_analytics(symbol: str) -> str:
    """Генерирует горизонтальную гистограмму метрик по конкретной монете."""
    if not MATPLOTLIB_AVAILABLE or plt is None:
        return ""
    if not JSON_FILE.exists():
        return ""

    try:
        with open(JSON_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return ""

    per_coin = data.get("per_coin", {})
    if symbol not in per_coin:
        return ""

    cdata = per_coin[symbol]

    # Извлечение метрик
    avg_daily = cdata.get("avg_daily_profit", 0.0)
    drme = cdata.get("DRME", 0.0)
    mdme = cdata.get("MDME", 0.0)
    max_dd = cdata.get("max_drawdown", 0.0)
    min_dd = cdata.get("min_drawdown", 0.0)
    cur_dd = cdata.get("current_drawdown", 0.0)

    net_profit = cdata.get("net_profit_usdt", 0.0)
    realized_pnl = cdata.get("realized_pnl_usdt", 0.0)
    realized_pnl_net = cdata.get("realized_pnl_net_usdt", realized_pnl)
    max_np = cdata.get("max_net_profit", net_profit)
    min_np = cdata.get("min_net_profit", net_profit)

    metrics = {
        "Max Hist. Drawdown": max_dd,
        "Unrealized PnL": cur_dd,
        "Min Hist. Drawdown": min_dd,
        "MDME": mdme,
        "DRME": drme,
        "Min Net Profit": min_np,
        "Avg Daily Profit (Net)": avg_daily,
        "Net Profit": net_profit,
        "Max Net Profit": max_np,
        "Realized PnL (Net)": realized_pnl_net,
        "Realized PnL (Gross)": realized_pnl
    }

    labels = list(metrics.keys())
    values = list(metrics.values())

    fig, ax = plt.subplots(figsize=(8.5, 7), facecolor="#0F172A")
    ax.set_facecolor("#1E293B")

    colors = []
    for val in values:
        if val > 0:
            colors.append("#10B981")  # Emerald Green
        elif val < 0:
            colors.append("#EF4444")  # Coral Red
        else:
            colors.append("#3B82F6")  # Blue

    bars = ax.barh(labels, values, color=colors, height=0.6, zorder=3)

    for bar in bars:
        width = bar.get_width()
        ax.text(
            0,
            bar.get_y() + bar.get_height() / 2,
            f"{width:.4f}",
            va="center",
            ha="center",
            fontweight="bold",
            color="#0F172A",
            fontsize=9,
            bbox=dict(facecolor="#F8FAFC", alpha=0.85, edgecolor="none", pad=2),
            zorder=4
        )

    ax.set_title(f"Advanced Analytics: {symbol}", fontsize=14, color="#F8FAFC", pad=15, fontweight="bold")
    ax.set_xlabel("Value (USDT)", fontsize=11, color="#CBD5E1", labelpad=8)

    ax.axvline(x=0, color="#94A3B8", linewidth=1, alpha=0.5, zorder=2)
    ax.grid(axis="x", linestyle="--", alpha=0.25, color="#64748B", zorder=1)

    ax.tick_params(axis="x", colors="#94A3B8")
    ax.tick_params(axis="y", colors="#CBD5E1")

    for spine in ax.spines.values():
        spine.set_color("#334155")

    plt.tight_layout()

    out_file = IMAGES_DIR / f"coin_analytics_{symbol.lower()}.png"
    plt.savefig(out_file, dpi=120, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)

    return str(out_file)


if __name__ == "__main__":
    generate_equity_curve("all")
