# ============================================================
# FILE: CORE/portfolio_selector.py
# ROLE: Multi-Mode Cross-Bot Portfolio Selector Service
# PROJECT: TrendH_Papper & Hron3 (cron3Papper) Symbiosis
# CLI EXAMPLES:
#   python CORE/portfolio_selector.py --mode FOR_GRID_ONLY --n 6
#   python CORE/portfolio_selector.py --mode FOR_GRIDE_FIRSTABLE --n 6
#   python CORE/portfolio_selector.py --mode FOR_TRENDH_ONLY --n 6
#   python CORE/portfolio_selector.py --mode FOR_TRENDH_FIRSTABLE --n 6
# ============================================================

import os
import json
import argparse
from dataclasses import dataclass, field
from typing import Dict, List, Any, Literal, Optional

# --- Operational Mode Annotation ---
# 1. FOR_GRID_ONLY: Pure standalone grid portfolio. Ignores TrendH metrics.
#    Strictly maximizes range-bound cash cows (high N/R, low R/R, low MDME, Net > 0).
# 2. FOR_GRIDE_FIRSTABLE: Grid-first symbiotic portfolio. Primary profit from Grid "Cash Cows"
#    while TrendH Harvester acts as sleeping hedge insurance (filters out chop traps).
# 3. FOR_TRENDH_ONLY: Standalone trend portfolio. Prioritizes highest volatility,
#    momentum, and proven TrendH win rates/returns across target trend strategies.
# 4. FOR_TRENDH_FIRSTABLE: TrendH-first symbiotic portfolio. TrendH Harvester is the
#    primary profit driver on runaway rockets (high DRME), while Combined PnL >= 0.
PortfolioMode = Literal[
    "FOR_GRID_ONLY",
    "FOR_GRIDE_FIRSTABLE",
    "FOR_TRENDH_ONLY",
    "FOR_TRENDH_FIRSTABLE",
]

# Default Paths to Grid Bot (cron3Papper) and TrendH Bot
DEFAULT_SYMBOLS_PATH = "C:/Users/user/Desktop/My_Pro/HP_EliteBook_735_old/MY/HRON_3/cron3Papper/CFG/app.json"
DEFAULT_RUNTIME_PATH = "C:/Users/user/Desktop/My_Pro/HP_EliteBook_735_old/MY/HRON_3/cron3Papper/CFG/runtime"
DEFAULT_CRON_ANALYTICS_PATH = "C:/Users/user/Desktop/My_Pro/HP_EliteBook_735_old/MY/HRON_3/cron3Papper/ANALYTICS/analytics.json"
DEFAULT_TRENDH_ANALYTICS_DIR = "logs/analytics"

# Configurable list of TrendH strategies to evaluate & aggregate
# User can customize this list to evaluate any set of top strategies
DEFAULT_TRENDH_TARGET_STRATEGIES: List[str] = [
    "u_shadow_harvester_50",
    "u_shadow_harvester_40",
    "u_delta_harvester",
    "u_delta_sniper_15m",
    "u_hvh_delta_symbiosis",
]


@dataclass
class CoinMetrics:
    """Consolidated metrics across Grid and TrendH bots for a single coin."""
    symbol: str
    # Grid Bot Metrics
    grid_net: float = 0.0
    grid_realized: float = 0.0
    grid_nr: float = 0.0
    grid_rr: float = 999.0
    grid_drme: float = 0.0
    grid_mdme: float = 999.0
    grid_trades: int = 0
    # TrendH Bot Metrics (Aggregated across target strategies)
    trendh_net: float = 0.0
    trendh_realized: float = 0.0
    trendh_trades: int = 0
    trendh_wins: int = 0
    trendh_winrate: float = 0.0
    trendh_by_strat: Dict[str, float] = field(default_factory=dict)
    # Combined Metrics & Selector Output
    combined_net: float = 0.0
    score: float = 0.0
    role: str = ""
    rationale: str = ""


@dataclass
class PortfolioResult:
    """Result of portfolio selection containing chosen coins and metadata."""
    mode: PortfolioMode
    coins: List[CoinMetrics] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)


class PortfolioSelector:
    """Service to evaluate cross-bot analytics and assemble optimal portfolios."""

    def __init__(
        self,
        symbols_path: str = DEFAULT_SYMBOLS_PATH,
        runtime_path: str = DEFAULT_RUNTIME_PATH,
        cron_analytics_path: str = DEFAULT_CRON_ANALYTICS_PATH,
        trendh_analytics_dir: str = DEFAULT_TRENDH_ANALYTICS_DIR,
        trendh_target_strategies: Optional[List[str]] = None,
    ):
        self.symbols_path = symbols_path
        self.runtime_path = runtime_path
        self.cron_analytics_path = cron_analytics_path
        self.trendh_analytics_dir = trendh_analytics_dir
        self.trendh_target_strategies = (
            trendh_target_strategies
            if trendh_target_strategies is not None
            else list(DEFAULT_TRENDH_TARGET_STRATEGIES)
        )

    def _safe_float(self, val: Any, default: float = 0.0) -> float:
        try:
            return float(val) if val is not None else default
        except (ValueError, TypeError):
            return default

    def load_data(self) -> Dict[str, CoinMetrics]:
        """Loads and merges analytics from both Grid and TrendH bots."""
        data_map: Dict[str, CoinMetrics] = {}

        # 1. Load Grid Bot (cron3Papper) Analytics
        if os.path.exists(self.cron_analytics_path):
            try:
                with open(self.cron_analytics_path, "r", encoding="utf-8") as f:
                    cron_json = json.load(f)
                per_coin = cron_json.get("per_coin", {})
                for sym, c in per_coin.items():
                    net = self._safe_float(c.get("net_profit_usdt"))
                    real = self._safe_float(c.get("realized_pnl_net_usdt"))
                    rr = self._safe_float(c.get("risk_reward_ratio"), 999.0)
                    drme = self._safe_float(c.get("DRME"), 0.0)
                    mdme = self._safe_float(c.get("MDME"), 999.0)
                    trades = int(c.get("trades", 0) or c.get("win_count", 0))
                    nr = (net / real) if real >= 1.0 else 0.0

                    data_map[sym] = CoinMetrics(
                        symbol=sym,
                        grid_net=net,
                        grid_realized=real,
                        grid_nr=nr,
                        grid_rr=rr,
                        grid_drme=drme,
                        grid_mdme=mdme,
                        grid_trades=trades,
                    )
            except Exception as e:
                print(f"[WARN] Error loading cron analytics: {e}")

        # 2. Load TrendH Analytics (Aggregated across target strategies)
        if os.path.exists(self.trendh_analytics_dir):
            try:
                for strat in self.trendh_target_strategies:
                    fname = f"analytics_{strat}.json"
                    fpath = os.path.join(self.trendh_analytics_dir, fname)
                    if not os.path.exists(fpath):
                        continue
                    with open(fpath, "r", encoding="utf-8") as f:
                        th_json = json.load(f)
                    th_coins = th_json.get("per_coin", {})
                    for sym, c in th_coins.items():
                        if sym not in data_map:
                            data_map[sym] = CoinMetrics(symbol=sym)
                        cm = data_map[sym]
                        c_net = self._safe_float(c.get("net_profit_usdt"))
                        c_real = self._safe_float(c.get("realized_pnl_net_usdt"))
                        c_trades = int(c.get("trades", 0))
                        c_wins = int(c.get("win_count", 0))

                        cm.trendh_net += c_net
                        cm.trendh_realized += c_real
                        cm.trendh_trades += c_trades
                        cm.trendh_wins += c_wins
                        cm.trendh_by_strat[strat] = round(c_net, 2)

                # Calculate weighted win rate and combined net
                for cm in data_map.values():
                    if cm.trendh_trades > 0:
                        cm.trendh_winrate = (cm.trendh_wins / cm.trendh_trades) * 100.0
                    cm.combined_net = cm.grid_net + cm.trendh_net
            except Exception as e:
                print(f"[WARN] Error loading TrendH analytics: {e}")

        return data_map

    def _score_for_grid_only(self, c: CoinMetrics) -> float:
        """Score for FOR_GRID_ONLY: Pure standalone grid without hedging.

        Prioritizes pure Net profit (50% weight), followed by N/R efficiency (20%),
        R/R ratio (15%), and MDME drawdown (15%). TrendH metrics are not considered.
        """
        if c.grid_realized < 5.0 or c.grid_net <= 0.0:
            return -999.0

        # 50% weight: Pure Net Profit (scaled up to 40.0 USDT)
        net_score = min(max(0.0, c.grid_net), 40.0) / 40.0 * 50.0
        # 20% weight: N/R efficiency (Net / Realized)
        nr_score = max(0.0, min(c.grid_nr, 1.0)) * 20.0
        # 15% weight: R/R ratio (lower risk/reward is better)
        rr_score = (1.0 / (max(0.2, c.grid_rr) + 0.8)) * 15.0
        # 15% weight: MDME (lower drawdown is better)
        mdme_score = (1.0 / (max(0.02, c.grid_mdme) * 20.0 + 1.0)) * 15.0
        return net_score + nr_score + rr_score + mdme_score

    def _score_for_gride_firstable(self, c: CoinMetrics) -> float:
        """Score for FOR_GRIDE_FIRSTABLE: Grid cash cows with sleeping hedge insurance."""
        if c.grid_realized < 5.0:
            return -999.0
        # Heavily penalize chop traps where TrendH Harvester lost > $10
        if c.trendh_net < -10.0:
            return -999.0

        nr_score = max(0.0, min(c.grid_nr, 1.0)) * 40.0
        rr_score = (1.0 / (max(0.1, c.grid_rr) + 0.2)) * 25.0
        mdme_score = (1.0 / (max(0.01, c.grid_mdme) + 0.05)) * 15.0
        net_score = min(max(0.0, c.grid_net), 30.0) / 30.0 * 20.0
        return nr_score + rr_score + mdme_score + net_score

    def _score_for_trendh_only(self, c: CoinMetrics) -> float:
        """Score for FOR_TRENDH_ONLY: Standalone trend strength, winrate, momentum."""
        th_pnl_score = max(-30.0, min(c.trendh_net, 150.0)) * 1.5
        wr_score = (c.trendh_winrate / 100.0) * 35.0 if c.trendh_trades >= 2 else 10.0
        vol_score = min(c.grid_drme, 0.2) / 0.2 * 25.0
        return th_pnl_score + wr_score + vol_score

    def _score_for_trendh_firstable(self, c: CoinMetrics) -> float:
        """Score for FOR_TRENDH_FIRSTABLE: High DRME trend rockets + POSITIVE Combined PnL.

        Key Criterion:
        1. Combined Net PnL (Grid Net + TrendH Net) MUST BE >= 0.
        2. TrendH Net must be non-destructive (trendh_net >= -3.0).
        """
        if c.combined_net < 0.0 or c.trendh_net < -3.0:
            return -999.0

        comb_score = min(max(0.0, c.combined_net), 100.0) * 1.2
        th_cash_engine = max(0.0, c.trendh_net) * 1.5
        drme_score = min(max(0.0, c.grid_drme), 0.25) / 0.25 * 30.0
        wr_bonus = (c.trendh_winrate / 100.0) * 15.0 if c.trendh_trades >= 2 else 5.0
        return comb_score + th_cash_engine + drme_score + wr_bonus

    def select_portfolio(
        self,
        n_coins: int = 6,
        mode: PortfolioMode = "FOR_GRIDE_FIRSTABLE",
    ) -> PortfolioResult:
        """Selects optimal n_coins according to the selected mode."""
        data_map = self.load_data()
        if not data_map:
            return PortfolioResult(mode=mode)

        # Calculate scores according to operational mode
        for c in data_map.values():
            if mode == "FOR_GRID_ONLY":
                c.score = self._score_for_grid_only(c)
                c.role = "PURE_CASH_COW" if c.grid_nr >= 0.75 and c.grid_rr < 1.0 else "STANDALONE_GRID"
                c.rationale = f"Grid Net: +{c.grid_net:.1f}$ (50%) | N/R: {c.grid_nr:.2f} | R/R: {c.grid_rr:.2f}"
            elif mode == "FOR_GRIDE_FIRSTABLE":
                c.score = self._score_for_gride_firstable(c)
                c.role = "CASH_COW" if c.grid_nr >= 0.75 and c.grid_rr < 1.0 else "GRID_STABLE"
                c.rationale = f"N/R: {c.grid_nr:.2f} | R/R: {c.grid_rr:.2f} | Grid Net: +{c.grid_net:.1f}$"
            elif mode == "FOR_TRENDH_ONLY":
                c.score = self._score_for_trendh_only(c)
                c.role = "TREND_RUNNER" if c.trendh_winrate >= 60 else "MOMENTUM_SURGE"
                c.rationale = f"TrendH Net: {c.trendh_net:+.1f}$ | WR: {c.trendh_winrate:.0f}% | DRME: {c.grid_drme:.3f}"
            elif mode == "FOR_TRENDH_FIRSTABLE":
                c.score = self._score_for_trendh_firstable(c)
                if c.trendh_net >= 10.0 and c.combined_net > 0:
                    c.role = "HARVESTER_ENGINE"
                elif c.trendh_net > 0 and c.combined_net > 0:
                    c.role = "SYMBIOTIC_RUNNER"
                else:
                    c.role = "CASH_STABILIZER"
                c.rationale = (
                    f"Comb Net: {c.combined_net:+.1f}$ | "
                    f"TrendH: {c.trendh_net:+.1f}$ | DRME: {c.grid_drme:.3f}"
                )

        valid_coins = [c for c in data_map.values() if c.score > -900.0]
        sorted_coins = sorted(valid_coins, key=lambda x: x.score, reverse=True)
        chosen = sorted_coins[:n_coins]

        total_grid_net = sum(c.grid_net for c in chosen)
        total_th_net = sum(c.trendh_net for c in chosen)
        total_comb_net = sum(c.combined_net for c in chosen)
        avg_drme = sum(c.grid_drme for c in chosen) / len(chosen) if chosen else 0.0

        summary = {
            "mode": mode,
            "total_coins_selected": len(chosen),
            "expected_grid_net_usdt": round(total_grid_net, 2),
            "expected_trendh_net_usdt": round(total_th_net, 2),
            "expected_combined_net_usdt": round(total_comb_net, 2),
            "avg_portfolio_drme": round(avg_drme, 4),
            "evaluated_strategies": self.trendh_target_strategies,
        }

        return PortfolioResult(mode=mode, coins=chosen, summary=summary)

    def format_report(self, res: PortfolioResult) -> str:
        """Formats the portfolio selection as a clear ASCII table."""
        strats_str = ", ".join(res.summary.get("evaluated_strategies", []))
        lines = [
            f"\n{'='*82}",
            f"[PORTFOLIO SELECTION RESULT] | MODE: {res.mode}",
            f"Evaluated Strategies: {strats_str}",
            f"{'='*82}",
            f"{'Symbol':<14} | {'Role':<18} | {'Score':<6} | {'Grid Net':<9} | {'TrendH Net':<11} | {'Comb Net':<9} | {'WR%':<4}",
            f"{'-'*82}",
        ]
        for c in res.coins:
            lines.append(
                f"{c.symbol:<14} | {c.role:<18} | {c.score:<6.1f} | "
                f"{c.grid_net:>+7.2f}$ | {c.trendh_net:>+9.2f}$ | "
                f"{c.combined_net:>+7.2f}$ | {c.trendh_winrate:>3.0f}%"
            )
        lines.append(f"{'-'*82}")
        lines.append(
            f"[SUMMARY] Grid Net: {res.summary.get('expected_grid_net_usdt', 0):+.2f}$ | "
            f"TrendH Net: {res.summary.get('expected_trendh_net_usdt', 0):+.2f}$ | "
            f"Comb Net: {res.summary.get('expected_combined_net_usdt', 0):+.2f}$ | "
            f"Avg DRME: {res.summary.get('avg_portfolio_drme', 0):.4f}"
        )
        lines.append(f"{'='*82}\n")
        return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-Mode Cross-Bot Portfolio Selector")
    parser.add_argument(
        "--mode",
        choices=[
            "FOR_GRID_ONLY",
            "FOR_GRIDE_FIRSTABLE",
            "FOR_TRENDH_ONLY",
            "FOR_TRENDH_FIRSTABLE",
        ],
        default="FOR_GRIDE_FIRSTABLE",
        help="Operational portfolio mode",
    )
    parser.add_argument("--n", type=int, default=6, help="Number of coins in portfolio")
    args = parser.parse_args()

    selector = PortfolioSelector()
    result = selector.select_portfolio(n_coins=args.n, mode=args.mode)
    print(selector.format_report(result))
