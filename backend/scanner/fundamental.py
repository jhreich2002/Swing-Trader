"""
Fundamental signal scorers.
Each scorer returns:
  {"score": 0|1, "raw": <value>, "detail": "<human readable string>"}

fundamental_profile() assembles all 3 scorers into a single dict per ticker.
The AI receives full detail strings for contextual reasoning.
"""
import logging

from backend.scanner.data_client import get_fundamentals, get_analyst_ratings

logger = logging.getLogger(__name__)

# Approximate sector median trailing P/E ratios.
# Used to flag "below sector median" as a relative-value signal.
SECTOR_PE_BENCHMARKS = {
    "Information Technology": 35,
    "Technology":             35,
    "Financials":             15,
    "Communication Services": 22,
    "Health Care":            25,
    "Energy":                 12,
    "Industrials":            22,
    "Materials":              18,
    "Consumer Discretionary": 28,
    "Consumer Staples":       22,
    "Utilities":              20,
    "Real Estate":            40,
}
_DEFAULT_PE_BENCHMARK = 25


# ---------------------------------------------------------------------------
# Individual fundamental scorers
# ---------------------------------------------------------------------------

def score_eps_trend(eps_quarters: list) -> dict:
    """
    Score 1 if the 2 most recent EPS quarters show consecutive growth
    (Q0 > Q1 > Q2, where Q0 is most recent).
    Catches genuine earnings acceleration, not one-off beats.
    """
    default = {"score": 0, "raw": None, "detail": "Insufficient EPS history"}
    if not eps_quarters or len(eps_quarters) < 3:
        return default

    recent = [q.get("epsActual") for q in eps_quarters[:4]]
    recent = [v for v in recent if v is not None]

    if len(recent) < 3:
        return default

    consecutive = 0
    for i in range(len(recent) - 1):
        if recent[i] > recent[i + 1]:
            consecutive += 1
        else:
            break

    score = int(consecutive >= 2)
    recent_display = [round(v, 2) for v in recent[:4]]
    detail = (
        f"EPS last {len(recent)} qtrs (newest first): {recent_display}, "
        f"{consecutive} consecutive growth qtrs — "
        f"{'accelerating' if score else 'no clear uptrend'}"
    )
    return {"score": score, "raw": round(recent[0], 4) if recent else None, "detail": detail}


def score_revenue_qoq(revenue_quarters: list) -> dict:
    """
    Score 1 if same-quarter year-over-year revenue grew for 2 consecutive quarters.
    Compares Q0 vs Q4 (same quarter, prior year) AND Q1 vs Q5.
    This eliminates seasonal bias — a retail stock's Q1 isn't punished
    for being lower than Q4.
    Requires at least 6 quarters of data.
    """
    default = {"score": 0, "raw": None, "detail": "Insufficient quarterly revenue history"}
    if not revenue_quarters or len(revenue_quarters) < 6:
        return default

    try:
        q = revenue_quarters  # most recent first
        # Same-quarter YoY: Q0 vs 1yr ago (Q4), Q1 vs 1yr ago (Q5)
        yoy_q0 = (q[0] - q[4]) / abs(q[4]) if q[4] != 0 else 0
        yoy_q1 = (q[1] - q[5]) / abs(q[5]) if q[5] != 0 else 0

        both_positive = yoy_q0 > 0 and yoy_q1 > 0
        score = int(both_positive)

        detail = (
            f"Most recent qtr YoY: {yoy_q0*100:+.1f}%, "
            f"prior qtr YoY: {yoy_q1*100:+.1f}% — "
            f"{'2 consecutive qtrs of YoY growth' if score else 'revenue not consistently growing YoY'}"
        )
        return {"score": score, "raw": round(yoy_q0 * 100, 2), "detail": detail}
    except Exception as e:
        logger.warning("score_revenue_qoq failed: %s", e)
        return default


def score_pe_vs_sector(fundamentals: dict) -> dict:
    """
    Score 1 if the stock's trailing P/E is below its sector benchmark.
    Negative P/E (loss-making company) always scores 0.
    """
    pe        = fundamentals.get("pe_ratio")
    sector    = fundamentals.get("sector", "Unknown")
    benchmark = SECTOR_PE_BENCHMARKS.get(sector, _DEFAULT_PE_BENCHMARK)

    if pe is None:
        return {"score": 0, "raw": None, "detail": f"P/E data unavailable (sector benchmark: {benchmark})"}

    if pe <= 0:
        return {
            "score": 0,
            "raw":   round(pe, 2),
            "detail": f"P/E={pe:.1f} (negative — not profitable), sector benchmark={benchmark}",
        }

    score = int(pe < benchmark)
    detail = (
        f"P/E={pe:.1f} vs {sector} benchmark={benchmark} — "
        f"{'below benchmark = relative value' if score else 'above benchmark = stretched'}"
    )
    return {"score": score, "raw": round(pe, 2), "detail": detail}


# ---------------------------------------------------------------------------
# Full profile assembler
# ---------------------------------------------------------------------------

def fundamental_profile(ticker: str) -> dict:
    """
    Fetches and scores all 3 fundamental signals for a single ticker.
    Returns:
      {
        "ticker": str,
        "signals": {
          "eps":     {"score": int, "raw": float, "detail": str},
          "revenue": {...},
          "pe":      {...},
        },
        "signal_count": int,   # 0–3
        "error": str | None,
      }
    """
    result = {
        "ticker":       ticker,
        "signals":      {},
        "signal_count": 0,
        "error":        None,
    }

    try:
        fund_data = get_fundamentals(ticker)

        result["signals"] = {
            "eps":     score_eps_trend(fund_data.get("eps_quarters", [])),
            "revenue": score_revenue_qoq(fund_data.get("revenue_qoq_quarters", [])),
            "pe":      score_pe_vs_sector(fund_data),
        }
        result["signal_count"] = sum(
            s["score"] for s in result["signals"].values() if s["score"] is not None
        )
    except Exception as e:
        logger.error("fundamental_profile(%s) failed: %s", ticker, e)
        result["error"] = str(e)
        for key in ("eps", "revenue", "pe"):
            result["signals"][key] = {"score": 0, "raw": None, "detail": "Data fetch error"}

    return result
