from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, DateTime, Date,
    Boolean, Text, ForeignKey
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from backend.config import DATABASE_URL

_is_sqlite = DATABASE_URL.startswith("sqlite")
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# stocks — universe of tracked equities
# ---------------------------------------------------------------------------
class Stock(Base):
    __tablename__ = "stocks"

    id         = Column(Integer, primary_key=True)
    ticker     = Column(String(10), unique=True, nullable=False, index=True)
    name       = Column(String(200))
    sector     = Column(String(100))
    market_cap = Column(Float)
    avg_volume = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# signals — full technical + fundamental profile per stock per scan
# ---------------------------------------------------------------------------
class Signal(Base):
    __tablename__ = "signals"

    id        = Column(Integer, primary_key=True)
    ticker    = Column(String(10), nullable=False, index=True)
    scan_date = Column(DateTime, default=datetime.utcnow)
    regime    = Column(String(20))    # trending / choppy / bearish

    # Technical scores (0 or 1) + raw values
    uptrend_score  = Column(Integer)
    uptrend_raw    = Column(Float)    # % above 50-SMA
    uptrend_detail = Column(String(300))

    rsi_score  = Column(Integer)
    rsi_raw    = Column(Float)        # current RSI value
    rsi_detail = Column(String(300))

    rs_score   = Column(Integer)
    rs_raw     = Column(Float)        # 3-month return differential vs sector
    rs_detail  = Column(String(300))

    volume_score  = Column(Integer)
    volume_raw    = Column(Float)     # 5-day/20-day volume ratio (<=0.80 = contracting)
    volume_detail = Column(String(300))

    position_52w_score  = Column(Integer)
    position_52w_raw    = Column(Float)    # % above 52-week low
    position_52w_detail = Column(String(300))

    vcp_score  = Column(Integer)
    vcp_raw    = Column(Float)        # contraction ratio (p3/p1, lower = more contracted)
    vcp_detail = Column(String(300))

    technical_total   = Column(Integer)  # 0–6

    # Earnings warning (not scored)
    earnings_warning = Column(Boolean, default=False)
    earnings_detail  = Column(String(300))

    # Fundamental scores (0 or 1)
    eps_score        = Column(Integer)
    revenue_score    = Column(Integer)
    pe_score         = Column(Integer)
    fundamental_total = Column(Integer)  # 0–3

    composite_score = Column(Float)     # 0–10

    created_at = Column(DateTime, default=datetime.utcnow)

    debate = relationship("Debate", back_populates="signal", uselist=False)


# ---------------------------------------------------------------------------
# debates — AI bull/bear/arbiter output per signal
# ---------------------------------------------------------------------------
class Debate(Base):
    __tablename__ = "debates"

    id               = Column(Integer, primary_key=True)
    signal_id        = Column(Integer, ForeignKey("signals.id"), nullable=False)
    bull_argument    = Column(Text)
    bear_argument    = Column(Text)
    arbiter_summary  = Column(Text)
    created_at       = Column(DateTime, default=datetime.utcnow)

    signal = relationship("Signal", back_populates="debate")


# ---------------------------------------------------------------------------
# recommendations — final output sent to user
# ---------------------------------------------------------------------------
class Recommendation(Base):
    __tablename__ = "recommendations"

    id                  = Column(Integer, primary_key=True)
    signal_id           = Column(Integer, ForeignKey("signals.id"), nullable=False)
    entry_price         = Column(Float)
    stop_loss           = Column(Float)
    target_price        = Column(Float)   # arbiter-set upside target (NULL on legacy rows)
    holding_window_days = Column(Integer)
    conviction_score    = Column(Float)
    status              = Column(String(20), default="pending")  # pending/active/closed/skipped
    portfolio_note      = Column(Text)     # concentration warning from portfolio agent
    created_at          = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# positions — paper trading positions
# ---------------------------------------------------------------------------
class Position(Base):
    __tablename__ = "positions"

    id                 = Column(Integer, primary_key=True)
    recommendation_id  = Column(Integer, ForeignKey("recommendations.id"), nullable=False)
    ticker             = Column(String(10), nullable=False, index=True)
    entry_price        = Column(Float)
    entry_date         = Column(DateTime)
    stop_loss          = Column(Float)
    current_stop       = Column(Float)
    shares             = Column(Float)
    portfolio_config   = Column(String(1))   # A / B / C
    status             = Column(String(10), default="open")  # open / closed
    exit_price         = Column(Float)
    exit_date          = Column(DateTime)
    exit_reason        = Column(String(100))
    pnl                = Column(Float)
    created_at         = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# stop_updates — log of every stop movement
# ---------------------------------------------------------------------------
class StopUpdate(Base):
    __tablename__ = "stop_updates"

    id           = Column(Integer, primary_key=True)
    position_id  = Column(Integer, ForeignKey("positions.id"), nullable=False)
    old_stop     = Column(Float)
    new_stop     = Column(Float)
    trigger_type = Column(String(20))
    rationale    = Column(Text)
    created_at   = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# bayesian_weights — current signal weights per market regime
# ---------------------------------------------------------------------------
class BayesianWeight(Base):
    __tablename__ = "bayesian_weights"

    id             = Column(Integer, primary_key=True)
    regime         = Column(String(20), nullable=False)

    # Technical signal weights
    uptrend_weight      = Column(Float, default=0.5)
    rsi_weight          = Column(Float, default=0.5)
    rs_weight           = Column(Float, default=0.5)
    volume_weight       = Column(Float, default=0.5)
    position_52w_weight = Column(Float, default=0.5)
    vcp_weight          = Column(Float, default=0.5)

    # Fundamental signal weights
    eps_weight     = Column(Float, default=0.5)
    revenue_weight = Column(Float, default=0.5)
    pe_weight      = Column(Float, default=0.5)

    updated_at = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# backtest_results — historical signal replay outcomes
# ---------------------------------------------------------------------------
class BacktestResult(Base):
    __tablename__ = "backtest_results"

    id          = Column(Integer, primary_key=True)
    ticker      = Column(String(10), nullable=False)
    signal_date = Column(DateTime)
    signal_type = Column(String(50))
    entry_price = Column(Float)
    exit_price  = Column(Float)
    hold_days   = Column(Integer)
    pnl_pct     = Column(Float)
    regime      = Column(String(20))
    created_at  = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# watchlist_items — user-curated ticker watchlist with AI digest
# ---------------------------------------------------------------------------
class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    id             = Column(Integer, primary_key=True)
    ticker         = Column(String(10), unique=True, nullable=False, index=True)
    name           = Column(String(200))
    sector         = Column(String(100))
    added_at       = Column(DateTime, default=datetime.utcnow)
    digest_status  = Column(String(20), default="pending")  # pending|running|complete|error
    digest_json    = Column(Text)   # full JSON blob from digester
    digested_at    = Column(DateTime)


# ---------------------------------------------------------------------------
# holdings — user's actual portfolio (one global, no auth).
# kind="cash" is a singleton row using cash_amount; kind="stock" rows use
# ticker + shares + cost_basis_per_share (one row per ticker).
# ---------------------------------------------------------------------------
class Holding(Base):
    __tablename__ = "holdings"

    id                   = Column(Integer, primary_key=True)
    kind                 = Column(String(10), nullable=False)  # "cash" | "stock"
    ticker               = Column(String(10), index=True)      # NULL for cash
    shares               = Column(Float)                       # NULL for cash
    cost_basis_per_share = Column(Float)                       # NULL for cash
    cash_amount          = Column(Float)                       # NULL for stock
    created_at           = Column(DateTime, default=datetime.utcnow)
    updated_at           = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---------------------------------------------------------------------------
# portfolio_snapshots — daily snapshot of total portfolio value & return.
# Upserted by GET /api/portfolio/actual (one row per calendar day).
# ---------------------------------------------------------------------------
class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id                 = Column(Integer, primary_key=True)
    snapshot_date      = Column(Date, unique=True, nullable=False, index=True)
    total_cost_basis   = Column(Float)
    total_market_value = Column(Float)
    return_pct         = Column(Float)
    created_at         = Column(DateTime, default=datetime.utcnow)
