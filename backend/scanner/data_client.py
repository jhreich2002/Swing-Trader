"""
Data abstraction layer.
All external data fetches go through here — yfinance for price/fundamentals,
Finnhub for analyst ratings and EPS. Results are cached to .cache/ as JSON
files; data older than 24 hours is re-fetched automatically.
"""
import json
import os
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf
import finnhub

from backend.config import FINNHUB_API_KEY

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache"
CACHE_DIR.mkdir(exist_ok=True)
CACHE_TTL_HOURS = 24

_finnhub_client = None


def _get_finnhub():
    global _finnhub_client
    if _finnhub_client is None:
        if not FINNHUB_API_KEY:
            raise RuntimeError("FINNHUB_API_KEY is not set in .env")
        _finnhub_client = finnhub.Client(api_key=FINNHUB_API_KEY)
    return _finnhub_client


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _cache_path(key: str) -> Path:
    safe = key.replace("/", "_").replace("^", "")
    return CACHE_DIR / f"{safe}.json"


def _load_cache(key: str):
    path = _cache_path(key)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        cached_at = datetime.fromisoformat(data["_cached_at"])
        if datetime.utcnow() - cached_at > timedelta(hours=CACHE_TTL_HOURS):
            return None
        return data["payload"]
    except Exception:
        return None


def _save_cache(key: str, payload):
    path = _cache_path(key)
    path.write_text(json.dumps({
        "_cached_at": datetime.utcnow().isoformat(),
        "payload": payload,
    }))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_daily_bars(ticker: str, days: int = 90) -> pd.DataFrame:
    """
    Returns a DataFrame with columns: Open, High, Low, Close, Volume.
    Index is DatetimeIndex sorted ascending.
    """
    cache_key = f"bars_{ticker}_{days}"
    cached = _load_cache(cache_key)
    if cached is not None:
        df = pd.DataFrame(cached)
        df.index = pd.to_datetime(df.index)
        return df

    try:
        tk = yf.Ticker(ticker)
        df = tk.history(period=f"{days}d", interval="1d", auto_adjust=True)
        if df.empty:
            logger.warning("No price data for %s", ticker)
            return pd.DataFrame()
        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.index = df.index.tz_localize(None)
        df_save = df.copy()
        df_save.index = df_save.index.strftime("%Y-%m-%d")
        _save_cache(cache_key, df_save.to_dict())
        return df
    except Exception as e:
        logger.error("get_daily_bars(%s) failed: %s", ticker, e)
        return pd.DataFrame()


def get_ticker_details(ticker: str) -> dict:
    """
    Returns: name, sector, market_cap (float).
    """
    cache_key = f"details_{ticker}"
    cached = _load_cache(cache_key)
    if cached is not None:
        return cached

    try:
        info = yf.Ticker(ticker).info
        result = {
            "name":       info.get("longName", ticker),
            "sector":     info.get("sector", "Unknown"),
            "market_cap": info.get("marketCap"),
        }
        _save_cache(cache_key, result)
        return result
    except Exception as e:
        logger.error("get_ticker_details(%s) failed: %s", ticker, e)
        return {"name": ticker, "sector": "Unknown", "market_cap": None}


def get_fundamentals(ticker: str) -> dict:
    """
    Returns:
      eps_quarters:          list of {period, epsActual} dicts, most recent first
      revenue_qoq_quarters:  list of quarterly revenue floats, most recent first (8 quarters)
      pe_ratio:              float or None
      sector:                str
      earnings_date:         ISO date string of next earnings, or None
    """
    cache_key = f"fundamentals_{ticker}"
    cached = _load_cache(cache_key)
    if cached is not None:
        return cached

    result = {
        "eps_quarters":         [],
        "revenue_qoq_quarters": [],
        "pe_ratio":             None,
        "sector":               "Unknown",
        "earnings_date":        None,
    }
    try:
        tk = yf.Ticker(ticker)
        info = tk.info

        result["pe_ratio"] = info.get("trailingPE") or info.get("forwardPE")
        result["sector"]   = info.get("sector", "Unknown")

        # EPS per quarter from earnings history
        hist = tk.earnings_history
        if hist is not None and not hist.empty and "epsActual" in hist.columns:
            eps_list = []
            for idx, row in hist.iterrows():
                if pd.notna(row.get("epsActual")):
                    eps_list.append({
                        "period":    str(idx.date()) if hasattr(idx, "date") else str(idx),
                        "epsActual": float(row["epsActual"]),
                    })
            result["eps_quarters"] = eps_list

        # Quarterly revenue — most recent 8 quarters, most recent first
        q_inc = tk.quarterly_income_stmt
        if q_inc is not None and not q_inc.empty and "Total Revenue" in q_inc.index:
            rev_row = q_inc.loc["Total Revenue"].dropna()
            # Columns are sorted most-recent first in yfinance
            result["revenue_qoq_quarters"] = [
                float(v) for v in rev_row.iloc[:8].values
            ]

        # Next earnings date from calendar
        try:
            cal = tk.calendar
            if isinstance(cal, dict):
                ed = cal.get("Earnings Date")
                if ed:
                    # May be a list or a single Timestamp
                    if isinstance(ed, list) and len(ed) > 0:
                        ed = ed[0]
                    if hasattr(ed, "date"):
                        result["earnings_date"] = str(ed.date())
                    else:
                        result["earnings_date"] = str(ed)
        except Exception:
            pass

        _save_cache(cache_key, result)
    except Exception as e:
        logger.error("get_fundamentals(%s) failed: %s", ticker, e)

    return result


def get_analyst_ratings(ticker: str) -> dict:
    """
    Returns via Finnhub:
      consensus: "buy" / "hold" / "sell" / "unknown"
      price_target: float or None
      current_price: float or None
    """
    cache_key = f"analyst_{ticker}"
    cached = _load_cache(cache_key)
    if cached is not None:
        return cached

    result = {"consensus": "unknown", "price_target": None, "current_price": None}
    try:
        fh = _get_finnhub()

        # Price target
        pt_data = fh.price_target(ticker)
        result["price_target"]  = pt_data.get("targetMean")
        result["current_price"] = pt_data.get("lastUpdated") and pt_data.get("targetMean")

        # Recommendation trend — use most recent period
        recs = fh.recommendation_trends(ticker)
        if recs:
            latest = recs[0]
            buy    = (latest.get("buy",        0) or 0) + (latest.get("strongBuy",  0) or 0)
            sell   = (latest.get("sell",       0) or 0) + (latest.get("strongSell", 0) or 0)
            hold   = latest.get("hold", 0) or 0
            total  = buy + sell + hold
            if total > 0:
                if buy / total >= 0.5:
                    result["consensus"] = "buy"
                elif sell / total >= 0.5:
                    result["consensus"] = "sell"
                else:
                    result["consensus"] = "hold"

        # Current price from yfinance (more reliable than Finnhub target date)
        info = yf.Ticker(ticker).fast_info
        result["current_price"] = getattr(info, "last_price", None)

        _save_cache(cache_key, result)
    except Exception as e:
        logger.error("get_analyst_ratings(%s) failed: %s", ticker, e)

    return result


def get_key_ratios(ticker: str) -> dict:
    """
    Returns valuation multiples, margins, leverage, and growth ratios from yfinance.
    All values are floats or None if unavailable.
    """
    cache_key = f"ratios_{ticker}"
    cached = _load_cache(cache_key)
    if cached is not None:
        return cached

    result = {
        "pe_trailing":       None,
        "pe_forward":        None,
        "ps_ratio":          None,
        "pb_ratio":          None,
        "ev_ebitda":         None,
        "debt_to_equity":    None,
        "current_ratio":     None,
        "roe":               None,
        "roa":               None,
        "gross_margin":      None,
        "operating_margin":  None,
        "net_margin":        None,
        "revenue_growth":    None,
        "earnings_growth":   None,
        "week52_high":       None,
        "week52_low":        None,
        "beta":              None,
        "dividend_yield":    None,
        "market_cap":        None,
        "enterprise_value":  None,
        "shares_outstanding": None,
        "free_cashflow":     None,
        "total_debt":        None,
    }
    try:
        info = yf.Ticker(ticker).info
        result.update({
            "pe_trailing":       info.get("trailingPE"),
            "pe_forward":        info.get("forwardPE"),
            "ps_ratio":          info.get("priceToSalesTrailing12Months"),
            "pb_ratio":          info.get("priceToBook"),
            "ev_ebitda":         info.get("enterpriseToEbitda"),
            "debt_to_equity":    info.get("debtToEquity"),
            "current_ratio":     info.get("currentRatio"),
            "roe":               info.get("returnOnEquity"),
            "roa":               info.get("returnOnAssets"),
            "gross_margin":      info.get("grossMargins"),
            "operating_margin":  info.get("operatingMargins"),
            "net_margin":        info.get("profitMargins"),
            "revenue_growth":    info.get("revenueGrowth"),
            "earnings_growth":   info.get("earningsGrowth"),
            "week52_high":       info.get("fiftyTwoWeekHigh"),
            "week52_low":        info.get("fiftyTwoWeekLow"),
            "beta":              info.get("beta"),
            "dividend_yield":    info.get("dividendYield"),
            "market_cap":        info.get("marketCap"),
            "enterprise_value":  info.get("enterpriseValue"),
            "shares_outstanding": info.get("sharesOutstanding"),
            "free_cashflow":     info.get("freeCashflow"),
            "total_debt":        info.get("totalDebt"),
        })
        _save_cache(cache_key, result)
    except Exception as e:
        logger.error("get_key_ratios(%s) failed: %s", ticker, e)

    return result


def get_market_snapshot() -> dict:
    """
    Returns:
      spy_bars: DataFrame of SPY daily bars (90 days)
      vix_close: most recent VIX closing price (float)
    """
    cache_key = "market_snapshot"
    cached = _load_cache(cache_key)
    if cached is not None:
        spy_df = pd.DataFrame(cached["spy_bars"])
        spy_df.index = pd.to_datetime(spy_df.index)
        return {"spy_bars": spy_df, "vix_close": cached["vix_close"]}

    try:
        spy_df  = get_daily_bars("SPY", days=90)
        vix_df  = get_daily_bars("^VIX", days=5)
        vix_val = float(vix_df["Close"].iloc[-1]) if not vix_df.empty else None

        if not spy_df.empty and vix_val is not None:
            spy_save = spy_df.copy()
            spy_save.index = spy_save.index.strftime("%Y-%m-%d")
            _save_cache(cache_key, {
                "spy_bars":  spy_save.to_dict(),
                "vix_close": vix_val,
            })
        return {"spy_bars": spy_df, "vix_close": vix_val}
    except Exception as e:
        logger.error("get_market_snapshot() failed: %s", e)
        return {"spy_bars": pd.DataFrame(), "vix_close": None}
