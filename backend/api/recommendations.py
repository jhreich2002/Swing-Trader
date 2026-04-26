"""
/api/recommendations/* routes — weekly trade recommendations.
"""
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query

from backend.database import SessionLocal, Recommendation, Signal, Debate
from backend.scanner.data_client import get_ticker_details

logger = logging.getLogger(__name__)
router = APIRouter()

POSITION_SIZE = 10_000  # assumed $ per trade for display


def _week_start(iso_date: str | None) -> datetime:
    """Returns Monday 00:00 UTC for the given ISO date string, or current week."""
    if iso_date:
        try:
            d = datetime.fromisoformat(iso_date)
        except ValueError:
            d = datetime.utcnow()
    else:
        d = datetime.utcnow()
    d = d - timedelta(days=d.weekday())
    return d.replace(hour=0, minute=0, second=0, microsecond=0)


def _build_rec_dict(rec: Recommendation, sig: Signal, debate: Debate | None,
                    current_price: float | None, name: str, sector: str) -> dict:
    signals_fired = []
    if sig:
        for fname in ("uptrend", "rsi", "rs", "volume", "position_52w", "vcp"):
            if getattr(sig, f"{fname}_score", 0) == 1:
                signals_fired.append(fname)

    stop_pct = None
    if rec.entry_price and rec.stop_loss and rec.entry_price > 0:
        stop_pct = round((rec.entry_price - rec.stop_loss) / rec.entry_price * 100, 2)

    shares = None
    if rec.entry_price and rec.entry_price > 0:
        shares = round(POSITION_SIZE / rec.entry_price, 2)

    tech_breakdown = {}
    fund_breakdown = {}
    earnings_warning = None

    if sig:
        for fname in ("uptrend", "rsi", "rs", "volume", "position_52w", "vcp"):
            tech_breakdown[fname] = {
                "score":  getattr(sig, f"{fname}_score", None),
                "raw":    getattr(sig, f"{fname}_raw", None),
                "detail": getattr(sig, f"{fname}_detail", None),
            }
        for fname in ("eps", "revenue", "pe"):
            fund_breakdown[fname] = {"score": getattr(sig, f"{fname}_score", None)}

        earnings_warning = {
            "warning": getattr(sig, "earnings_warning", False),
            "detail":  getattr(sig, "earnings_detail", None),
        }

    return {
        "id":                    rec.id,
        "ticker":                sig.ticker if sig else "",
        "name":                  name,
        "sector":                sector,
        "current_price":         current_price,
        "entry_price":           rec.entry_price,
        "stop_loss":             rec.stop_loss,
        "stop_distance_pct":     stop_pct,
        "position_value":        POSITION_SIZE,
        "shares":                shares,
        "holding_window_days":   rec.holding_window_days,
        "conviction_score":      rec.conviction_score,
        "regime":                sig.regime if sig else None,
        "composite_score":       sig.composite_score if sig else None,
        "arbiter_summary":       debate.arbiter_summary if debate else None,
        "entry_rationale":       None,
        "bull_argument":         debate.bull_argument if debate else None,
        "bear_argument":         debate.bear_argument if debate else None,
        "signals_fired":         signals_fired,
        "technical_breakdown":   tech_breakdown,
        "fundamental_breakdown": fund_breakdown,
        "earnings_warning":      earnings_warning,
        "portfolio_note":        rec.portfolio_note if rec else None,
        "status":                rec.status,
        "scan_date":             sig.scan_date.isoformat() if sig and sig.scan_date else None,
        "created_at":            rec.created_at.isoformat() if rec.created_at else None,
    }


@router.get("")
def list_recommendations(week: str = Query(default=None)):
    """
    Returns recommendations for a given week (defaults to current week).
    week param: ISO date string of any day in the target week.
    """
    week_start = _week_start(week)
    week_end   = week_start + timedelta(days=7)

    db = SessionLocal()
    try:
        rows = (
            db.query(Recommendation, Signal, Debate)
            .join(Signal, Recommendation.signal_id == Signal.id)
            .outerjoin(Debate, Debate.signal_id == Signal.id)
            .filter(
                Recommendation.created_at >= week_start,
                Recommendation.created_at <  week_end,
                Recommendation.status.in_(["pending", "active"]),
            )
            .order_by(Recommendation.conviction_score.desc())
            .all()
        )

        results = []
        portfolio_note = None

        for rec, sig, debate in rows:
            ticker  = sig.ticker if sig else ""
            details = get_ticker_details(ticker) if ticker else {}
            name    = details.get("name", ticker)
            sector  = details.get("sector", "Unknown")

            # Use yfinance fast_info for current price (no Finnhub dependency)
            current = None
            try:
                import yfinance as yf
                info    = yf.Ticker(ticker).fast_info
                current = getattr(info, "last_price", None)
            except Exception:
                pass

            rec_dict = _build_rec_dict(rec, sig, debate, current, name, sector)
            results.append(rec_dict)

            # Capture portfolio_note from any rec (they all share the same note)
            if rec.portfolio_note and portfolio_note is None:
                portfolio_note = rec.portfolio_note

        return {
            "week":            week_start.date().isoformat(),
            "portfolio_note":  portfolio_note,
            "recommendations": results,
        }
    finally:
        db.close()


@router.get("/{rec_id}")
def get_recommendation(rec_id: int):
    """Returns full detail for a single recommendation."""
    db = SessionLocal()
    try:
        row = (
            db.query(Recommendation, Signal, Debate)
            .join(Signal, Recommendation.signal_id == Signal.id)
            .outerjoin(Debate, Debate.signal_id == Signal.id)
            .filter(Recommendation.id == rec_id)
            .first()
        )
        if not row:
            raise HTTPException(status_code=404, detail=f"Recommendation {rec_id} not found")

        rec, sig, debate = row
        ticker  = sig.ticker if sig else ""
        details = get_ticker_details(ticker) if ticker else {}
        name    = details.get("name", ticker)
        sector  = details.get("sector", "Unknown")

        current = None
        try:
            import yfinance as yf
            info    = yf.Ticker(ticker).fast_info
            current = getattr(info, "last_price", None)
        except Exception:
            pass

        return _build_rec_dict(rec, sig, debate, current, name, sector)
    finally:
        db.close()
