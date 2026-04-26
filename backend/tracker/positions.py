"""
Position lifecycle management.

activate_position()  — converts a pending recommendation into an open position
close_position()     — manually close an open position
list_open()          — returns all open Position rows
list_pending_recs()  — returns pending recommendations (not yet entered)
"""
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from backend.database import Position, Recommendation, Signal, SessionLocal

logger = logging.getLogger(__name__)


def list_pending_recs(db: Session) -> list[Recommendation]:
    """All recommendations awaiting entry (status='pending')."""
    return (
        db.query(Recommendation)
        .filter(Recommendation.status == "pending")
        .order_by(Recommendation.created_at.desc())
        .all()
    )


def list_open(db: Session) -> list[Position]:
    """All currently open positions."""
    return db.query(Position).filter(Position.status == "open").all()


def activate_position(
    ticker: str,
    entry_price: float,
    shares: float,
    db: Session,
    portfolio_config: str = "A",
    recommendation_id: int | None = None,
) -> Position:
    """
    Creates an open Position for a ticker.

    If recommendation_id is given, links to that specific recommendation.
    Otherwise finds the most recent pending recommendation for the ticker
    (matched via the signals table).

    Raises ValueError if no pending recommendation exists and no ID given.
    """
    rec = None

    if recommendation_id is not None:
        rec = db.query(Recommendation).filter(Recommendation.id == recommendation_id).first()
        if rec is None:
            raise ValueError(f"No recommendation with id={recommendation_id}")
    else:
        # Find the most recent pending recommendation whose signal matches ticker
        rec = (
            db.query(Recommendation)
            .join(Signal, Recommendation.signal_id == Signal.id)
            .filter(
                Signal.ticker        == ticker,
                Recommendation.status == "pending",
            )
            .order_by(Recommendation.created_at.desc())
            .first()
        )
        if rec is None:
            raise ValueError(
                f"No pending recommendation found for {ticker}. "
                "Run the scanner first, or pass --rec-id to link manually."
            )

    # Initial stop comes from arbiter recommendation
    initial_stop = rec.stop_loss

    position = Position(
        recommendation_id = rec.id,
        ticker            = ticker,
        entry_price       = entry_price,
        entry_date        = datetime.utcnow(),
        stop_loss         = initial_stop,
        current_stop      = initial_stop,
        shares            = shares,
        portfolio_config  = portfolio_config,
        status            = "open",
        created_at        = datetime.utcnow(),
    )
    db.add(position)

    rec.status      = "active"
    rec.entry_price = entry_price

    db.commit()
    db.refresh(position)
    logger.info("Activated position: %s @ $%.2f  stop=$%.2f  shares=%.0f",
                ticker, entry_price, initial_stop or 0, shares)
    return position


def close_position(
    position_id: int,
    exit_price: float,
    reason: str,
    db: Session,
) -> Position:
    """
    Closes an open position and computes P&L.
    reason: 'stop_hit' | 'target_reached' | 'manual' | 'expired'
    """
    pos = db.query(Position).filter(Position.id == position_id).first()
    if pos is None:
        raise ValueError(f"No position with id={position_id}")
    if pos.status != "open":
        raise ValueError(f"Position {position_id} is already {pos.status}")

    pnl_pct = (exit_price - pos.entry_price) / pos.entry_price * 100

    pos.exit_price  = exit_price
    pos.exit_date   = datetime.utcnow()
    pos.exit_reason = reason
    pos.pnl         = round(pnl_pct, 4)
    pos.status      = "closed"

    # Mark the linked recommendation as closed
    if pos.recommendation_id:
        rec = db.query(Recommendation).filter(
            Recommendation.id == pos.recommendation_id
        ).first()
        if rec:
            rec.status = "closed"

    db.commit()
    db.refresh(pos)
    logger.info("Closed position: %s @ $%.2f  P&L=%.1f%%  reason=%s",
                pos.ticker, exit_price, pnl_pct, reason)
    return pos
