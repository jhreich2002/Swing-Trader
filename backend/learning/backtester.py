"""
Historical signal replay engine — Phase 2.

For every ticker in the universe, steps through 3 years of daily data
one week at a time. At each step it runs the 7 technical scorers on
the data available up to that date (no lookahead), then measures what
happened to the price over each signal's holding window.

Results are saved to the backtest_results table and used by the
Bayesian engine to seed signal weights.
"""
import logging
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import ta

from backend.config import (
    BACKTEST_YEARS,
    BACKTEST_STEP_DAYS,
    ATR_STOP_MULTIPLIER,
    ATR_PERIOD,
    WIN_REQUIRES_NO_STOP,
    SIGNAL_WINDOWS,
    SECTOR_ETF_MAP,
)
from backend.scanner.technical import (
    score_rsi,
    score_ma_crossover,
    score_macd,
    score_volume_surge,
    score_support_bounce,
    score_relative_strength,
    score_bollinger_breakout,
)
from backend.database import SessionLocal, BacktestResult

logger = logging.getLogger(__name__)

SCORERS = {
    "rsi":       score_rsi,
    "ma":        score_ma_crossover,
    "macd":      score_macd,
    "volume":    score_volume_surge,
    "support":   score_support_bounce,
    "bollinger": score_bollinger_breakout,
}


# ---------------------------------------------------------------------------
# ATR-based stop calculation
# ---------------------------------------------------------------------------

def _compute_atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> float | None:
    if df.empty or len(df) < period + 1:
        return None
    atr = ta.volatility.AverageTrueRange(
        df["High"], df["Low"], df["Close"], window=period
    ).average_true_range()
    val = atr.iloc[-1]
    return float(val) if not np.isnan(val) else None


def _compute_regime_simple(df_spy: pd.DataFrame, vix_val: float | None) -> str:
    """
    Lightweight regime detector for historical replay.
    Uses only SPY MAs + VIX (no breadth — too slow to compute historically).
    """
    if df_spy.empty or len(df_spy) < 55:
        return "choppy"

    close   = df_spy["Close"]
    sma20   = float(close.rolling(20).mean().iloc[-1])
    sma50   = float(close.rolling(50).mean().iloc[-1])
    current = float(close.iloc[-1])

    above_20 = current > sma20
    above_50 = current > sma50
    high_vix = vix_val is not None and vix_val >= 25

    if high_vix and not above_50:
        return "bearish"
    if above_20 and above_50 and not high_vix:
        return "trending"
    return "choppy"


# ---------------------------------------------------------------------------
# Outcome measurement
# ---------------------------------------------------------------------------

def _measure_outcome(
    df_full: pd.DataFrame,
    entry_idx: int,
    signal_name: str,
    atr: float,
) -> dict | None:
    """
    Given the full ticker DataFrame and the index of the entry bar,
    looks forward over the signal's holding window and records the outcome.

    Returns None if there isn't enough forward data.
    """
    window    = SIGNAL_WINDOWS[signal_name]
    max_days  = window["max"]
    min_days  = window["min"]

    entry_price = float(df_full["Close"].iloc[entry_idx])
    stop_price  = entry_price - (ATR_STOP_MULTIPLIER * atr)

    forward = df_full.iloc[entry_idx + 1: entry_idx + 1 + max_days]
    if len(forward) < min_days:
        return None  # Not enough forward data (end of history)

    # Walk forward day by day — check if stop is hit
    stop_hit      = False
    stop_hit_day  = None
    for i, (_, bar) in enumerate(forward.iterrows()):
        if float(bar["Low"]) <= stop_price:
            stop_hit     = True
            stop_hit_day = i + 1
            break

    # Measure exit price at the signal's max window (or stop hit day)
    if stop_hit:
        exit_idx   = min(stop_hit_day, len(forward) - 1)
        exit_price = stop_price  # Assume filled at stop
        hold_days  = stop_hit_day
    else:
        exit_price = float(forward["Close"].iloc[-1])
        hold_days  = len(forward)

    pnl_pct = (exit_price - entry_price) / entry_price * 100

    # Win definition: price up AND (if required) stop was not hit
    if WIN_REQUIRES_NO_STOP:
        win = (not stop_hit) and (exit_price > entry_price)
    else:
        win = exit_price > entry_price

    return {
        "entry_price": entry_price,
        "exit_price":  exit_price,
        "hold_days":   hold_days,
        "pnl_pct":     round(pnl_pct, 4),
        "stop_hit":    stop_hit,
        "win":         win,
    }


# ---------------------------------------------------------------------------
# Single ticker replay
# ---------------------------------------------------------------------------

def replay_ticker(
    ticker:    str,
    sector:    str,
    df_full:   pd.DataFrame,
    df_spy:    pd.DataFrame,
    df_vix:    pd.DataFrame,
    df_sector: pd.DataFrame,
) -> list[dict]:
    """
    Replays the full price history of one ticker week by week.
    Returns a list of result dicts ready to be saved to backtest_results.
    """
    results      = []
    total_bars   = len(df_full)
    # Need at least 60 bars of history before we start scanning
    min_history  = 60
    # Total lookback in trading days
    lookback     = BACKTEST_YEARS * 252

    # Start index: begin from the oldest date we want to replay
    start_idx = max(min_history, total_bars - lookback)

    idx = start_idx
    while idx < total_bars - SIGNAL_WINDOWS["volume"]["min"]:
        # Slice up to current date — no lookahead
        df_slice  = df_full.iloc[:idx + 1]

        # Corresponding SPY and sector slices (align by position approximation)
        spy_ratio = len(df_spy) / total_bars if total_bars > 0 else 1
        spy_end   = min(int(idx * spy_ratio) + 1, len(df_spy))
        df_spy_sl = df_spy.iloc[:spy_end]

        sec_ratio = len(df_sector) / total_bars if total_bars > 0 else 1
        sec_end   = min(int(idx * sec_ratio) + 1, len(df_sector))
        df_sec_sl = df_sector.iloc[:sec_end]

        # VIX at this date
        vix_ratio = len(df_vix) / total_bars if total_bars > 0 else 1
        vix_end   = min(int(idx * vix_ratio) + 1, len(df_vix))
        vix_val   = float(df_vix["Close"].iloc[vix_end - 1]) if vix_end > 0 and not df_vix.empty else None

        # Regime at this date
        regime = _compute_regime_simple(df_spy_sl, vix_val)

        # Current date for logging
        current_date = df_full.index[idx]

        # ATR for stop placement
        atr = _compute_atr(df_slice)
        if atr is None or atr == 0:
            idx += BACKTEST_STEP_DAYS
            continue

        # Run all scorers
        signal_results = {
            "rsi":       score_rsi(df_slice),
            "ma":        score_ma_crossover(df_slice),
            "macd":      score_macd(df_slice),
            "volume":    score_volume_surge(df_slice),
            "support":   score_support_bounce(df_slice),
            "rs":        score_relative_strength(df_slice, df_sec_sl),
            "bollinger": score_bollinger_breakout(df_slice),
        }

        # For each signal that fired, measure the outcome
        for signal_name, sig in signal_results.items():
            if sig["score"] != 1:
                continue

            outcome = _measure_outcome(df_full, idx, signal_name, atr)
            if outcome is None:
                continue

            results.append({
                "ticker":      ticker,
                "signal_date": current_date,
                "signal_type": signal_name,
                "regime":      regime,
                **outcome,
            })

        idx += BACKTEST_STEP_DAYS

    return results


# ---------------------------------------------------------------------------
# Batch runner
# ---------------------------------------------------------------------------

def run_backtest(
    universe:       list[tuple[str, str]],
    df_spy:         pd.DataFrame,
    df_vix:         pd.DataFrame,
    sector_etf_dfs: dict[str, pd.DataFrame],
    progress_cb=None,
) -> int:
    """
    Runs the backtester across the full universe.
    Saves results to the database in batches.
    Returns total number of signal events recorded.
    """
    db    = SessionLocal()
    total = 0

    try:
        for i, (ticker, sector) in enumerate(universe):
            if progress_cb:
                progress_cb(i + 1, len(universe), ticker)

            df_sector = sector_etf_dfs.get(sector, pd.DataFrame())

            # Import here to avoid circular dependency
            from backend.scanner.data_client import get_daily_bars
            df_full = get_daily_bars(ticker, days=BACKTEST_YEARS * 365 + 60)

            if df_full.empty or len(df_full) < 100:
                logger.warning("Skipping %s — insufficient history", ticker)
                continue

            try:
                results = replay_ticker(ticker, sector, df_full, df_spy, df_vix, df_sector)
            except Exception as e:
                logger.error("replay_ticker(%s) failed: %s", ticker, e)
                continue

            # Batch insert
            for r in results:
                db.add(BacktestResult(
                    ticker      = r["ticker"],
                    signal_date = r["signal_date"],
                    signal_type = r["signal_type"],
                    entry_price = r["entry_price"],
                    exit_price  = r["exit_price"],
                    hold_days   = r["hold_days"],
                    pnl_pct     = r["pnl_pct"],
                    regime      = r["regime"],
                ))
            db.commit()
            total += len(results)
            logger.info("%s: %d signal events recorded (total so far: %d)", ticker, len(results), total)

    finally:
        db.close()

    return total
