"""
/api/portfolio/* routes — performance curve and trade history.
"""
import logging
import time
import json
from datetime import datetime, timedelta, date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.database import (
    SessionLocal, Position, Recommendation, Signal, BacktestResult,
    Holding, PortfolioSnapshot, AdvisorRecommendation,
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
# Holdings — multi-portfolio (active swing book, Roth IRA, passive).
# All routes are scoped by {ptype}. Legacy unscoped routes act as back-compat
# shims pointing at the "active" portfolio.
# ---------------------------------------------------------------------------

from typing import Literal, Optional

PortfolioType = Literal["active", "roth_ira", "passive"]
_VALID_PTYPES = {"active", "roth_ira", "passive"}


def _validate_ptype(ptype: str) -> str:
    if ptype not in _VALID_PTYPES:
        raise HTTPException(status_code=422, detail=f"invalid portfolio type: {ptype}")
    return ptype


class CashIn(BaseModel):
    amount: float


class StockIn(BaseModel):
    ticker: str
    shares: float
    cost_basis_per_share: float
    bucket: Optional[str] = None  # roth_ira only


class StockPatchIn(BaseModel):
    shares: Optional[float] = None
    cost_basis_per_share: Optional[float] = None
    bucket: Optional[str] = None


def _holdings_payload(db, ptype: str) -> dict:
    cash_row = (
        db.query(Holding)
          .filter(Holding.portfolio_type == ptype, Holding.kind == "cash")
          .first()
    )
    stock_rows = (
        db.query(Holding)
          .filter(Holding.portfolio_type == ptype, Holding.kind == "stock")
          .order_by(Holding.ticker)
          .all()
    )
    return {
        "portfolio_type": ptype,
        "cash":   float(cash_row.cash_amount) if cash_row and cash_row.cash_amount else 0.0,
        "stocks": [
            {
                "id":                   s.id,
                "ticker":               s.ticker,
                "shares":               s.shares,
                "cost_basis_per_share": s.cost_basis_per_share,
                "bucket":               s.bucket,
            }
            for s in stock_rows
        ],
    }


@router.get("/{ptype}/holdings")
def get_holdings(ptype: str):
    _validate_ptype(ptype)
    db = SessionLocal()
    try:
        return _holdings_payload(db, ptype)
    finally:
        db.close()


@router.put("/{ptype}/holdings/cash")
def set_cash(ptype: str, payload: CashIn):
    _validate_ptype(ptype)
    if payload.amount < 0:
        raise HTTPException(status_code=400, detail="cash amount must be >= 0")
    db = SessionLocal()
    try:
        row = (
            db.query(Holding)
              .filter(Holding.portfolio_type == ptype, Holding.kind == "cash")
              .first()
        )
        if row is None:
            row = Holding(portfolio_type=ptype, kind="cash", cash_amount=float(payload.amount))
            db.add(row)
        else:
            row.cash_amount = float(payload.amount)
            row.updated_at = datetime.utcnow()
        db.commit()
        _actual_cache_clear(ptype)
        return _holdings_payload(db, ptype)
    finally:
        db.close()


@router.post("/{ptype}/holdings")
def upsert_stock(ptype: str, payload: StockIn):
    _validate_ptype(ptype)
    if payload.shares <= 0 or payload.cost_basis_per_share < 0:
        raise HTTPException(status_code=400, detail="shares must be > 0 and cost basis >= 0")
    ticker = payload.ticker.strip().upper()
    if not ticker:
        raise HTTPException(status_code=400, detail="ticker required")
    bucket = payload.bucket
    if ptype == "roth_ira" and bucket is None:
        bucket = _classify_bucket(ticker)
    db = SessionLocal()
    try:
        row = (
            db.query(Holding)
              .filter(Holding.portfolio_type == ptype, Holding.kind == "stock", Holding.ticker == ticker)
              .first()
        )
        if row is None:
            row = Holding(
                portfolio_type=ptype,
                kind="stock",
                ticker=ticker,
                shares=float(payload.shares),
                cost_basis_per_share=float(payload.cost_basis_per_share),
                bucket=bucket if ptype == "roth_ira" else None,
            )
            db.add(row)
        else:
            row.shares = float(payload.shares)
            row.cost_basis_per_share = float(payload.cost_basis_per_share)
            if ptype == "roth_ira" and payload.bucket is not None:
                row.bucket = payload.bucket
            row.updated_at = datetime.utcnow()
        db.commit()
        _actual_cache_clear(ptype)
        return _holdings_payload(db, ptype)
    finally:
        db.close()


@router.patch("/{ptype}/holdings/{holding_id}")
def patch_stock(ptype: str, holding_id: int, payload: StockPatchIn):
    _validate_ptype(ptype)
    db = SessionLocal()
    try:
        row = (
            db.query(Holding)
              .filter(Holding.id == holding_id, Holding.portfolio_type == ptype)
              .first()
        )
        if row is None:
            raise HTTPException(status_code=404, detail="holding not found")
        if row.kind == "cash":
            raise HTTPException(status_code=400, detail="use PUT /holdings/cash for cash")
        if payload.shares is not None:
            if payload.shares <= 0:
                raise HTTPException(status_code=400, detail="shares must be > 0")
            row.shares = float(payload.shares)
        if payload.cost_basis_per_share is not None:
            if payload.cost_basis_per_share < 0:
                raise HTTPException(status_code=400, detail="cost basis must be >= 0")
            row.cost_basis_per_share = float(payload.cost_basis_per_share)
        if payload.bucket is not None and ptype == "roth_ira":
            row.bucket = payload.bucket
        row.updated_at = datetime.utcnow()
        db.commit()
        _actual_cache_clear(ptype)
        return _holdings_payload(db, ptype)
    finally:
        db.close()


@router.delete("/{ptype}/holdings/{holding_id}")
def delete_stock(ptype: str, holding_id: int):
    _validate_ptype(ptype)
    db = SessionLocal()
    try:
        row = (
            db.query(Holding)
              .filter(Holding.id == holding_id, Holding.portfolio_type == ptype)
              .first()
        )
        if row is None:
            raise HTTPException(status_code=404, detail="holding not found")
        if row.kind == "cash":
            raise HTTPException(status_code=400, detail="use PUT /holdings/cash to clear cash")
        db.delete(row)
        db.commit()
        _actual_cache_clear(ptype)
        return _holdings_payload(db, ptype)
    finally:
        db.close()


# Lightweight ETF auto-classifier used at create time and exposed for FE.
_INDEX_TICKERS    = {"SPY","VOO","IVV","VTI","QQQ","SCHB","SCHX","VEA","VXUS","IEFA","EFA","ITOT","SPLG"}
_GOLD_BOND_TICKERS = {"GLD","IAU","SGOL","TLT","IEF","AGG","BND","LQD","SHY","GOVT","BNDX","TIP"}


def _classify_bucket(ticker: str) -> str:
    t = (ticker or "").upper()
    if t in _INDEX_TICKERS:
        return "index"
    if t in _GOLD_BOND_TICKERS:
        return "gold_bonds"
    return "long_term_hold"


# ---------------------------------------------------------------------------
# Back-compat shims (legacy unscoped routes -> active portfolio)
# These prevent 404s on a live frontend deployed before the rename.
# ---------------------------------------------------------------------------
@router.get("/holdings")
def get_holdings_legacy():
    return get_holdings("active")


@router.put("/holdings/cash")
def set_cash_legacy(payload: CashIn):
    return set_cash("active", payload)


@router.post("/holdings")
def upsert_stock_legacy(payload: StockIn):
    return upsert_stock("active", payload)


@router.delete("/holdings/{holding_id}")
def delete_stock_legacy(holding_id: int):
    return delete_stock("active", holding_id)


def _last_price(ticker: str) -> float | None:
    prices = get_last_prices([ticker])
    return prices.get(ticker)


# --- short response cache for /api/portfolio/{ptype}/actual ----------------
_ACTUAL_CACHE_TTL_SEC = 30
_actual_cache: dict = {}   # ptype -> {"ts": float, "value": dict}


def _actual_cache_get(ptype: str):
    hit = _actual_cache.get(ptype)
    if hit and time.time() - hit["ts"] < _ACTUAL_CACHE_TTL_SEC:
        return hit["value"]
    return None


def _actual_cache_set(ptype: str, value):
    _actual_cache[ptype] = {"ts": time.time(), "value": value}


def _actual_cache_clear(ptype: str | None = None):
    if ptype is None:
        _actual_cache.clear()
    else:
        _actual_cache.pop(ptype, None)
    # Total aggregates depend on every ptype
    _total_cache_clear()


def _build_actual_payload(db, ptype: str) -> dict:
    """Pure helper: builds the /actual payload for a given portfolio_type.
    Side effect: upserts today's PortfolioSnapshot row for the portfolio.
    """
    cash_row = (
        db.query(Holding)
          .filter(Holding.portfolio_type == ptype, Holding.kind == "cash")
          .first()
    )
    cash = float(cash_row.cash_amount) if cash_row and cash_row.cash_amount else 0.0
    stock_rows = (
        db.query(Holding)
          .filter(Holding.portfolio_type == ptype, Holding.kind == "stock")
          .order_by(Holding.ticker)
          .all()
    )

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
            "bucket":               s.bucket,
        })

    total_market_value = round(stocks_market_value + cash, 2)
    total_cost_basis   = round(stocks_cost_basis + cash, 2)
    return_pct = round((total_market_value - total_cost_basis) / total_cost_basis * 100, 3) \
        if total_cost_basis > 0 else 0.0

    for p in positions:
        p["weight_pct"] = round(p["market_value"] / total_market_value * 100, 2) \
            if total_market_value > 0 else 0.0
    cash_weight = round(cash / total_market_value * 100, 2) if total_market_value > 0 else 0.0

    if total_cost_basis > 0:
        today = date.today()
        snap = (
            db.query(PortfolioSnapshot)
              .filter(PortfolioSnapshot.portfolio_type == ptype,
                      PortfolioSnapshot.snapshot_date == today)
              .first()
        )
        if snap is None:
            snap = PortfolioSnapshot(portfolio_type=ptype, snapshot_date=today)
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
        for row in db.query(PortfolioSnapshot)
                     .filter(PortfolioSnapshot.portfolio_type == ptype)
                     .order_by(PortfolioSnapshot.snapshot_date)
                     .all()
    ]

    return {
        "portfolio_type":     ptype,
        "cash":               round(cash, 2),
        "cash_weight_pct":    cash_weight,
        "positions":          positions,
        "total_market_value": total_market_value,
        "total_cost_basis":   total_cost_basis,
        "return_pct":         return_pct,
        "history":            history,
    }


@router.get("/{ptype}/actual")
def actual_portfolio(ptype: str):
    _validate_ptype(ptype)
    cached = _actual_cache_get(ptype)
    if cached is not None:
        return cached
    db = SessionLocal()
    try:
        result = _build_actual_payload(db, ptype)
        _actual_cache_set(ptype, result)
        return result
    finally:
        db.close()


@router.get("/actual")
def actual_portfolio_legacy():
    """Legacy: defaults to active portfolio."""
    return actual_portfolio("active")


# ---------------------------------------------------------------------------
# Total portfolio aggregation across all portfolio_types
# ---------------------------------------------------------------------------
_TOTAL_CACHE_TTL_SEC = 30
_total_cache: dict = {"ts": 0.0, "value": None}


def _total_cache_get():
    if _total_cache["value"] is not None and time.time() - _total_cache["ts"] < _TOTAL_CACHE_TTL_SEC:
        return _total_cache["value"]
    return None


def _total_cache_set(value):
    _total_cache["ts"] = time.time()
    _total_cache["value"] = value


def _total_cache_clear():
    _total_cache["value"] = None


@router.get("/total")
def total_portfolio():
    """Aggregates active + roth_ira + passive portfolios into one view."""
    cached = _total_cache_get()
    if cached is not None:
        return cached

    from backend.scanner.data_client import get_ticker_details

    db = SessionLocal()
    try:
        per_portfolio = {p: _build_actual_payload(db, p) for p in ("active", "roth_ira", "passive")}

        grand_mkt  = sum(p["total_market_value"] for p in per_portfolio.values())
        grand_cost = sum(p["total_cost_basis"]   for p in per_portfolio.values())
        grand_return_pct = round((grand_mkt - grand_cost) / grand_cost * 100, 3) if grand_cost > 0 else 0.0

        portfolios_summary = []
        for ptype, p in per_portfolio.items():
            portfolios_summary.append({
                "portfolio_type":             ptype,
                "total_market_value":         p["total_market_value"],
                "total_cost_basis":           p["total_cost_basis"],
                "return_pct":                 p["return_pct"],
                "cash":                       p["cash"],
                "weight_of_grand_total_pct":  round(p["total_market_value"] / grand_mkt * 100, 2) if grand_mkt > 0 else 0.0,
            })

        # Combined positions (one row per ticker, by_portfolio breakdown)
        by_ticker: dict = {}
        for ptype, p in per_portfolio.items():
            for pos in p["positions"]:
                t = pos["ticker"]
                entry = by_ticker.setdefault(t, {
                    "ticker":              t,
                    "total_shares":        0.0,
                    "total_market_value":  0.0,
                    "by_portfolio":        {"active": 0.0, "roth_ira": 0.0, "passive": 0.0},
                    "bucket":              pos.get("bucket"),
                })
                entry["total_shares"]       += pos["shares"] or 0.0
                entry["total_market_value"] += pos["market_value"] or 0.0
                entry["by_portfolio"][ptype] = round(pos["market_value"] or 0.0, 2)

        combined_positions = []
        for t, entry in by_ticker.items():
            entry["total_market_value"] = round(entry["total_market_value"], 2)
            entry["weight_pct"] = round(entry["total_market_value"] / grand_mkt * 100, 2) if grand_mkt > 0 else 0.0
            combined_positions.append(entry)
        combined_positions.sort(key=lambda x: -x["total_market_value"])

        # Sector exposure (ETF override: bucket-classified tickers get pseudo-sectors)
        sector_map: dict = {}
        for entry in combined_positions:
            t = entry["ticker"]
            bucket = _classify_bucket(t)
            if bucket == "index":
                sec = "Index ETF"
            elif bucket == "gold_bonds":
                sec = "Bonds & Gold"
            else:
                details = get_ticker_details(t) if t else {}
                sec = (details.get("sector") or "Unknown")
            sector_map[sec] = sector_map.get(sec, 0.0) + entry["total_market_value"]
        sector_exposure = [
            {
                "sector":     sec,
                "market_value": round(v, 2),
                "weight_pct": round(v / grand_mkt * 100, 2) if grand_mkt > 0 else 0.0,
            }
            for sec, v in sorted(sector_map.items(), key=lambda kv: -kv[1])
        ]

        # Asset-class exposure
        equity_v = bonds_gold_v = 0.0
        for entry in combined_positions:
            b = _classify_bucket(entry["ticker"])
            if b == "gold_bonds":
                bonds_gold_v += entry["total_market_value"]
            else:
                equity_v += entry["total_market_value"]
        cash_v = sum(p["cash"] for p in per_portfolio.values())
        asset_class_exposure = [
            {"class": "equity",     "market_value": round(equity_v, 2),     "weight_pct": round(equity_v / grand_mkt * 100, 2) if grand_mkt > 0 else 0.0},
            {"class": "bonds_gold", "market_value": round(bonds_gold_v, 2), "weight_pct": round(bonds_gold_v / grand_mkt * 100, 2) if grand_mkt > 0 else 0.0},
            {"class": "cash",       "market_value": round(cash_v, 2),       "weight_pct": round(cash_v / grand_mkt * 100, 2) if grand_mkt > 0 else 0.0},
        ]

        # Concentration
        top5_weight = round(sum(x["weight_pct"] for x in combined_positions[:5]), 2)
        max_pos_pct = combined_positions[0]["weight_pct"] if combined_positions else 0.0
        max_sec_pct = sector_exposure[0]["weight_pct"] if sector_exposure else 0.0

        # History — sum market value across portfolios per date
        rows = (
            db.query(PortfolioSnapshot)
              .order_by(PortfolioSnapshot.snapshot_date)
              .all()
        )
        per_date: dict = {}
        for r in rows:
            entry = per_date.setdefault(r.snapshot_date, {"market": 0.0, "cost": 0.0})
            entry["market"] += r.total_market_value or 0.0
            entry["cost"]   += r.total_cost_basis or 0.0
        history = [
            {
                "date":             d.isoformat(),
                "grand_return_pct": round((v["market"] - v["cost"]) / v["cost"] * 100, 3) if v["cost"] > 0 else 0.0,
                "total_value":      round(v["market"], 2),
            }
            for d, v in sorted(per_date.items())
        ]

        result = {
            "portfolios":              portfolios_summary,
            "grand_total_market_value": round(grand_mkt, 2),
            "grand_total_cost_basis":   round(grand_cost, 2),
            "grand_return_pct":         grand_return_pct,
            "combined_positions":       combined_positions,
            "sector_exposure":          sector_exposure,
            "asset_class_exposure":     asset_class_exposure,
            "concentration": {
                "top_5_weight_pct":      top5_weight,
                "max_single_position_pct": max_pos_pct,
                "max_single_sector_pct":   max_sec_pct,
            },
            "history": history,
        }
        _total_cache_set(result)
        return result
    finally:
        db.close()


# ---------------------------------------------------------------------------
# AI advisor endpoints (POST = generate, GET = cached)
# ---------------------------------------------------------------------------
@router.post("/{ptype_or_total}/recommendations")
def generate_recommendations(ptype_or_total: str):
    if ptype_or_total != "total":
        _validate_ptype(ptype_or_total)
    from backend.portfolio.advisor import generate_for_portfolio
    db = SessionLocal()
    try:
        if ptype_or_total == "total":
            payload = total_portfolio()
            ai = generate_for_portfolio("total", payload)
        else:
            payload = _build_actual_payload(db, ptype_or_total)
            ai = generate_for_portfolio(ptype_or_total, payload)

        rec = AdvisorRecommendation(
            portfolio_type=ptype_or_total,
            payload_json=json.dumps(ai),
        )
        db.add(rec)
        db.commit()
        return {**ai, "last_generated": rec.created_at.isoformat()}
    finally:
        db.close()


@router.get("/{ptype_or_total}/recommendations")
def get_recommendations(ptype_or_total: str):
    if ptype_or_total != "total":
        _validate_ptype(ptype_or_total)
    db = SessionLocal()
    try:
        rec = (
            db.query(AdvisorRecommendation)
              .filter(AdvisorRecommendation.portfolio_type == ptype_or_total)
              .order_by(AdvisorRecommendation.created_at.desc())
              .first()
        )
        if rec is None:
            return {"summary": None, "actions": [], "last_generated": None}
        try:
            data = json.loads(rec.payload_json or "{}")
        except Exception:
            data = {}
        return {**data, "last_generated": rec.created_at.isoformat()}
    finally:
        db.close()