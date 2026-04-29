"""
/api/portfolio/* routes — performance curve and trade history.
"""
import logging
import time
from datetime import datetime, timedelta, date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.database import (
    SessionLocal, Position, Recommendation, Signal, BacktestResult,
    Holding, PortfolioSnapshot,
)
from backend.scanner.data_client import get_last_prices

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


# ---------------------------------------------------------------------------
# Holdings — user's actual portfolio (single global, no auth)
# ---------------------------------------------------------------------------

class CashIn(BaseModel):
    amount: float


class StockIn(BaseModel):
    ticker: str
    shares: float
    cost_basis_per_share: float


def _holdings_payload(db) -> dict:
    cash_row = db.query(Holding).filter(Holding.kind == "cash").first()
    stock_rows = db.query(Holding).filter(Holding.kind == "stock").order_by(Holding.ticker).all()
    return {
        "cash":   float(cash_row.cash_amount) if cash_row and cash_row.cash_amount else 0.0,
        "stocks": [
            {
                "id":                   s.id,
                "ticker":               s.ticker,
                "shares":               s.shares,
                "cost_basis_per_share": s.cost_basis_per_share,
            }
            for s in stock_rows
        ],
    }


@router.get("/holdings")
def get_holdings():
    db = SessionLocal()
    try:
        return _holdings_payload(db)
    finally:
        db.close()


@router.put("/holdings/cash")
def set_cash(payload: CashIn):
    if payload.amount < 0:
        raise HTTPException(status_code=400, detail="cash amount must be >= 0")
    db = SessionLocal()
    try:
        row = db.query(Holding).filter(Holding.kind == "cash").first()
        if row is None:
            row = Holding(kind="cash", cash_amount=float(payload.amount))
            db.add(row)
        else:
            row.cash_amount = float(payload.amount)
            row.updated_at = datetime.utcnow()
        db.commit()
        _actual_cache_clear()
        return _holdings_payload(db)
    finally:
        db.close()


@router.post("/holdings")
def upsert_stock(payload: StockIn):
    if payload.shares <= 0 or payload.cost_basis_per_share < 0:
        raise HTTPException(status_code=400, detail="shares must be > 0 and cost basis >= 0")
    ticker = payload.ticker.strip().upper()
    if not ticker:
        raise HTTPException(status_code=400, detail="ticker required")
    db = SessionLocal()
    try:
        row = db.query(Holding).filter(Holding.kind == "stock", Holding.ticker == ticker).first()
        if row is None:
            row = Holding(
                kind="stock",
                ticker=ticker,
                shares=float(payload.shares),
                cost_basis_per_share=float(payload.cost_basis_per_share),
            )
            db.add(row)
        else:
            row.shares = float(payload.shares)
            row.cost_basis_per_share = float(payload.cost_basis_per_share)
            row.updated_at = datetime.utcnow()
        db.commit()
        _actual_cache_clear()
        return _holdings_payload(db)
    finally:
        db.close()


@router.delete("/holdings/{holding_id}")
def delete_stock(holding_id: int):
    db = SessionLocal()
    try:
        row = db.query(Holding).filter(Holding.id == holding_id).first()
        if row is None:
            raise HTTPException(status_code=404, detail="holding not found")
        if row.kind == "cash":
            raise HTTPException(status_code=400, detail="use PUT /holdings/cash to clear cash")
        db.delete(row)
        db.commit()
        _actual_cache_clear()
        return _holdings_payload(db)
    finally:
        db.close()


def _last_price(ticker: str) -> float | None:
    prices = get_last_prices([ticker])
    return prices.get(ticker)


# --- short response cache for /api/portfolio/actual ------------------------
_ACTUAL_CACHE_TTL_SEC = 30
_actual_cache: dict = {"ts": 0.0, "value": None}


def _actual_cache_get():
    if _actual_cache["value"] is not None and time.time() - _actual_cache["ts"] < _ACTUAL_CACHE_TTL_SEC:
        return _actual_cache["value"]
    return None


def _actual_cache_set(value):
    _actual_cache["ts"] = time.time()
    _actual_cache["value"] = value


def _actual_cache_clear():
    _actual_cache["value"] = None


@router.get("/actual")
def actual_portfolio():
    """
    Returns the current portfolio with per-position market values, weights,
    and a daily-snapshot history. Side effect: upserts today's snapshot row.
    """
    cached = _actual_cache_get()
    if cached is not None:
        return cached

    db = SessionLocal()
    try:
        cash_row = db.query(Holding).filter(Holding.kind == "cash").first()
        cash = float(cash_row.cash_amount) if cash_row and cash_row.cash_amount else 0.0
        stock_rows = db.query(Holding).filter(Holding.kind == "stock").order_by(Holding.ticker).all()

        # Batch all live price lookups in parallel
        prices = get_last_prices([s.ticker for s in stock_rows])

        positions = []
        stocks_market_value = 0.0
        stocks_cost_basis = 0.0
        for s in stock_rows:
            price = prices.get(s.ticker)
            mkt = (price or 0.0) * (s.shares or 0.0)
            cost = (s.cost_basis_per_share or 0.0) * (s.shares or 0.0)
            stocks_market_value += mkt
            stocks_cost_basis += cost
            positions.append({
                "id":                   s.id,
                "ticker":               s.ticker,
                "shares":               s.shares,
                "cost_basis_per_share": s.cost_basis_per_share,
                "current_price":        price,
                "market_value":         round(mkt, 2),
                "cost_basis":           round(cost, 2),
                "pnl":                  round(mkt - cost, 2),
                "pnl_pct":              round((mkt - cost) / cost * 100, 2) if cost > 0 else None,
            })

        total_market_value = round(stocks_market_value + cash, 2)
        total_cost_basis   = round(stocks_cost_basis + cash, 2)
        return_pct = round((total_market_value - total_cost_basis) / total_cost_basis * 100, 3) \
            if total_cost_basis > 0 else 0.0

        # Weights
        for p in positions:
            p["weight_pct"] = round(p["market_value"] / total_market_value * 100, 2) \
                if total_market_value > 0 else 0.0
        cash_weight = round(cash / total_market_value * 100, 2) if total_market_value > 0 else 0.0

        # Upsert today's snapshot (only if we actually have holdings)
        if total_cost_basis > 0:
            today = date.today()
            snap = db.query(PortfolioSnapshot).filter(PortfolioSnapshot.snapshot_date == today).first()
            if snap is None:
                snap = PortfolioSnapshot(snapshot_date=today)
                db.add(snap)
            snap.total_cost_basis   = total_cost_basis
            snap.total_market_value = total_market_value
            snap.return_pct         = return_pct
            db.commit()

        history = [
            {
                "date":         row.snapshot_date.isoformat(),
                "return_pct":   row.return_pct,
                "total_value":  row.total_market_value,
            }
            for row in db.query(PortfolioSnapshot).order_by(PortfolioSnapshot.snapshot_date).all()
        ]

        result = {
            "cash":               round(cash, 2),
            "cash_weight_pct":    cash_weight,
            "positions":          positions,
            "total_market_value": total_market_value,
            "total_cost_basis":   total_cost_basis,
            "return_pct":         return_pct,
            "history":            history,
        }
        _actual_cache_set(result)
        return result
    finally:
        db.close()