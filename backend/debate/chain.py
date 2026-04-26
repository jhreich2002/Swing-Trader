"""
Debate chain orchestrator.

run_debate_chain() runs the full bull → bear → arbiter sequence for a single
candidate and persists the result to the debates and recommendations tables.

Designed to be called for the top N candidates after scoring, not for every
ticker in the universe.
"""
import logging
from datetime import datetime

from backend.database import Debate, Recommendation
from backend.debate.bull import make_bull_argument
from backend.debate.bear import make_bear_argument
from backend.debate.arbiter import arbitrate
from backend.scanner.data_client import get_daily_bars

logger = logging.getLogger(__name__)


def run_debate_chain(
    signal_id: int,
    ticker: str,
    tech_profile: dict,
    fund_profile: dict,
    composite_score: dict,
    regime: str,
    db,
) -> dict:
    """
    Runs the full three-agent debate for one candidate.

    Steps:
      1. Bull agent — strongest buy case
      2. Bear agent — strongest risk case
      3. Arbiter — weighs both, renders structured verdict
      4. Saves Debate row to DB
      5. If arbiter says include: saves Recommendation row to DB

    Returns the arbiter verdict dict (always, even on error).
    """
    logger.info("  [%s] Running bull argument...", ticker)
    try:
        bull_arg = make_bull_argument(ticker, tech_profile, fund_profile, composite_score, regime)
    except Exception as e:
        logger.error("  [%s] Bull agent failed: %s", ticker, e)
        bull_arg = f"[Bull analysis unavailable: {e}]"

    logger.info("  [%s] Running bear argument...", ticker)
    try:
        bear_arg = make_bear_argument(ticker, tech_profile, fund_profile, composite_score, regime)
    except Exception as e:
        logger.error("  [%s] Bear agent failed: %s", ticker, e)
        bear_arg = f"[Bear analysis unavailable: {e}]"

    logger.info("  [%s] Running arbiter...", ticker)
    try:
        verdict = arbitrate(
            ticker, bull_arg, bear_arg, tech_profile, fund_profile, composite_score
        )
    except Exception as e:
        logger.error("  [%s] Arbiter failed: %s", ticker, e)
        verdict = {
            "include":             False,
            "conviction_score":    0,
            "arbiter_summary":     f"Arbiter error: {e}",
            "entry_rationale":     "",
            "stop_loss_pct":       6.0,
            "holding_window_days": 10,
            "skip_reason":         f"API error: {e}",
        }

    # Persist debate row
    try:
        debate_row = Debate(
            signal_id       = signal_id,
            bull_argument   = bull_arg,
            bear_argument   = bear_arg,
            arbiter_summary = verdict.get("arbiter_summary", ""),
            created_at      = datetime.utcnow(),
        )
        db.add(debate_row)

        # Persist recommendation if arbiter approved
        if verdict.get("include"):
            entry_price = _get_current_price(ticker)
            stop_loss   = None
            if entry_price and verdict.get("stop_loss_pct"):
                stop_loss = round(entry_price * (1 - verdict["stop_loss_pct"] / 100), 4)

            rec = Recommendation(
                signal_id           = signal_id,
                entry_price         = entry_price,
                stop_loss           = stop_loss,
                holding_window_days = verdict.get("holding_window_days", 10),
                conviction_score    = verdict.get("conviction_score", 5.0),
                status              = "pending",
                created_at          = datetime.utcnow(),
            )
            db.add(rec)

        db.commit()
    except Exception as e:
        logger.error("  [%s] DB write failed: %s", ticker, e)
        db.rollback()

    return verdict


def _get_current_price(ticker: str) -> float | None:
    """Gets the most recent closing price for entry price estimation."""
    try:
        df = get_daily_bars(ticker, days=5)
        if not df.empty:
            return float(df["Close"].iloc[-1])
    except Exception:
        pass
    return None
