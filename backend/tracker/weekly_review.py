"""
Weekly P&L review.

Summarizes positions closed in the last N days, computes win rate,
and feeds results back into backtest_results so the Bayesian weight
engine improves from real-trade outcomes over time.
"""
import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from backend.database import Position, Signal, Recommendation, BacktestResult, SessionLocal

logger = logging.getLogger(__name__)


def run_weekly_review(db: Session, lookback_days: int = 7) -> dict:
    """
    Summarizes all positions closed in the last `lookback_days` days.

    Returns:
      {
        "closed":    list of position dicts,
        "wins":      int,
        "losses":    int,
        "win_rate":  float,
        "total_pnl": float,   # sum of pnl_pct
        "avg_pnl":   float,
      }
    """
    since = datetime.utcnow() - timedelta(days=lookback_days)
    closed = (
        db.query(Position)
        .filter(Position.status == "closed", Position.exit_date >= since)
        .order_by(Position.exit_date.desc())
        .all()
    )

    if not closed:
        return {
            "closed":    [],
            "wins":      0,
            "losses":    0,
            "win_rate":  0.0,
            "total_pnl": 0.0,
            "avg_pnl":   0.0,
        }

    rows = []
    wins   = 0
    losses = 0
    total_pnl = 0.0

    for pos in closed:
        pnl = pos.pnl or 0.0
        won = pnl > 0
        if won:
            wins += 1
        else:
            losses += 1
        total_pnl += pnl

        hold_days = None
        if pos.entry_date and pos.exit_date:
            hold_days = (pos.exit_date - pos.entry_date).days

        rows.append({
            "ticker":      pos.ticker,
            "entry_price": pos.entry_price,
            "exit_price":  pos.exit_price,
            "hold_days":   hold_days,
            "pnl_pct":     round(pnl, 2),
            "exit_reason": pos.exit_reason,
            "won":         won,
        })

    n = len(closed)
    return {
        "closed":    rows,
        "wins":      wins,
        "losses":    losses,
        "win_rate":  round(wins / n * 100, 1),
        "total_pnl": round(total_pnl, 2),
        "avg_pnl":   round(total_pnl / n, 2),
    }


def feed_results_to_backtest(db: Session, lookback_days: int = 7) -> int:
    """
    Inserts closed position outcomes into backtest_results so the Bayesian
    weight engine picks them up the next time seed_weights() is called.

    Maps each closed position back to its original signal row to recover
    which signals fired (so we know which signal "caused" this trade).

    Returns the number of rows inserted.
    """
    since = datetime.utcnow() - timedelta(days=lookback_days)
    closed = (
        db.query(Position)
        .filter(Position.status == "closed", Position.exit_date >= since)
        .all()
    )

    inserted = 0
    for pos in closed:
        if pos.pnl is None or pos.entry_price is None or pos.exit_price is None:
            continue

        # Recover the signal row to find which signals fired
        sig = None
        if pos.recommendation_id:
            rec = db.query(Recommendation).filter(
                Recommendation.id == pos.recommendation_id
            ).first()
            if rec and rec.signal_id:
                sig = db.query(Signal).filter(Signal.id == rec.signal_id).first()

        regime    = sig.regime if sig else "unknown"
        hold_days = None
        if pos.entry_date and pos.exit_date:
            hold_days = (pos.exit_date - pos.entry_date).days

        # Which signals fired on this trade?
        fired_signals = _get_fired_signals(sig) if sig else []

        if not fired_signals:
            # Still record it under a generic "live_trade" type so it's not lost
            fired_signals = ["live_trade"]

        for signal_type in fired_signals:
            row = BacktestResult(
                ticker      = pos.ticker,
                signal_date = pos.entry_date,
                signal_type = signal_type,
                entry_price = pos.entry_price,
                exit_price  = pos.exit_price,
                hold_days   = hold_days,
                pnl_pct     = pos.pnl,
                regime      = regime,
                created_at  = datetime.utcnow(),
            )
            db.add(row)
            inserted += 1

    db.commit()
    logger.info("Fed %d live trade results into backtest_results", inserted)
    return inserted


def _get_fired_signals(sig: Signal) -> list[str]:
    """Returns the list of signal names that scored 1 on this Signal row."""
    fired = []
    if sig.rsi_score    == 1: fired.append("rsi")
    if sig.ma_score     == 1: fired.append("ma")
    if sig.macd_score   == 1: fired.append("macd")
    if sig.volume_score == 1: fired.append("volume")
    if sig.support_score == 1: fired.append("support")
    if sig.rs_score     == 1: fired.append("rs")
    if sig.bb_score     == 1: fired.append("bollinger")
    return fired


def print_review(summary: dict):
    """Prints the weekly review to console."""
    rows = summary["closed"]
    if not rows:
        print("\n  No closed positions in the review period.\n")
        return

    header = (
        f"{'Ticker':<8} {'Entry':>8} {'Exit':>8} {'Days':>5} "
        f"{'P&L %':>8} {'Result':>8} {'Reason':<15}"
    )
    sep = "=" * len(header)

    print(f"\n{sep}")
    print("  WEEKLY POSITION REVIEW")
    print(sep)
    print(header)
    print("-" * len(header))

    for r in rows:
        result = "WIN" if r["won"] else "LOSS"
        print(
            f"{r['ticker']:<8} "
            f"${r['entry_price']:>7.2f} "
            f"${r['exit_price']:>7.2f} "
            f"{str(r['hold_days'] or '--'):>5} "
            f"{r['pnl_pct']:>+7.1f}% "
            f"{result:>8} "
            f"{(r['exit_reason'] or ''):.<15}"
        )

    print("-" * len(header))
    print(
        f"{'TOTAL':<8}  {'':>8}  {'':>8}  {'':>5}  "
        f"{summary['total_pnl']:>+7.1f}%  "
        f"Win rate: {summary['win_rate']:.1f}%  "
        f"({summary['wins']}W / {summary['losses']}L)"
    )
    print(sep + "\n")
