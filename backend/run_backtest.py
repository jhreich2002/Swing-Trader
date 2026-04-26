"""
Phase 2 entry point — backtest + Bayesian seeding.

Usage (from project root):
    python -m backend.run_backtest

What it does:
  1. Fetches the S&P 500 universe from Wikipedia
  2. Pre-fetches SPY, VIX, and all 11 sector ETF price histories
  3. Replays 3 years of weekly signals for every ticker
  4. Saves all signal events to backtest_results
  5. Computes win rates per signal per regime
  6. Seeds bayesian_weights table

Runtime: expect 20-40 minutes on first run (500 tickers x 3 years).
All data is cached — subsequent runs complete in under 2 minutes.
"""
import logging
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("run_backtest")

from backend.config import BACKTEST_YEARS, SECTOR_ETF_MAP
from backend.scanner.universe import get_sp500_universe
from backend.scanner.data_client import get_daily_bars
from backend.learning.backtester import run_backtest
from backend.learning.bayesian import seed_weights, print_weight_table


def _prefetch_market_data() -> tuple:
    """Pre-fetches SPY, VIX, and all sector ETFs. Returns (df_spy, df_vix, sector_dfs)."""
    days = BACKTEST_YEARS * 365 + 90  # extra buffer

    logger.info("Pre-fetching SPY (%d days)...", days)
    df_spy = get_daily_bars("SPY", days=days)

    logger.info("Pre-fetching VIX (%d days)...", days)
    df_vix = get_daily_bars("^VIX", days=days)

    sector_dfs = {}
    for sector, etf in SECTOR_ETF_MAP.items():
        logger.info("Pre-fetching %s (%s)...", sector, etf)
        sector_dfs[sector] = get_daily_bars(etf, days=days)

    return df_spy, df_vix, sector_dfs


def _progress(current: int, total: int, ticker: str):
    pct  = current / total * 100
    bar  = "#" * int(pct / 2) + "-" * (50 - int(pct / 2))
    print(f"\r  [{bar}] {pct:5.1f}%  {current}/{total}  {ticker:<8}", end="", flush=True)


def run():
    print("\n" + "=" * 60)
    print("  PHASE 2 — BACKTEST + BAYESIAN SEEDING")
    print("=" * 60)

    # 1. Universe
    print("\nStep 1: Loading S&P 500 universe...")
    universe = get_sp500_universe()
    print(f"  {len(universe)} tickers loaded.")

    # 2. Market data pre-fetch
    print("\nStep 2: Pre-fetching market data...")
    df_spy, df_vix, sector_dfs = _prefetch_market_data()
    print(f"  SPY: {len(df_spy)} bars | VIX: {len(df_vix)} bars | "
          f"Sectors: {len(sector_dfs)} ETFs loaded.")

    # 3. Backtest replay
    print(f"\nStep 3: Replaying {BACKTEST_YEARS} years of signals across {len(universe)} tickers...")
    print("  (This takes 20-40 minutes on first run — data is cached afterwards)\n")
    t0 = time.time()

    total_events = run_backtest(
        universe       = universe,
        df_spy         = df_spy,
        df_vix         = df_vix,
        sector_etf_dfs = sector_dfs,
        progress_cb    = _progress,
    )
    print()  # newline after progress bar

    elapsed = time.time() - t0
    print(f"\n  Done. {total_events:,} signal events recorded in {elapsed/60:.1f} minutes.")

    if total_events == 0:
        print("\n  WARNING: No signal events recorded. Check data fetch and scorer logic.")
        return

    # 4. Seed Bayesian weights
    print("\nStep 4: Computing Bayesian weights from backtest results...")
    all_weights = seed_weights()

    # 5. Print weight table
    print_weight_table(all_weights)

    print("\nPhase 2 complete.")
    print("  bayesian_weights table seeded — AI debate chain can now use calibrated weights.")
    print("  Run 'python -m backend.run_scan' to see the live scanner with weighted signals.\n")


if __name__ == "__main__":
    run()
