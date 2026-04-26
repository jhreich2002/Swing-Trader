"""
Stop loss manager — checks open positions daily and trails stops upward.

Two-stage trailing logic:
  Stage 1 (break-even):   when price >= entry + 1R, move stop to entry
  Stage 2 (ATR trail):    stop = max(current_stop, price_high_watermark - 1.5 * ATR)
                          applied whenever price is above entry

Where R (initial risk) = entry_price - initial_stop_loss.

Run this daily after market close:
    python -m backend.run_tracker --check
"""
import logging
from datetime import datetime

import numpy as np
import pandas as pd

from sqlalchemy.orm import Session

from backend.config import ATR_PERIOD, ATR_STOP_MULTIPLIER
from backend.database import Position, StopUpdate, SessionLocal
from backend.scanner.data_client import get_daily_bars
from backend.tracker.positions import close_position

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ATR helpers
# ---------------------------------------------------------------------------

def _compute_atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> float | None:
    """Returns the most recent ATR value. None if insufficient data."""
    if df.empty or len(df) < period + 1:
        return None

    high  = df["High"]
    low   = df["Low"]
    close = df["Close"]

    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low  - close.shift(1)).abs(),
    ], axis=1).max(axis=1)

    atr = tr.rolling(period).mean().iloc[-1]
    return float(atr) if not np.isnan(atr) else None


# ---------------------------------------------------------------------------
# Stop check logic for a single position
# ---------------------------------------------------------------------------

def _check_position(pos: Position, db: Session) -> dict:
    """
    Evaluates one open position. Returns a status dict:
      {"ticker", "action", "old_stop", "new_stop", "current_price", "detail"}

    action: "stopped_out" | "stop_trailed" | "no_change"
    """
    df = get_daily_bars(pos.ticker, days=60)
    if df.empty:
        logger.warning("%s: no price data — skipping", pos.ticker)
        return {"ticker": pos.ticker, "action": "no_data"}

    current_price = float(df["Close"].iloc[-1])
    old_stop      = pos.current_stop or pos.stop_loss or 0.0
    entry         = pos.entry_price or current_price
    initial_stop  = pos.stop_loss or old_stop
    initial_risk  = entry - initial_stop  # R value; may be 0 if stop not set

    # --- Check: stop hit? ---
    if current_price <= old_stop and old_stop > 0:
        close_position(pos.id, current_price, "stop_hit", db)
        logger.info("%s stopped out at $%.2f (stop was $%.2f)", pos.ticker, current_price, old_stop)
        return {
            "ticker":        pos.ticker,
            "action":        "stopped_out",
            "current_price": current_price,
            "old_stop":      old_stop,
            "new_stop":      old_stop,
            "detail":        f"Stop hit at ${current_price:.2f}",
        }

    # --- Trail the stop ---
    atr = _compute_atr(df)
    new_stop = old_stop

    if atr:
        # ATR trail: stop = current_price - multiplier * ATR
        # Only move stop UP, never down
        atr_stop = current_price - ATR_STOP_MULTIPLIER * atr
        new_stop = max(old_stop, atr_stop)

    # Break-even override: if price >= entry + 1R and current stop is below entry,
    # snap stop to entry regardless of ATR (protect the trade)
    if initial_risk > 0 and current_price >= entry + initial_risk:
        new_stop = max(new_stop, entry)

    new_stop = round(new_stop, 4)

    if new_stop > old_stop + 0.0001:
        # Stop moved — log it
        stop_update = StopUpdate(
            position_id  = pos.id,
            old_stop     = old_stop,
            new_stop     = new_stop,
            trigger_type = "price_move",
            rationale    = (
                f"Price=${current_price:.2f}, "
                f"ATR={atr:.2f if atr is not None else 'N/A'}, "
                f"trail={ATR_STOP_MULTIPLIER}x ATR"
            ),
            created_at   = datetime.utcnow(),
        )
        db.add(stop_update)
        pos.current_stop = new_stop
        db.commit()

        logger.info("%s stop trailed: $%.2f → $%.2f  (price=$%.2f)",
                    pos.ticker, old_stop, new_stop, current_price)
        return {
            "ticker":        pos.ticker,
            "action":        "stop_trailed",
            "current_price": current_price,
            "old_stop":      old_stop,
            "new_stop":      new_stop,
            "detail":        (
                f"Trail: ${old_stop:.2f} -> ${new_stop:.2f} (ATR={atr:.2f})"
                if atr else
                f"Trail: ${old_stop:.2f} -> ${new_stop:.2f}"
            ),
        }

    return {
        "ticker":        pos.ticker,
        "action":        "no_change",
        "current_price": current_price,
        "old_stop":      old_stop,
        "new_stop":      old_stop,
        "detail":        f"Price=${current_price:.2f}, stop=${old_stop:.2f} unchanged",
    }


# ---------------------------------------------------------------------------
# Check all open positions
# ---------------------------------------------------------------------------

def check_all_stops(db: Session) -> list[dict]:
    """
    Iterates every open position, checks for stop hits, trails stops.
    Returns list of status dicts for printing.
    """
    positions = db.query(Position).filter(Position.status == "open").all()
    if not positions:
        return []

    results = []
    for pos in positions:
        result = _check_position(pos, db)
        results.append(result)

    return results


# ---------------------------------------------------------------------------
# Expiry check — close positions past their holding window
# ---------------------------------------------------------------------------

def check_expirations(db: Session) -> list[dict]:
    """
    Closes any position that has exceeded its holding window and prints a warning.
    The user decides whether to actually close — this just flags them.
    """
    from backend.database import Recommendation

    positions = db.query(Position).filter(Position.status == "open").all()
    expired = []

    for pos in positions:
        if pos.entry_date is None:
            continue

        days_held = (datetime.utcnow() - pos.entry_date).days

        rec = db.query(Recommendation).filter(
            Recommendation.id == pos.recommendation_id
        ).first() if pos.recommendation_id else None

        max_days = rec.holding_window_days if rec and rec.holding_window_days else 20

        if days_held >= max_days:
            expired.append({
                "ticker":    pos.ticker,
                "days_held": days_held,
                "max_days":  max_days,
                "position_id": pos.id,
            })

    return expired
