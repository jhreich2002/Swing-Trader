"""
Multi-index universe fetcher.

Supports: S&P 500, S&P 400 (mid-cap), NASDAQ 100.
All lists are pulled from Wikipedia and cached locally for 7 days.

get_universe() is the main entry point. It combines the configured sources,
deduplicates by ticker, and optionally filters by minimum average daily volume.
"""
import io
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import requests
import pandas as pd

from backend.config import UNIVERSE_SOURCES, UNIVERSE_MIN_AVG_VOLUME

logger     = logging.getLogger(__name__)
CACHE_DIR  = Path(__file__).resolve().parents[2] / ".cache"
CACHE_TTL  = timedelta(days=7)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# Tickers with known yfinance incompatibilities
_SKIP = {"BRK.B", "BF.B", "BRK-B", "BF-B"}


# ---------------------------------------------------------------------------
# Generic Wikipedia table fetcher
# ---------------------------------------------------------------------------

def _fetch_wikipedia_index(url: str, cache_name: str) -> list[tuple[str, str]]:
    """
    Fetches a ticker/sector list from a Wikipedia index page.
    Normalises column names and handles dot-to-hyphen ticker conversion.
    """
    cache_path = CACHE_DIR / f"{cache_name}_universe.json"

    # Try cache first
    if cache_path.exists():
        try:
            data      = json.loads(cache_path.read_text())
            cached_at = datetime.fromisoformat(data["cached_at"])
            if datetime.utcnow() - cached_at < CACHE_TTL:
                logger.info("%s universe loaded from cache (%d tickers)", cache_name, len(data["tickers"]))
                return [tuple(t) for t in data["tickers"]]
        except Exception:
            pass

    logger.info("Fetching %s universe from Wikipedia...", cache_name)
    response = requests.get(url, headers=_HEADERS, timeout=15)
    response.raise_for_status()
    tables = pd.read_html(io.StringIO(response.text))

    # Find the table that has both a ticker column and a sector column
    df = None
    for table in tables:
        cols = [c.strip().lower() for c in table.columns]
        has_ticker = any("ticker" in c or "symbol" in c for c in cols)
        has_sector = any("sector" in c or "gics" in c for c in cols)
        if has_ticker and has_sector:
            df = table
            break

    if df is None:
        # NASDAQ 100 fallback — may only have ticker, no sector column
        for table in tables:
            cols = [c.strip().lower() for c in table.columns]
            if any("ticker" in c or "symbol" in c for c in cols):
                df = table
                break

    if df is None:
        raise ValueError(f"No usable table found at {url}")

    # Flatten multi-level column headers (some Wikipedia tables use them)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [" ".join(str(c) for c in col).strip() for col in df.columns]
    else:
        df.columns = [str(c).strip() for c in df.columns]

    ticker_col = next(
        (c for c in df.columns if "ticker" in c.lower() or "symbol" in c.lower()), None
    )
    sector_col = next(
        (c for c in df.columns if "sector" in c.lower() or "gics" in c.lower()), None
    )

    if ticker_col is None:
        raise ValueError(f"Could not find ticker column in {url}")

    result = []
    for _, row in df.iterrows():
        ticker = str(row[ticker_col]).strip().replace(".", "-")
        sector = str(row[sector_col]).strip() if sector_col else "Unknown"
        if ticker in _SKIP or not ticker or ticker == "nan":
            continue
        result.append((ticker, sector))

    CACHE_DIR.mkdir(exist_ok=True)
    cache_path.write_text(json.dumps({
        "cached_at": datetime.utcnow().isoformat(),
        "tickers":   result,
    }))
    logger.info("%s universe fetched: %d tickers", cache_name, len(result))
    return result


# ---------------------------------------------------------------------------
# Individual index fetchers
# ---------------------------------------------------------------------------

def get_sp500_universe() -> list[tuple[str, str]]:
    try:
        return _fetch_wikipedia_index(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            "sp500",
        )
    except Exception as e:
        logger.error("Failed to fetch S&P 500: %s — using fallback", e)
        return _FALLBACK_SP500


def get_sp400_universe() -> list[tuple[str, str]]:
    try:
        return _fetch_wikipedia_index(
            "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies",
            "sp400",
        )
    except Exception as e:
        logger.error("Failed to fetch S&P 400: %s — returning empty", e)
        return []


def get_nasdaq100_universe() -> list[tuple[str, str]]:
    try:
        return _fetch_wikipedia_index(
            "https://en.wikipedia.org/wiki/Nasdaq-100",
            "nasdaq100",
        )
    except Exception as e:
        logger.error("Failed to fetch NASDAQ 100: %s — returning empty", e)
        return []


# ---------------------------------------------------------------------------
# Combined universe
# ---------------------------------------------------------------------------

def get_universe(
    sources: list[str] | None = None,
    min_avg_volume: int = UNIVERSE_MIN_AVG_VOLUME,
) -> list[tuple[str, str]]:
    """
    Combines the configured index sources, deduplicates by ticker, and
    applies a minimum average daily volume filter.

    Args:
        sources: list of "sp500" | "sp400" | "nasdaq100" (defaults to config)
        min_avg_volume: skip tickers with avg daily volume below this threshold

    Returns:
        Deduplicated list of (ticker, sector) tuples.
    """
    if sources is None:
        sources = UNIVERSE_SOURCES

    _FETCHERS = {
        "sp500":    get_sp500_universe,
        "sp400":    get_sp400_universe,
        "nasdaq100": get_nasdaq100_universe,
    }

    seen:    dict[str, str] = {}   # ticker → sector
    for src in sources:
        fetcher = _FETCHERS.get(src)
        if fetcher is None:
            logger.warning("Unknown universe source '%s' — skipping", src)
            continue
        for ticker, sector in fetcher():
            if ticker not in seen:
                seen[ticker] = sector

    combined = list(seen.items())   # [(ticker, sector), ...]
    logger.info(
        "Combined universe (%s): %d unique tickers before volume filter",
        "+".join(sources), len(combined)
    )

    if min_avg_volume > 0:
        combined = _filter_by_volume(combined, min_avg_volume)

    logger.info("Universe after volume filter: %d tickers", len(combined))
    return combined


def _filter_by_volume(
    universe: list[tuple[str, str]],
    min_avg_volume: int,
) -> list[tuple[str, str]]:
    """
    Removes tickers whose average daily volume (from yfinance fast_info) is below
    the threshold. Uses a lightweight check — no full price history fetch.
    Results are cached per-ticker alongside regular price data.
    """
    import yfinance as yf
    from pathlib import Path
    import json as _json
    from datetime import datetime as _dt

    cache_path = CACHE_DIR / "volume_filter.json"
    vol_cache: dict[str, int] = {}

    if cache_path.exists():
        try:
            data = _json.loads(cache_path.read_text())
            # Only use entries cached today (volume can change)
            today_str = _dt.utcnow().date().isoformat()
            if data.get("date") == today_str:
                vol_cache = data.get("volumes", {})
        except Exception:
            pass

    filtered = []
    updated  = False

    for ticker, sector in universe:
        if ticker in vol_cache:
            avg_vol = vol_cache[ticker]
        else:
            try:
                info    = yf.Ticker(ticker).fast_info
                avg_vol = int(getattr(info, "three_month_average_volume", 0) or 0)
            except Exception:
                avg_vol = 0
            vol_cache[ticker] = avg_vol
            updated = True

        if avg_vol >= min_avg_volume:
            filtered.append((ticker, sector))
        else:
            logger.debug(
                "Skipping %s: avg volume %s < %s minimum",
                ticker, f"{avg_vol:,}", f"{min_avg_volume:,}"
            )

    if updated:
        cache_path.write_text(_json.dumps({
            "date":    _dt.utcnow().date().isoformat(),
            "volumes": vol_cache,
        }))

    removed = len(universe) - len(filtered)
    if removed:
        logger.info("Volume filter removed %d tickers below %s avg daily volume", removed, f"{min_avg_volume:,}")

    return filtered


# ---------------------------------------------------------------------------
# S&P 500 fallback (used if Wikipedia is unreachable)
# ---------------------------------------------------------------------------
_FALLBACK_SP500 = [
    ("AAPL",  "Information Technology"), ("MSFT",  "Information Technology"),
    ("NVDA",  "Information Technology"), ("AMZN",  "Consumer Discretionary"),
    ("META",  "Communication Services"), ("GOOGL", "Communication Services"),
    ("JPM",   "Financials"),             ("BAC",   "Financials"),
    ("V",     "Financials"),             ("MA",    "Financials"),
    ("UNH",   "Health Care"),            ("JNJ",   "Health Care"),
    ("XOM",   "Energy"),                 ("CVX",   "Energy"),
    ("HD",    "Consumer Discretionary"), ("PG",    "Consumer Staples"),
    ("CAT",   "Industrials"),            ("NEE",   "Utilities"),
    ("LIN",   "Materials"),              ("CRM",   "Information Technology"),
]
