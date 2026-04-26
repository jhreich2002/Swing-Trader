"""
/api/portfolio/* routes — performance curve and trade history.
"""
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter

from backend.database import SessionLocal, Position, Recommendation, Signal, BacktestResult

logger = logging.getLogger(__name__)
router = APIRouter()

POSITION_SIZE  = 10_000   # $ per trade
PORTFOLIO_BASE = 100_000  # starting $ value


@router.get("/performance")
def get_performance():
    """
    Cumulative return curve of all completed trades, assuming $10k per trade
    on a $100k starting portfolio.

    Primary source: closed Position rows.
    Fallback: BacktestResult rows (if no real positions yet).
    """
    db = SessionLocal()
    try:
        positions = (
            db.query(Position)
            .filter(Position.status == "closed")
            .filter(Position.exit_date.isnot(None))
            .order_by(Position.exit_date)
            .all()
        )

        if positions:
            source = "positions"
            trades = [
                {
                    "date": pos.exit_date.date().isoformat(),
                    "pnl":  pos.pnl or 0.0,
                }
                for pos in positions
            ]
        else:
            # Fall back to backtest results — use signal_date + hold_days as exit date
            bt_rows = (
                db.query(BacktestResult)
                .filter(BacktestResult.signal_date.isnot(None))
                .order_by(BacktestResult.signal_date)
                .all()
            )
            source = "backtest"
            trades = []
            for r in bt_rows:
                exit_dt = r.signal_date + timedelta(days=r.hold_days or 10)
                trades.append({"date": exit_dt.date().isoformat(), "pnl": r.pnl_pct or 0.0})
            # Sort by derived exit date
            trades.sort(key=lambda x: x["date"])

        # Build cumulative return data points
        running_pnl  = 0.0
        wins, losses = 0, 0
        data         = [{"date": trades[0]["date"] if trades else datetime.utcnow().date().isoformat(),
                         "cumulative_return": 0.0, "trade_count": 0}]

        for i, t in enumerate(trades):
            dollar_pnl  = POSITION_SIZE * (t["pnl"] / 100)
            running_pnl += dollar_pnl
            cum_ret      = round(running_pnl / PORTFOLIO_BASE * 100, 2)
            if t["pnl"] > 0:
                wins += 1
            else:
                losses += 1
            data.append({
                "date":              t["date"],
                "cumulative_return": cum_ret,
                "trade_count":       i + 1,
            })

        total  = wins + losses
        return {
            "source":          source,
            "total_trades":    total,
            "wins":            wins,
            "losses":          losses,
            "win_rate":        round(wins / total * 100, 1) if total else 0.0,
            "total_return_pct": data[-1]["cumulative_return"] if data else 0.0,
            "data":            data,
        }
    finally:
        db.close()


@router.get("/trades")
def get_trades():
    """Full trade history — closed positions joined to signals for regime context."""
    db = SessionLocal()
    try:
        rows = (
            db.query(Position, Recommendation, Signal)
            .join(Recommendation, Position.recommendation_id == Recommendation.id, isouter=True)
            .join(Signal, Recommendation.signal_id == Signal.id, isouter=True)
            .order_by(Position.entry_date.desc())
            .all()
        )

        trades = []
        for pos, rec, sig in rows:
            hold_days = None
            if pos.entry_date and pos.exit_date:
                hold_days = (pos.exit_date - pos.entry_date).days

            trades.append({
                "id":              pos.id,
                "ticker":          pos.ticker,
                "entry_date":      pos.entry_date.date().isoformat() if pos.entry_date else None,
                "entry_price":     pos.entry_price,
                "exit_date":       pos.exit_date.date().isoformat() if pos.exit_date else None,
                "exit_price":      pos.exit_price,
                "hold_days":       hold_days,
                "pnl_pct":         pos.pnl,
                "regime":          sig.regime if sig else None,
                "conviction_score": rec.conviction_score if rec else None,
                "exit_reason":     pos.exit_reason,
                "outcome":         "win" if (pos.pnl or 0) > 0 else ("loss" if pos.exit_date else "open"),
                "status":          pos.status,
            })

        return {"trades": trades}
    finally:
        db.close()
