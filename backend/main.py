"""
FastAPI application entry point.

Launch:
    uvicorn backend.main:app --reload --port 8000

The React build is served as static files from frontend/dist.
All /api/* routes are handled by the routers before the static catch-all.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api import market, recommendations, stock, portfolio, scan, watchlist

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Warm the market synthesis cache at startup so the first request is instant."""
    # Sweep stale on-disk cache files (older than 48 h) so .cache/ doesn't grow forever
    try:
        _sweep_stale_cache(max_age_hours=48)
    except Exception as e:
        logger.warning("cache sweep at startup failed: %s", e)

    async def _warm():
        # Small delay so all env vars are fully loaded before touching external APIs
        await asyncio.sleep(2)
        try:
            from backend.synthesis.market_brief import get_market_brief
            logger.info("Warming market synthesis cache...")
            await asyncio.to_thread(get_market_brief)
            logger.info("Market synthesis cache warmed.")
        except Exception as e:
            logger.warning("Could not warm synthesis cache at startup: %s", e)

    asyncio.create_task(_warm())
    yield


def _sweep_stale_cache(max_age_hours: int = 48) -> None:
    """Delete .cache/*.json files older than max_age_hours. Skips universe lists."""
    import time
    cache_dir = Path(__file__).resolve().parents[1] / ".cache"
    if not cache_dir.exists():
        return
    cutoff = time.time() - max_age_hours * 3600
    keep_prefixes = ("sp500_universe", "sp400_universe")
    removed = 0
    for p in cache_dir.glob("*.json"):
        if p.name.startswith(keep_prefixes):
            continue
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink()
                removed += 1
        except OSError:
            pass
    if removed:
        logger.info("Cache sweep removed %d stale files from %s", removed, cache_dir)


app = FastAPI(
    title="Swing Trader API",
    version="1.0.0",
    lifespan=lifespan,
)

# Allow the production Vercel frontend, any preview deploys (*.vercel.app),
# and local dev. Override at runtime by setting CORS_ALLOW_ORIGINS to a
# comma-separated list of explicit origins.
import os
_default_origins = [
    "https://swing-trader-tau.vercel.app",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
_env_origins = [o.strip() for o in os.getenv("CORS_ALLOW_ORIGINS", "").split(",") if o.strip()]
_allow_origins = _env_origins or _default_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_methods=["*"],
    allow_headers=["*"],
)

# Compress JSON/HTML/JS responses larger than 1 KB (≈3-5x reduction on JSON)
app.add_middleware(GZipMiddleware, minimum_size=1024)

app.include_router(market.router,          prefix="/api/market",          tags=["market"])
app.include_router(recommendations.router, prefix="/api/recommendations",  tags=["recommendations"])
app.include_router(stock.router,           prefix="/api/stock",            tags=["stock"])
app.include_router(portfolio.router,       prefix="/api/portfolio",        tags=["portfolio"])
app.include_router(scan.router,            prefix="/api/scan",             tags=["scan"])
app.include_router(watchlist.router,       prefix="/api/watchlist",        tags=["watchlist"])

# Serve the React build — MUST be mounted last (catch-all)
_dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="static")
else:
    logger.warning(
        "frontend/dist not found — run 'npm run build' inside frontend/ to enable static serving. "
        "API routes are still available."
    )
