"""
/api/market/* routes — market regime, index prices, AI synthesis, news.
"""
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import finnhub
from fastapi import APIRouter

from backend.config import FINNHUB_API_KEY
from backend.scanner.regime import detect_regime
from backend.scanner.data_client import get_daily_bars

logger = logging.getLogger(__name__)
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

@router.get("/regime")
def get_regime():
    """Current market regime: trending / choppy / bearish."""
    try:
        data = detect_regime()
        return {
            "regime":          data.get("regime", "unknown"),
            "vix":             data.get("vix"),
            "breadth_pct":     data.get("breadth_pct"),
            "spy_above_20sma": data.get("spy_above_20sma"),
            "spy_above_50sma": data.get("spy_above_50sma"),
            "detail":          data.get("detail", ""),
        }
    except Exception as e:
        logger.error("get_regime failed: %s", e)
        return {"regime": "unknown", "detail": str(e)}


@router.get("/indices")
def get_indices():
    """365 days of daily close prices for SPY, QQQ, DIA."""
    result = {}
    for ticker, key in [("SPY", "spy"), ("QQQ", "qqq"), ("DIA", "dia")]:
        df = get_daily_bars(ticker, days=365)
        if df.empty:
            result[key] = []
        else:
            result[key] = [
                {"date": str(idx.date()), "close": round(float(row["Close"]), 2)}
                for idx, row in df.iterrows()
            ]
    return result


@router.get("/synthesis")
def get_synthesis():
    """AI market synthesis — generated once per day via Claude Opus."""
    from backend.synthesis.market_brief import get_market_brief
    try:
        return get_market_brief()
    except Exception as e:
        logger.error("get_synthesis failed: %s", e)
        return {
            "synthesis": "Market synthesis temporarily unavailable.",
            "themes": [],
            "generated_at": datetime.utcnow().date().isoformat(),
        }


@router.get("/news")
def get_market_news():
    """General market news from Finnhub, cached 6 hours."""
    cached = _load_cache_ttl("market_news.json", hours=6)
    if cached:
        return {"articles": cached}

    articles = []
    try:
        fh = finnhub.Client(api_key=FINNHUB_API_KEY)
        raw = fh.general_news(category="general", min_id=0)[:15]
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
        _save_cache_ttl("market_news.json", articles)
    except Exception as e:
        logger.error("get_market_news failed: %s", e)

    return {"articles": articles}
