"""
/api/stock/{ticker}/* routes — chart data, fundamentals, news, competitors.
"""
import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path

import finnhub
from fastapi import APIRouter, Query

from backend.config import FINNHUB_API_KEY
from backend.scanner.data_client import (
    get_daily_bars, get_fundamentals, get_analyst_ratings, get_ticker_details,
)
from backend.scanner.universe import get_sp500_universe

logger = logging.getLogger(__name__)

# yfinance sector names → Wikipedia S&P 500 sector names (universe uses Wikipedia naming)
_SECTOR_ALIASES = {
    "Technology":             "Information Technology",
    "Financial Services":     "Financials",
    "Healthcare":             "Health Care",
    "Consumer Cyclical":      "Consumer Discretionary",
    "Consumer Defensive":     "Consumer Staples",
    "Basic Materials":        "Materials",
    "Communication Services": "Communication Services",
    "Energy":                 "Energy",
    "Industrials":            "Industrials",
    "Utilities":              "Utilities",
    "Real Estate":            "Real Estate",
}

def _normalise_sector(sector: str) -> str:
    """Maps yfinance sector names to Wikipedia naming used by the S&P 500 universe."""
    return _SECTOR_ALIASES.get(sector, sector)
router = APIRouter()

CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache"
CACHE_DIR.mkdir(exist_ok=True)


def _load_cache_ttl(filename: str, hours: int):
    path = CACHE_DIR / filename
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        cached_at = datetime.fromisoformat(data["_cached_at"])
        if datetime.utcnow() - cached_at < timedelta(hours=hours):
            return data["payload"]
    except Exception:
        pass
    return None


def _save_cache_ttl(filename: str, payload):
    path = CACHE_DIR / filename
    path.write_text(json.dumps({
        "_cached_at": datetime.utcnow().isoformat(),
        "payload": payload,
    }))


# ---------------------------------------------------------------------------

@router.get("/{ticker}/chart")
def get_chart(
    ticker: str,
    type: str  = Query(default="candle", pattern="^(candle|line)$"),
    days: int  = Query(default=90, ge=5, le=365),
):
    """OHLCV bars for a ticker. type=candle returns full OHLCV; type=line returns close only."""
    df = get_daily_bars(ticker.upper(), days=days)
    if df.empty:
        return {"ticker": ticker.upper(), "type": type, "bars": []}

    if type == "candle":
        bars = [
            {
                "time":   str(idx.date()),
                "open":   round(float(row["Open"]),   2),
                "high":   round(float(row["High"]),   2),
                "low":    round(float(row["Low"]),    2),
                "close":  round(float(row["Close"]),  2),
                "volume": int(row["Volume"]),
            }
            for idx, row in df.iterrows()
        ]
    else:
        bars = [
            {"time": str(idx.date()), "close": round(float(row["Close"]), 2)}
            for idx, row in df.iterrows()
        ]

    return {"ticker": ticker.upper(), "type": type, "bars": bars}


@router.get("/{ticker}/fundamentals")
def get_stock_fundamentals(ticker: str):
    """P/E, revenue growth, EPS trend, analyst consensus, market cap."""
    t = ticker.upper()
    fund    = get_fundamentals(t)
    ratings = get_analyst_ratings(t)
    details = get_ticker_details(t)

    return {
        "ticker":             t,
        "name":               details.get("name", t),
        "sector":             details.get("sector", "Unknown"),
        "market_cap":         details.get("market_cap"),
        "pe_ratio":           fund.get("pe_ratio"),
        "revenue_yoy_growth": fund.get("revenue_yoy_growth"),
        "eps_quarters":       fund.get("eps_quarters", []),
        "analyst_consensus":  ratings.get("consensus", "unknown"),
        "price_target":       ratings.get("price_target"),
        "current_price":      ratings.get("current_price"),
    }


@router.get("/{ticker}/news")
def get_stock_news(ticker: str):
    """Stock-specific news from Finnhub, last 7 days, cached 6 hours."""
    t = ticker.upper()
    cache_key = f"news_{t}_{date.today().isoformat()}.json"
    cached = _load_cache_ttl(cache_key, hours=6)
    if cached:
        return {"ticker": t, "articles": cached}

    articles = []
    try:
        fh       = finnhub.Client(api_key=FINNHUB_API_KEY)
        to_date  = date.today().isoformat()
        from_date = (date.today() - timedelta(days=7)).isoformat()
        raw = fh.company_news(t, _from=from_date, to=to_date)[:10]
        articles = [
            {
                "headline": item.get("headline", ""),
                "source":   item.get("source", ""),
                "url":      item.get("url", ""),
                "datetime": item.get("datetime"),
                "summary":  item.get("summary", ""),
                "image":    item.get("image", ""),
            }
            for item in raw
        ]
        _save_cache_ttl(cache_key, articles)
    except Exception as e:
        logger.error("get_stock_news(%s) failed: %s", t, e)

    return {"ticker": t, "articles": articles}


@router.get("/{ticker}/competitors")
def get_competitors(ticker: str):
    """
    Top 5 S&P 500 peers by market cap in the same sector.
    Subject ticker is always first row (is_subject=true) for easy comparison.
    """
    t       = ticker.upper()
    details = get_ticker_details(t)
    sector  = details.get("sector", "Unknown")
    # Normalise to Wikipedia naming so it matches the cached universe
    sector_wiki = _normalise_sector(sector)

    universe = get_sp500_universe()
    peers    = [sym for sym, sec in universe if sec == sector_wiki and sym != t]

    # Sort peers by market cap descending — fetch details for each (cached)
    peer_details = []
    for sym in peers:
        d = get_ticker_details(sym)
        mc = d.get("market_cap") or 0
        peer_details.append((sym, d, mc))

    peer_details.sort(key=lambda x: x[2], reverse=True)
    top_peers = [sym for sym, _, _ in peer_details[:5]]

    def _build_row(sym: str, is_subject: bool) -> dict:
        d    = get_ticker_details(sym)
        fund = get_fundamentals(sym)
        df   = get_daily_bars(sym, days=365)

        ret_52w = None
        if not df.empty:
            last  = float(df["Close"].iloc[-1])
            start = float(df["Close"].iloc[-252]) if len(df) >= 252 else float(df["Close"].iloc[0])
            if start > 0:
                ret_52w = round((last - start) / start * 100, 1)

        return {
            "ticker":             sym,
            "name":               d.get("name", sym),
            "market_cap":         d.get("market_cap"),
            "pe_ratio":           fund.get("pe_ratio"),
            "revenue_yoy_growth": fund.get("revenue_yoy_growth"),
            "return_52w":         ret_52w,
            "is_subject":         is_subject,
        }

    competitors = [_build_row(t, True)] + [_build_row(sym, False) for sym in top_peers]
    return {"ticker": t, "sector": sector, "competitors": competitors}
