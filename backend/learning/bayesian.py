"""
Bayesian weight engine.

Reads backtest_results and computes per-signal win rates, broken down
by market regime. Writes the resulting weights to the bayesian_weights
table — one row per regime.

Weights are win rates (0.0–1.0). A signal with a 65% win rate gets
weight 0.65. These weights are used by the AI debate chain to calibrate
how much emphasis to place on each signal when evaluating candidates.

Separate weight sets are maintained per regime so bull-market signal
performance doesn't contaminate bear-market calibration.
"""
import logging
from datetime import datetime

from backend.database import SessionLocal, BayesianWeight, BacktestResult
from backend.config import SIGNAL_WINDOWS

logger = logging.getLogger(__name__)

REGIMES    = ["trending", "choppy", "bearish"]
SIGNALS    = ["uptrend", "rsi", "rs", "volume", "position_52w", "vcp"]
MIN_SAMPLE = 30   # Minimum signal events needed to trust a win rate

# Informed starting weights derived from Minervini SEPA research.
# Replace neutral 0.5 until real backtest data accumulates.
_SEED_WEIGHTS = {
    "trending": {"uptrend": 0.70, "rsi": 0.55, "rs": 0.65, "volume": 0.55, "position_52w": 0.70, "vcp": 0.65},
    "choppy":   {"uptrend": 0.50, "rsi": 0.55, "rs": 0.55, "volume": 0.55, "position_52w": 0.55, "vcp": 0.60},
    "bearish":  {"uptrend": 0.30, "rsi": 0.55, "rs": 0.50, "volume": 0.50, "position_52w": 0.40, "vcp": 0.55},
}

_SEED_FUND_WEIGHTS = {
    "trending": {"eps": 0.60, "revenue": 0.55, "pe": 0.50},
    "choppy":   {"eps": 0.55, "revenue": 0.55, "pe": 0.50},
    "bearish":  {"eps": 0.55, "revenue": 0.50, "pe": 0.55},
}


def seed_initial_weights(db) -> None:
    """
    Inserts informed starting weights into bayesian_weights for all three
    regimes. Only writes rows that don't already exist — will not overwrite
    weights that have been updated from real backtest data.
    """
    for regime in REGIMES:
        existing = db.query(BayesianWeight).filter(BayesianWeight.regime == regime).first()
        if existing:
            continue  # Don't overwrite real data

        tech  = _SEED_WEIGHTS.get(regime, {})
        fund  = _SEED_FUND_WEIGHTS.get(regime, {})

        db.add(BayesianWeight(
            regime              = regime,
            uptrend_weight      = tech.get("uptrend",      0.5),
            rsi_weight          = tech.get("rsi",          0.5),
            rs_weight           = tech.get("rs",           0.5),
            volume_weight       = tech.get("volume",       0.5),
            position_52w_weight = tech.get("position_52w", 0.5),
            vcp_weight          = tech.get("vcp",          0.5),
            eps_weight          = fund.get("eps",          0.5),
            revenue_weight      = fund.get("revenue",      0.5),
            pe_weight           = fund.get("pe",           0.5),
            updated_at          = datetime.utcnow(),
        ))

    db.commit()
    logger.info("Seeded initial Bayesian weights for all regimes.")


def compute_weights(regime: str, db) -> dict[str, float]:
    """
    Computes win rate for each signal within a specific regime.
    Returns dict of signal_name → weight (win rate).
    Falls back to seed weights if sample size is too small.
    """
    weights = {}
    seed_tech = _SEED_WEIGHTS.get(regime, {})

    for signal in SIGNALS:
        rows = (
            db.query(BacktestResult)
            .filter(
                BacktestResult.regime      == regime,
                BacktestResult.signal_type == signal,
            )
            .all()
        )

        if len(rows) < MIN_SAMPLE:
            fallback = seed_tech.get(signal, 0.5)
            logger.warning(
                "Signal '%s' in regime '%s': only %d samples (need %d) — using seed weight %.2f",
                signal, regime, len(rows), MIN_SAMPLE, fallback
            )
            weights[signal] = fallback
            continue

        wins     = sum(1 for r in rows if r.pnl_pct > 0)
        win_rate = wins / len(rows)
        weights[signal] = round(win_rate, 4)

        logger.info(
            "  [%s] %s: %d/%d wins = %.1f%%",
            regime, signal, wins, len(rows), win_rate * 100
        )

    return weights


def seed_weights(db=None) -> dict[str, dict[str, float]]:
    """
    Computes weights for all three regimes and upserts into bayesian_weights.
    Returns the full weight table as a nested dict: {regime: {signal: weight}}.
    """
    close_db = db is None
    if db is None:
        db = SessionLocal()

    all_weights = {}

    try:
        for regime in REGIMES:
            logger.info("Computing weights for regime: %s", regime)
            weights = compute_weights(regime, db)
            all_weights[regime] = weights

            fund_seed = _SEED_FUND_WEIGHTS.get(regime, {})
            existing  = db.query(BayesianWeight).filter(BayesianWeight.regime == regime).first()

            if existing:
                existing.uptrend_weight      = weights.get("uptrend",      0.5)
                existing.rsi_weight          = weights.get("rsi",          0.5)
                existing.rs_weight           = weights.get("rs",           0.5)
                existing.volume_weight       = weights.get("volume",       0.5)
                existing.position_52w_weight = weights.get("position_52w", 0.5)
                existing.vcp_weight          = weights.get("vcp",          0.5)
                existing.updated_at          = datetime.utcnow()
            else:
                db.add(BayesianWeight(
                    regime              = regime,
                    uptrend_weight      = weights.get("uptrend",      0.5),
                    rsi_weight          = weights.get("rsi",          0.5),
                    rs_weight           = weights.get("rs",           0.5),
                    volume_weight       = weights.get("volume",       0.5),
                    position_52w_weight = weights.get("position_52w", 0.5),
                    vcp_weight          = weights.get("vcp",          0.5),
                    eps_weight          = fund_seed.get("eps",        0.5),
                    revenue_weight      = fund_seed.get("revenue",    0.5),
                    pe_weight           = fund_seed.get("pe",         0.5),
                    updated_at          = datetime.utcnow(),
                ))

        db.commit()
        logger.info("Bayesian weights saved to database.")

    finally:
        if close_db:
            db.close()

    return all_weights


def get_weights(regime: str) -> dict[str, float]:
    """
    Retrieves the current Bayesian weights for a given regime.
    Falls back to seed weights (and seeds the DB) if none exist yet.
    """
    db = SessionLocal()
    try:
        row = db.query(BayesianWeight).filter(BayesianWeight.regime == regime).first()
        if row is None:
            logger.warning(
                "No Bayesian weights found for regime '%s' — seeding initial weights.", regime
            )
            seed_initial_weights(db)
            row = db.query(BayesianWeight).filter(BayesianWeight.regime == regime).first()

        if row is None:
            # Should not happen after seed, but guard anyway
            seed = {**_SEED_WEIGHTS.get(regime, {}), **_SEED_FUND_WEIGHTS.get(regime, {})}
            return {s: seed.get(s, 0.5) for s in SIGNALS + ["eps", "revenue", "pe"]}

        return {
            "uptrend":      row.uptrend_weight,
            "rsi":          row.rsi_weight,
            "rs":           row.rs_weight,
            "volume":       row.volume_weight,
            "position_52w": row.position_52w_weight,
            "vcp":          row.vcp_weight,
            "eps":          row.eps_weight,
            "revenue":      row.revenue_weight,
            "pe":           row.pe_weight,
        }
    finally:
        db.close()


def print_weight_table(all_weights: dict[str, dict[str, float]]):
    """Prints a formatted weight table to console."""
    all_signals = SIGNALS + ["eps", "revenue", "pe"]
    col_w  = 12
    header = f"{'Signal':<12}" + "".join(f"{r.upper():>{col_w}}" for r in REGIMES)
    print("\n" + "=" * len(header))
    print("BAYESIAN SIGNAL WEIGHTS (win rates by regime)")
    print("=" * len(header))
    print(header)
    print("-" * len(header))
    for signal in all_signals:
        row = f"{signal:<12}"
        for regime in REGIMES:
            w = all_weights.get(regime, {}).get(signal, 0.5)
            row += f"{w:>{col_w}.1%}"
        print(row)
    print("=" * len(header))
