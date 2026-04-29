"""
/api/recommendations/* routes — weekly trade recommendations.
"""
import logging
import time
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query

from backend.database import SessionLocal, Recommendation, Signal, Debate
from backend.scanner.data_client import get_ticker_details, get_daily_bars, get_last_prices

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

    cache_key = f"list:{week_start.date().isoformat()}"
    cached = _list_cache_get(cache_key)
    if cached is not None:
        return cached

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

        # Batch the live price lookups (parallel + 1-min cached)
        tickers = [sig.ticker for _, sig, _ in rows if sig and sig.ticker]
        prices  = get_last_prices(tickers)

        results = []
        portfolio_note = None

        for rec, sig, debate in rows:
            ticker  = sig.ticker if sig else ""
            details = get_ticker_details(ticker) if ticker else {}
            name    = details.get("name", ticker)
            sector  = details.get("sector", "Unknown")
            current = prices.get(ticker)

            rec_dict = _build_rec_dict(rec, sig, debate, current, name, sector)
            results.append(rec_dict)

            # Capture portfolio_note from any rec (they all share the same note)
            if rec.portfolio_note and portfolio_note is None:
                portfolio_note = rec.portfolio_note

        result = {
            "week":            week_start.date().isoformat(),
            "portfolio_note":  portfolio_note,
            "recommendations": results,
        }
        _list_cache_set(cache_key, result)
        return result
    finally:
        db.close()


# --- short response cache for /api/recommendations?week=... ----------------
_LIST_CACHE_TTL_SEC = 30
_list_cache: dict = {}   # key -> (timestamp, payload)


def _list_cache_get(key: str):
    hit = _list_cache.get(key)
    if hit and time.time() - hit[0] < _LIST_CACHE_TTL_SEC:
        return hit[1]
    return None


def _list_cache_set(key: str, value):
    _list_cache[key] = (time.time(), value)


@router.get("/hypothetical")
def hypothetical_returns():
    """
    Simulates entering every recommendation at its `entry_price` and exiting at
    the first hit of `target_price`, `stop_loss`, or `holding_window_days`
    expiry; still-open trades are marked-to-market at today's close.

    Each trade contributes its own pct return; the cumulative curve is the
    running average of all trades exited or open up to each event date
    (equal-weighted simple average).

    Cached in-process for ~1 hour to limit yfinance traffic.
    """
    cached = _hypo_cache_get()
    if cached is not None:
        return cached

    db = SessionLocal()
    try:
        rows = (
            db.query(Recommendation, Signal)
            .join(Signal, Recommendation.signal_id == Signal.id)
            .filter(Recommendation.entry_price.isnot(None))
            .filter(Signal.scan_date.isnot(None))
            .order_by(Signal.scan_date)
            .all()
        )

        events = []          # one row per simulated trade
        wins = losses = open_count = 0

        # Group by ticker so we fetch each ticker's bars only once
        from collections import defaultdict
        by_ticker: dict[str, list] = defaultdict(list)
        for rec, sig in rows:
            by_ticker[sig.ticker].append((rec, sig))

        today = datetime.utcnow().date()

        for ticker, recs in by_ticker.items():
            # earliest entry to today gives us the lookback window
            earliest = min(s.scan_date.date() for _, s in recs)
            lookback_days = max((today - earliest).days + 5, 30)
            bars = get_daily_bars(ticker, days=lookback_days)
            if bars.empty:
                continue

            for rec, sig in recs:
                entry_dt   = sig.scan_date.date()
                entry      = rec.entry_price
                stop       = rec.stop_loss
                target     = rec.target_price
                window     = rec.holding_window_days or 10

                # Use bars strictly AFTER the entry date
                fwd = bars[bars.index.date > entry_dt]
                if fwd.empty or not entry:
                    continue

                exit_date = None
                exit_price = None
                exit_reason = None

                for i, (idx, row) in enumerate(fwd.iterrows(), start=1):
                    hi, lo, close = float(row["High"]), float(row["Low"]), float(row["Close"])
                    # Same-day target+stop -> treat as stop (conservative)
                    if stop and lo <= stop:
                        exit_date, exit_price, exit_reason = idx.date(), stop, "stop"
                        break
                    if target and hi >= target:
                        exit_date, exit_price, exit_reason = idx.date(), target, "target"
                        break
                    if i >= window:
                        exit_date, exit_price, exit_reason = idx.date(), close, "expired"
                        break

                if exit_date is None:
                    # Still open -> mark to market at most recent close
                    last_idx = fwd.index[-1]
                    exit_date   = last_idx.date()
                    exit_price  = float(fwd["Close"].iloc[-1])
                    exit_reason = "open"
                    open_count += 1

                ret_pct = (exit_price - entry) / entry * 100.0
                if exit_reason != "open":
                    if ret_pct > 0:
                        wins += 1
                    else:
                        losses += 1

                events.append({
                    "ticker":      ticker,
                    "entry_date":  entry_dt.isoformat(),
                    "exit_date":   exit_date.isoformat(),
                    "exit_reason": exit_reason,
                    "return_pct":  round(ret_pct, 3),
                })

        # Build curve: sort by exit date, plot running average of returns so far
        events.sort(key=lambda e: e["exit_date"])
        data = []
        if events:
            running_sum = 0.0
            data.append({
                "date":        events[0]["exit_date"],
                "return_pct":  0.0,
                "trade_count": 0,
            })
            for i, e in enumerate(events, start=1):
                running_sum += e["return_pct"]
                data.append({
                    "date":        e["exit_date"],
                    "return_pct":  round(running_sum / i, 3),
                    "trade_count": i,
                })

        result = {
            "data":              data,
            "total_return_pct":  data[-1]["return_pct"] if data else 0.0,
            "n_trades":          len(events),
            "n_winners":         wins,
            "n_losers":          losses,
            "n_open":            open_count,
            "events":            events,
        }
        _hypo_cache_set(result)
        return result
    finally:
        db.close()


# --- in-process cache for the hypothetical curve ---------------------------
_HYPO_CACHE_TTL_SEC = 3600
_hypo_cache: dict = {"value": None, "ts": 0.0}


def _hypo_cache_get():
    if _hypo_cache["value"] is None:
        return None
    if time.time() - _hypo_cache["ts"] > _HYPO_CACHE_TTL_SEC:
        return None
    return _hypo_cache["value"]


def _hypo_cache_set(value):
    _hypo_cache["value"] = value
    _hypo_cache["ts"] = time.time()


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

        from backend.scanner.data_client import get_last_price
        current = get_last_price(ticker) if ticker else None

        return _build_rec_dict(rec, sig, debate, current, name, sector)
    finally:
        db.close()
