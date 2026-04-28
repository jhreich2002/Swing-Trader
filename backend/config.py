import os
from dotenv import load_dotenv

load_dotenv()

# --- API keys ---
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GOOGLE_API_KEY    = os.getenv("GOOGLE_API_KEY", "")
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
SENDGRID_FROM_EMAIL = os.getenv("SENDGRID_FROM_EMAIL", "")
ALERT_TO_EMAIL = os.getenv("ALERT_TO_EMAIL", "")

# --- Database ---
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./swingtrade.db")

# --- IBKR ---
IBKR_HOST = os.getenv("IBKR_HOST", "127.0.0.1")
IBKR_PORT = int(os.getenv("IBKR_PORT", "7497"))
IBKR_CLIENT_ID = int(os.getenv("IBKR_CLIENT_ID", "1"))

# --- Sector ETF map ---
# Maps sector name → SPDR ETF ticker
# Includes both Wikipedia naming ("Information Technology") and
# yfinance naming ("Technology") so lookups work from both sources
SECTOR_ETF_MAP = {
    "Information Technology": "XLK",   # Wikipedia S&P 500 list naming
    "Technology":             "XLK",   # yfinance .info naming
    "Financials":             "XLF",
    "Communication Services": "XLC",
    "Health Care":            "XLV",
    "Energy":                 "XLE",
    "Industrials":            "XLI",
    "Materials":              "XLB",
    "Consumer Discretionary": "XLY",
    "Consumer Staples":       "XLP",
    "Utilities":              "XLU",
    "Real Estate":            "XLRE",
}

# --- Scanner universe ---
# Which index lists to include in the full scan universe.
# Options: "sp500", "sp400", "nasdaq100"
# sp500 + sp400 = ~900 unique tickers (Russell 1000 equivalent)
# Adding nasdaq100 adds ~20 unique names not already in sp500.
UNIVERSE_SOURCES = ["sp500", "sp400"]   # ~903 unique tickers (Russell 1000 equivalent)
# "nasdaq100" is supported but ~95% overlaps with sp500, so adds minimal unique names

# Minimum average daily volume to include a ticker (filters illiquid mid-caps)
UNIVERSE_MIN_AVG_VOLUME = 500_000

# Small test universe used by run_scan.py when USE_FULL_UNIVERSE=False
TEST_UNIVERSE = [
    "AAPL", "MSFT", "NVDA", "META", "GOOGL",   # Technology / Comms
    "JPM",  "BAC",  "V",                         # Financials
    "XOM",  "CVX",                               # Energy
    "UNH",  "JNJ",                               # Health Care
    "AMZN", "HD",                                # Consumer Discretionary
    "PG",                                        # Consumer Staples
]

# --- Regime thresholds ---
VIX_BEARISH_THRESHOLD = 25       # VIX above this → bearish signal
BREADTH_BEARISH_THRESHOLD = 40   # % of S&P above 200MA below this → bearish signal
BREADTH_TRENDING_THRESHOLD = 60  # % of S&P above 200MA above this → trending signal

# --- Sector filter limits by regime ---
SECTOR_LIMIT = {
    "trending": 5,
    "choppy":   3,
    "bearish":  2,
}

# --- Signal holding windows (in trading days) ---
# Each signal implies a different trade duration. min = earliest exit, max = latest exit.
# When multiple signals fire the holding window = max across fired signals.
SIGNAL_WINDOWS = {
    "uptrend":      {"min": 5,  "max": 15},  # Stage 2 trend template
    "rsi":          {"min": 5,  "max": 10},  # Momentum zone
    "rs":           {"min": 10, "max": 20},  # Market leadership
    "volume":       {"min": 5,  "max": 10},  # Base contraction / dry-up
    "position_52w": {"min": 5,  "max": 15},  # Stage 2 price zone (25% above low, near high)
    "vcp":          {"min": 3,  "max": 10},  # Volatility contraction near pivot
}

# When multiple signals fire on the same stock, the holding window is
# determined by the signal with the longest max window among those that fired.
# This gives the trade its best chance to play out.

# --- Backtester settings ---
BACKTEST_YEARS       = 3         # How many years of history to replay
BACKTEST_STEP_DAYS   = 5         # Step forward N trading days between each scan (weekly)
ATR_STOP_MULTIPLIER  = 1.5       # Stop loss = entry − (ATR × this)
ATR_PERIOD           = 14        # ATR calculation period
WIN_REQUIRES_NO_STOP = True      # A win requires: price up AND stop not hit
