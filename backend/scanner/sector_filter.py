"""
Sector momentum pre-filter.
Scores each of the 11 SPDR sector ETFs on 3 criteria and returns the
top qualifying sectors for the current market regime.

This runs FIRST in the pipeline — individual stocks are only scanned
within sectors that pass this filter.
"""
import logging
import pandas as pd

from backend.config import SECTOR_ETF_MAP, SECTOR_LIMIT
from backend.scanner.data_client import get_daily_bars

logger = logging.getLogger(__name__)


def score_sector_etf(etf_ticker: str, spy_df: pd.DataFrame) -> dict:
    """
    Scores a single sector ETF on 3 momentum criteria.

    Returns:
      {
        "ticker":       str,
        "criteria": {
          "above_20sma":   {"score": 0|1, "detail": str},
          "golden_cross":  {"score": 0|1, "detail": str},
          "vs_spy":        {"score": 0|1, "detail": str},
        },
        "total":        int (0–3),
        "error":        str or None
      }
    """
    result = {
        "ticker":   etf_ticker,
        "criteria": {},
        "total":    0,
        "error":    None,
    }

    df = get_daily_bars(etf_ticker, days=90)
    if df.empty or len(df) < 55:
        result["error"] = f"Insufficient data for {etf_ticker}"
        return result

    close   = df["Close"]
    sma20   = close.rolling(20).mean()
    sma50   = close.rolling(50).mean()
    current = float(close.iloc[-1])

    # --- Criterion 1: Price > 20-day SMA ---
    s20 = float(sma20.iloc[-1])
    above = current > s20
    result["criteria"]["above_20sma"] = {
        "score":  int(above),
        "detail": f"Price {current:.2f} {'>' if above else '<='} 20-SMA {s20:.2f}",
    }

    # --- Criterion 2: 20-day SMA > 50-day SMA (golden cross) ---
    s50 = float(sma50.iloc[-1])
    cross = s20 > s50
    result["criteria"]["golden_cross"] = {
        "score":  int(cross),
        "detail": f"20-SMA {s20:.2f} {'>' if cross else '<='} 50-SMA {s50:.2f}",
    }

    # --- Criterion 3: 20-day return > SPY 20-day return ---
    if len(df) >= 21 and not spy_df.empty and len(spy_df) >= 21:
        etf_ret = (current - float(close.iloc[-21])) / float(close.iloc[-21])
        spy_ret = (
            float(spy_df["Close"].iloc[-1]) - float(spy_df["Close"].iloc[-21])
        ) / float(spy_df["Close"].iloc[-21])
        outperform = etf_ret > spy_ret
        diff = (etf_ret - spy_ret) * 100
        result["criteria"]["vs_spy"] = {
            "score":  int(outperform),
            "detail": f"ETF 20d ret {etf_ret*100:.1f}% vs SPY {spy_ret*100:.1f}% (diff {diff:+.1f}%)",
        }
    else:
        result["criteria"]["vs_spy"] = {"score": 0, "detail": "Insufficient data for SPY comparison"}

    result["total"] = sum(c["score"] for c in result["criteria"].values())
    return result


def get_qualified_sectors(regime: str, spy_df: pd.DataFrame) -> list[dict]:
    """
    Scores all 11 sector ETFs and returns qualifying sectors for the regime.

    Qualification thresholds:
      trending → 2 of 3 criteria, top 5 returned
      choppy   → 3 of 3 criteria, top 3 returned
      bearish  → 3 of 3 criteria, top 2 returned

    Returns list of dicts:
      [{"sector": str, "etf": str, "total": int, "criteria": {...}}, ...]
    """
    min_score = 3 if regime in ("choppy", "bearish") else 2
    limit     = SECTOR_LIMIT.get(regime, 5)

    scored = []
    for sector, etf in SECTOR_ETF_MAP.items():
        try:
            result = score_sector_etf(etf, spy_df)
            if result["error"]:
                logger.warning("Sector %s skipped: %s", sector, result["error"])
                continue
            scored.append({
                "sector":   sector,
                "etf":      etf,
                "total":    result["total"],
                "criteria": result["criteria"],
            })
        except Exception as e:
            logger.error("Error scoring sector %s (%s): %s", sector, etf, e)

    # Sort by score descending, take top N that meet minimum threshold
    qualified = [s for s in scored if s["total"] >= min_score]
    qualified.sort(key=lambda x: x["total"], reverse=True)
    return qualified[:limit]
