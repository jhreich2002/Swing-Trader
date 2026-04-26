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
from fastapi.staticfiles import StaticFiles

from backend.api import market, recommendations, stock, portfolio, scan, watchlist

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Warm the market synthesis cache at startup so the first request is instant."""
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


app = FastAPI(
    title="Swing Trader API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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
