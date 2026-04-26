"""
Technical signal scorers — Minervini SEPA/VCP-aligned weekly swing strategy.

Each scorer returns:
  {"score": 0|1, "raw": <numeric value>, "detail": "<human readable string>"}

Signals are forward-looking setup conditions valid as of Sunday close,
intended to remain valid for a Monday entry.

technical_profile() assembles all 6 scored signals plus an earnings warning.

Signal set (6 scored):
  1. uptrend      — Full MA stack: price > 20/50/150/200-day SMAs in correct order,
                    200-day SMA trending up (Minervini Stage 2 template)
  2. rsi          — RSI(14) >= 40 (momentum positive, not broken)
  3. rs           — Stock 3-month return > SPY by >= 10 pct points (market leader)
  4. volume       — 5-day avg volume <= 0.80x baseline (volume drying up, base forming)
  5. position_52w — Price >= 25% above 52-week low AND within 25% of 52-week high
  6. vcp          — Volatility contraction: 3 consecutive 15-day ranges narrowing,
                    price within 10% of the base high (near pivot)
"""
import logging
import pandas as pd
import ta

from backend.scanner.data_client import get_daily_bars

logger = logging.getLogger(__name__)

# Calendar days to fetch — needs to cover 252 trading days (52-week range)
# 400 calendar days ≈ 280 trading days, sufficient for 200d SMA and 52w checks
_FETCH_DAYS = 400


# ---------------------------------------------------------------------------
# Individual signal scorers
# ---------------------------------------------------------------------------

def score_uptrend(df: pd.DataFrame) -> dict:
    """
    Minervini Stage 2 trend template (all 8 conditions):
      1. Price > 150-day SMA
      2. Price > 200-day SMA
      3. 150-day SMA > 200-day SMA
      4. 200-day SMA trending up (current > 21 days ago)
      5. 50-day SMA > 150-day SMA > 200-day SMA (full MA stack)
      6. Price > 50-day SMA
      7. Price > 20-day SMA (confirmation of short-term trend)
      — 52-week positioning is scored separately in score_52week_position

    Raw: % price is above the 200-day SMA.
    """
    default = {"score": 0, "raw": None, "detail": "Insufficient data (need 220+ trading days)"}
    if df.empty or len(df) < 220:
        return default

    close = df["Close"]
    price  = float(close.iloc[-1])
    sma20  = float(close.rolling(20).mean().iloc[-1])
    sma50  = float(close.rolling(50).mean().iloc[-1])
    sma150 = float(close.rolling(150).mean().iloc[-1])
    sma200 = float(close.rolling(200).mean().iloc[-1])

    # 200d SMA trending up: compare current to 21 trading days ago (~1 month)
    sma200_21ago = float(close.rolling(200).mean().iloc[-22])
    sma200_up    = sma200 > sma200_21ago

    price_above_all = price > sma20 and price > sma50 and price > sma150 and price > sma200
    ma_stack_ok     = sma50 > sma150 and sma150 > sma200

    score        = int(price_above_all and ma_stack_ok and sma200_up)
    pct_above_200 = (price - sma200) / sma200 * 100

    if score:
        status = "Stage 2 uptrend confirmed"
    else:
        fails = []
        if not price_above_all:
            fails.append("price below MA(s)")
        if not ma_stack_ok:
            fails.append("MA stack misaligned")
        if not sma200_up:
            fails.append("200d SMA not trending up")
        status = ", ".join(fails)

    detail = (
        f"Price={price:.2f} | 20={sma20:.2f} 50={sma50:.2f} 150={sma150:.2f} 200={sma200:.2f} | "
        f"200d {'up' if sma200_up else 'flat/down'} | {pct_above_200:+.1f}% above 200d -- {status}"
    )
    return {"score": score, "raw": round(pct_above_200, 2), "detail": detail}


def score_rsi_zone(df: pd.DataFrame) -> dict:
    """
    RSI(14) >= 40: momentum is positive, stock not oversold or broken.
    No upper bound — strong trending stocks sustain RSI 60-75.
    Raw: current RSI value.
    """
    default = {"score": 0, "raw": None, "detail": "Insufficient data"}
    if df.empty or len(df) < 20:
        return default

    rsi = ta.momentum.RSIIndicator(df["Close"], window=14).rsi()
    if rsi.isna().all():
        return default

    current_rsi = float(rsi.iloc[-1])
    score       = int(current_rsi >= 40)
    detail = (
        f"RSI(14)={current_rsi:.1f} -- "
        f"{'momentum positive' if score else 'oversold / momentum broken'}"
    )
    return {"score": score, "raw": round(current_rsi, 2), "detail": detail}


def score_relative_strength(df: pd.DataFrame, market_df: pd.DataFrame) -> dict:
    """
    Minervini RS: stock's 3-month (63-day) return must exceed SPY by >= 10 pct points.
    This filters for true market leaders, not just sector followers.
    Raw: return differential (stock - SPY) in %.
    """
    default = {"score": 0, "raw": None, "detail": "Insufficient data"}
    if df.empty or market_df.empty or len(df) < 64 or len(market_df) < 64:
        return default

    stock_ret  = (float(df["Close"].iloc[-1])     - float(df["Close"].iloc[-64]))     / float(df["Close"].iloc[-64])
    market_ret = (float(market_df["Close"].iloc[-1]) - float(market_df["Close"].iloc[-64])) / float(market_df["Close"].iloc[-64])

    diff  = stock_ret - market_ret
    score = int(diff >= 0.10)   # Must outperform SPY by >= 10 percentage points

    detail = (
        f"Stock 3m={stock_ret*100:.1f}%, SPY={market_ret*100:.1f}%, diff={diff*100:+.1f}% -- "
        f"{'market leader (>= +10%)' if score else 'not a market leader vs SPY'}"
    )
    return {"score": score, "raw": round(diff * 100, 2), "detail": detail}


def score_volume_contraction(df: pd.DataFrame) -> dict:
    """
    Minervini VCP volume: 5-day avg volume <= 0.80x the 20-day prior baseline.
    Volume drying up signals a base is forming and institutional selling has ceased.
    This is the opposite of the old "accumulation surge" check — we want quiet before
    the breakout, not a volume spike (that happens on entry day, not in the scan).
    Raw: ratio of 5-day avg to 20-day baseline (lower = more contraction).
    """
    default = {"score": 0, "raw": None, "detail": "Insufficient data"}
    if df.empty or len(df) < 30:
        return default

    volume  = df["Volume"]
    avg_5d  = float(volume.iloc[-5:].mean())
    avg_20d = float(volume.iloc[-25:-5].mean())   # prior 20 days as baseline

    if avg_20d == 0:
        return default

    ratio = avg_5d / avg_20d
    score = int(ratio <= 0.80)   # volume contracting >= 20% below baseline

    detail = (
        f"5-day avg vol={avg_5d:,.0f}, 20-day baseline={avg_20d:,.0f}, "
        f"ratio={ratio:.2f}x -- "
        f"{'volume drying up (base forming)' if score else 'volume elevated / no contraction'}"
    )
    return {"score": score, "raw": round(ratio, 3), "detail": detail}


def score_52week_position(df: pd.DataFrame) -> dict:
    """
    Minervini Stage 2 price zone:
      - Price >= 25% above 52-week low  (stock has already broken out of a base)
      - Price within 25% of 52-week high (stock is near the top, not a laggard)
    Together these confirm the stock is in Stage 2 (advancing), not Stage 1 (base) or Stage 3/4.
    Raw: % above 52-week low.
    """
    default = {"score": 0, "raw": None, "detail": "Insufficient data (need 252+ trading days)"}
    if df.empty or len(df) < 252:
        return default

    close       = df["Close"]
    price       = float(close.iloc[-1])
    high_52w    = float(close.iloc[-252:].max())
    low_52w     = float(close.iloc[-252:].min())

    pct_above_low  = (price - low_52w)  / low_52w  * 100
    pct_from_high  = (high_52w - price) / high_52w * 100

    above_low_ok = pct_above_low >= 25
    near_high_ok  = pct_from_high <= 25

    score = int(above_low_ok and near_high_ok)

    if score:
        status = "Stage 2 price zone"
    else:
        fails = []
        if not above_low_ok:
            fails.append(f"only {pct_above_low:.0f}% above 52w-low (need 25%+)")
        if not near_high_ok:
            fails.append(f"{pct_from_high:.0f}% below 52w-high (need within 25%)")
        status = ", ".join(fails)

    detail = (
        f"Price={price:.2f} | 52w-high={high_52w:.2f} ({pct_from_high:.1f}% below) | "
        f"52w-low={low_52w:.2f} ({pct_above_low:.1f}% above) -- {status}"
    )
    return {"score": score, "raw": round(pct_above_low, 2), "detail": detail}


def score_vcp(df: pd.DataFrame) -> dict:
    """
    Volatility Contraction Pattern (VCP) proxy.
    Splits the last 45 trading days into 3 equal 15-day periods.
    Measures the high-low range as a % of the midpoint for each period.
    Score 1 if:
      - All 3 range values are contracting (p1 > p2 > p3)
      - Current price is within 10% of the 45-day base high (near pivot)
    Raw: ratio of most recent range to earliest range (lower = more contraction).
    """
    default = {"score": 0, "raw": None, "detail": "Insufficient data"}
    if df.empty or len(df) < 50:
        return default

    def _range_pct(s: pd.DataFrame) -> float:
        h   = float(s["High"].max())
        lo  = float(s["Low"].min())
        mid = (h + lo) / 2
        return (h - lo) / mid * 100 if mid > 0 else 0.0

    p1 = _range_pct(df.iloc[-45:-30])   # oldest 15 days
    p2 = _range_pct(df.iloc[-30:-15])   # middle 15 days
    p3 = _range_pct(df.iloc[-15:])      # most recent 15 days

    contracting = p1 > p2 > p3

    base_high          = float(df["High"].iloc[-45:].max())
    price              = float(df["Close"].iloc[-1])
    pct_from_base_high = (base_high - price) / base_high * 100 if base_high > 0 else 100
    near_pivot         = pct_from_base_high <= 10

    score             = int(contracting and near_pivot)
    contraction_ratio = round(p3 / p1, 3) if p1 > 0 else 1.0

    if score:
        status = "VCP confirmed: volatility contracting near pivot"
    else:
        fails = []
        if not contracting:
            fails.append(f"ranges not contracting ({p1:.1f}%>{p2:.1f}%>{p3:.1f}% required)")
        if not near_pivot:
            fails.append(f"{pct_from_base_high:.1f}% below base high (need within 10%)")
        status = ", ".join(fails) if fails else "no pattern"

    detail = (
        f"15-day ranges: {p1:.1f}% -> {p2:.1f}% -> {p3:.1f}% | "
        f"{pct_from_base_high:.1f}% below 45d-high -- {status}"
    )
    return {"score": score, "raw": contraction_ratio, "detail": detail}


# ---------------------------------------------------------------------------
# Earnings proximity warning (not scored — context for AI only)
# ---------------------------------------------------------------------------

def check_earnings_proximity(fund_data: dict) -> dict:
    """
    Returns a warning dict if earnings are within 14 calendar days.
    NOT a scored signal — passed to AI as risk context.
    """
    from datetime import date
    earnings_date_str = fund_data.get("earnings_date")
    if not earnings_date_str:
        return {"warning": False, "detail": "Earnings date unknown", "days_until": None}

    try:
        ed         = date.fromisoformat(str(earnings_date_str)[:10])
        today      = date.today()
        days_until = (ed - today).days
        if days_until < 0:
            return {"warning": False, "detail": f"Last earnings: {ed.isoformat()}", "days_until": days_until}
        warning = days_until <= 14
        detail  = (
            f"Earnings in {days_until} days ({ed.isoformat()}) -- "
            f"{'WARNING: within 2-week hold window' if warning else 'outside hold window'}"
        )
        return {"warning": warning, "detail": detail, "days_until": days_until}
    except Exception:
        return {"warning": False, "detail": "Could not parse earnings date", "days_until": None}


# ---------------------------------------------------------------------------
# Full profile assembler
# ---------------------------------------------------------------------------

def technical_profile(ticker: str, sector: str, regime: str, fund_data: dict | None = None) -> dict:
    """
    Fetches price data and runs all 6 technical scorers for a single ticker.
    Also checks earnings proximity warning (requires fund_data).

    Returns:
      {
        "ticker":  str,
        "sector":  str,
        "regime":  str,
        "signals": {
          "uptrend":      {"score": int, "raw": float, "detail": str},
          "rsi":          {...},
          "rs":           {...},
          "volume":       {...},
          "position_52w": {...},
          "vcp":          {...},
        },
        "signal_count":     int,   # 0-6
        "earnings_warning": {"warning": bool, "detail": str, "days_until": int|None},
        "error": str | None,
      }
    """
    result = {
        "ticker":           ticker,
        "sector":           sector,
        "regime":           regime,
        "signals":          {},
        "signal_count":     0,
        "earnings_warning": {"warning": False, "detail": "No earnings data", "days_until": None},
        "error":            None,
    }

    # Fetch 400 calendar days — covers 200d SMA (needs ~280 trading days) and 52-week range
    df = get_daily_bars(ticker, days=_FETCH_DAYS)
    if df.empty:
        result["error"] = f"No price data for {ticker}"
        return result

    # SPY for market-wide relative strength comparison
    spy_df = get_daily_bars("SPY", days=_FETCH_DAYS)

    result["signals"] = {
        "uptrend":      score_uptrend(df),
        "rsi":          score_rsi_zone(df),
        "rs":           score_relative_strength(df, spy_df),
        "volume":       score_volume_contraction(df),
        "position_52w": score_52week_position(df),
        "vcp":          score_vcp(df),
    }
    result["signal_count"] = sum(
        s["score"] for s in result["signals"].values() if s["score"] is not None
    )

    if fund_data:
        result["earnings_warning"] = check_earnings_proximity(fund_data)

    return result
