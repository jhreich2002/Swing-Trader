"""
Market regime detector.
Combines VIX level, SPY moving average relationship, and market breadth
(% of S&P 500 stocks above their 200-day MA) to classify the current
market as: trending / choppy / bearish.

Result is passed into every downstream scanner call so signal thresholds
can be applied in context.
"""
import logging
import pandas as pd

from backend.config import (
    VIX_BEARISH_THRESHOLD,
    BREADTH_BEARISH_THRESHOLD,
    BREADTH_TRENDING_THRESHOLD,
)
from backend.scanner.data_client import get_daily_bars

logger = logging.getLogger(__name__)

# S&P 500 constituents used for breadth calculation.
# Using a representative 100-stock sample to stay within free-tier rate limits.
# Replace with a full list or a database-driven universe for production.
SP500_SAMPLE = [
    "AAPL","MSFT","NVDA","AMZN","META","GOOGL","GOOG","BRK-B","JPM","LLY",
    "V","UNH","XOM","TSLA","MA","JNJ","PG","HD","AVGO","MRK",
    "CVX","COST","ABBV","KO","PEP","WMT","BAC","MCD","CSCO","CRM",
    "ACN","TMO","ABT","ORCL","LIN","DHR","NEE","TXN","ADBE","NKE",
    "PM","INTC","CMCSA","AMD","INTU","VZ","AMGN","HON","UPS","CAT",
    "IBM","GS","SPGI","MS","RTX","AXP","DE","BKNG","ISRG","GE",
    "SYK","MDLZ","SBUX","ADI","REGN","GILD","BLK","MMC","CI","TJX",
    "C","NOW","MO","ZTS","CB","PLD","SO","DUK","USB","EOG",
    "BSX","SCHW","CME","ITW","TGT","ETN","ELV","EMR","APD","AON",
    "SLB","WM","MCO","CL","NSC","FDX","PNC","KLAC","HUM","AIG",
]


def _compute_breadth(sample: list[str]) -> float | None:
    """
    Returns the percentage of stocks in the sample that are trading
    above their 200-day simple moving average.
    """
    above = 0
    total = 0
    for ticker in sample:
        try:
            df = get_daily_bars(ticker, days=210)
            if df.empty or len(df) < 200:
                continue
            sma200 = df["Close"].rolling(200).mean().iloc[-1]
            current = df["Close"].iloc[-1]
            total += 1
            if current > sma200:
                above += 1
        except Exception as e:
            logger.debug("Breadth skip %s: %s", ticker, e)

    if total == 0:
        return None
    return (above / total) * 100


def detect_regime() -> dict:
    """
    Returns:
      {
        "regime":  "trending" | "choppy" | "bearish",
        "vix":     float,
        "spy_above_20sma": bool,
        "spy_above_50sma": bool,
        "breadth_pct":     float,   # % of S&P 500 sample above 200-day MA
        "detail":  str              # human-readable rationale
      }
    """
    from backend.scanner.data_client import get_market_snapshot

    snapshot = get_market_snapshot()
    spy_df   = snapshot["spy_bars"]
    vix      = snapshot["vix_close"]

    result = {
        "regime":           "choppy",
        "vix":              vix,
        "spy_above_20sma":  False,
        "spy_above_50sma":  False,
        "breadth_pct":      None,
        "detail":           "",
    }

    if spy_df.empty or vix is None:
        result["detail"] = "Insufficient data — defaulting to choppy"
        logger.warning("detect_regime: missing SPY or VIX data")
        return result

    close   = spy_df["Close"]
    sma20   = float(close.rolling(20).mean().iloc[-1])
    sma50   = float(close.rolling(50).mean().iloc[-1])
    current = float(close.iloc[-1])

    result["spy_above_20sma"] = current > sma20
    result["spy_above_50sma"] = current > sma50

    logger.info("Computing market breadth (100-stock sample)...")
    breadth = _compute_breadth(SP500_SAMPLE)
    result["breadth_pct"] = breadth

    # --- Classification logic ---
    bearish_signals = 0
    trending_signals = 0

    if vix >= VIX_BEARISH_THRESHOLD:
        bearish_signals += 1
    if not result["spy_above_50sma"]:
        bearish_signals += 1
    if breadth is not None and breadth < BREADTH_BEARISH_THRESHOLD:
        bearish_signals += 1

    if result["spy_above_20sma"] and result["spy_above_50sma"]:
        trending_signals += 1
    if breadth is not None and breadth > BREADTH_TRENDING_THRESHOLD:
        trending_signals += 1
    if vix < 18:
        trending_signals += 1

    if bearish_signals >= 2:
        result["regime"] = "bearish"
    elif trending_signals >= 2:
        result["regime"] = "trending"
    else:
        result["regime"] = "choppy"

    breadth_str = f"{breadth:.1f}%" if breadth is not None else "N/A"
    result["detail"] = (
        f"VIX={vix:.1f}, SPY vs 20-SMA={'above' if result['spy_above_20sma'] else 'below'}, "
        f"SPY vs 50-SMA={'above' if result['spy_above_50sma'] else 'below'}, "
        f"Breadth={breadth_str} above 200-MA | "
        f"Regime: {result['regime'].upper()}"
    )

    return result
