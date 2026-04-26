"""
Watchlist API endpoints.

GET    /api/watchlist               — list all watchlist items (summary cards)
POST   /api/watchlist/{ticker}      — add ticker + trigger async digest
DELETE /api/watchlist/{ticker}      — remove ticker from watchlist
GET    /api/watchlist/{ticker}      — get full digest JSON for a ticker
POST   /api/watchlist/{ticker}/refresh — re-run digest for an existing ticker
"""
import json
import logging
import threading

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database import get_db, WatchlistItem

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Background digest helper
# ---------------------------------------------------------------------------

def _run_digest_bg(ticker: str):
    """Spawns a fresh DB session and runs the digest in a background thread."""
    from backend.database import SessionLocal
    from backend.watchlist.digester import digest_and_save
    db = SessionLocal()
    try:
        digest_and_save(ticker, db)
    except Exception as e:
        logger.error("Background digest error for %s: %s", ticker, e)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("")
def list_watchlist(db: Session = Depends(get_db)):
    """Return all watchlist items as summary cards (no full digest JSON)."""
    items = db.query(WatchlistItem).order_by(WatchlistItem.added_at.desc()).all()
    return {
        "watchlist": [
            {
                "ticker":        item.ticker,
                "name":          item.name or item.ticker,
                "sector":        item.sector or "Unknown",
                "added_at":      item.added_at.isoformat() if item.added_at else None,
                "digest_status": item.digest_status,
                "digested_at":   item.digested_at.isoformat() if item.digested_at else None,
                # Surface a few quick facts from digest if available
                "current_price":     _quick(item, "current_price"),
                "analyst_consensus": _quick(item, "analyst_consensus"),
                "analyst_target":    _quick(item, "analyst_target"),
            }
            for item in items
        ]
    }


def _quick(item: WatchlistItem, key: str):
    """Pull a top-level key from digest_json without loading the whole dict."""
    if not item.digest_json:
        return None
    try:
        return json.loads(item.digest_json).get(key)
    except Exception:
        return None


@router.post("/{ticker}")
def add_to_watchlist(ticker: str, db: Session = Depends(get_db)):
    """Add a ticker to the watchlist and kick off a background digest."""
    ticker = ticker.upper().strip()

    existing = db.query(WatchlistItem).filter(WatchlistItem.ticker == ticker).first()
    if existing:
        # Already in watchlist — return current status
        return {
            "status": "already_exists",
            "digest_status": existing.digest_status,
            "message": f"{ticker} is already in your watchlist.",
        }

    item = WatchlistItem(ticker=ticker, digest_status="pending")
    db.add(item)
    db.commit()

    # Kick off digest in background thread
    t = threading.Thread(target=_run_digest_bg, args=(ticker,), daemon=True)
    t.start()

    return {
        "status":  "added",
        "ticker":  ticker,
        "message": f"{ticker} added. Digest running in background (~60s).",
    }


@router.delete("/{ticker}")
def remove_from_watchlist(ticker: str, db: Session = Depends(get_db)):
    """Remove a ticker from the watchlist."""
    ticker = ticker.upper().strip()
    item = db.query(WatchlistItem).filter(WatchlistItem.ticker == ticker).first()
    if not item:
        raise HTTPException(status_code=404, detail=f"{ticker} not in watchlist.")
    db.delete(item)
    db.commit()
    return {"status": "removed", "ticker": ticker}


@router.get("/{ticker}")
def get_digest(ticker: str, db: Session = Depends(get_db)):
    """Return the full digest JSON for a ticker."""
    ticker = ticker.upper().strip()
    item = db.query(WatchlistItem).filter(WatchlistItem.ticker == ticker).first()
    if not item:
        raise HTTPException(status_code=404, detail=f"{ticker} not in watchlist.")

    if item.digest_status == "pending" or item.digest_status == "running":
        return {
            "ticker":        ticker,
            "digest_status": item.digest_status,
            "message":       "Digest is still running. Check back shortly.",
        }

    if not item.digest_json:
        return {
            "ticker":        ticker,
            "digest_status": item.digest_status or "error",
            "message":       "No digest data available.",
        }

    try:
        digest = json.loads(item.digest_json)
        digest["digest_status"] = item.digest_status
        return digest
    except Exception:
        raise HTTPException(status_code=500, detail="Digest data is corrupted.")


@router.post("/{ticker}/refresh")
def refresh_digest(ticker: str, db: Session = Depends(get_db)):
    """Re-run the digest for an existing watchlist ticker."""
    ticker = ticker.upper().strip()
    item = db.query(WatchlistItem).filter(WatchlistItem.ticker == ticker).first()
    if not item:
        raise HTTPException(status_code=404, detail=f"{ticker} not in watchlist.")

    if item.digest_status == "running":
        return {"status": "already_running", "message": "Digest already in progress."}

    item.digest_status = "pending"
    db.commit()

    t = threading.Thread(target=_run_digest_bg, args=(ticker,), daemon=True)
    t.start()

    return {"status": "refreshing", "ticker": ticker, "message": "Re-digest started."}
