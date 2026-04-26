"""
Full pipeline entry point — regime → sectors → technical → fundamental → debate.

Usage (from project root):
    python -m backend.run_scan

Phases executed:
  1. Detect market regime (VIX + SPY MAs + breadth)
  2. Identify qualifying sectors (sector ETF momentum filter)
  3. Filter universe to stocks in qualifying sectors
  4. Score all technical + fundamental signals per stock
  5. Compute composite score (60% tech / 40% fundamental, Bayesian-weighted)
  6. Run bull → bear → arbiter debate for candidates with composite ≥ 5.0
  7. Run portfolio concentration review on included recommendations
  8. Save everything to SQLite; print final recommendations

For production (full S&P 500 universe) set USE_FULL_UNIVERSE=True below.
For a quick smoke test, leave it False (uses TEST_UNIVERSE from config.py).
"""
import logging
import sys
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("run_scan")

from backend.config import TEST_UNIVERSE
from backend.scanner.regime import detect_regime
from backend.scanner.sector_filter import get_qualified_sectors
from backend.scanner.technical import technical_profile
from backend.scanner.fundamental import fundamental_profile
from backend.scanner.scorer import compute_composite_score
from backend.scanner.data_client import get_ticker_details, get_market_snapshot
from backend.scanner.universe import get_universe
from backend.learning.bayesian import get_weights
from backend.debate.chain import run_debate_chain
from backend.debate.portfolio_agent import review as portfolio_review
from backend.database import SessionLocal, Signal, Recommendation

# ---- Configuration --------------------------------------------------------
USE_FULL_UNIVERSE  = True    # Set True to scan all ~500 S&P 500 tickers
DEBATE_TOP_N       = 15      # Max candidates to debate (composite ≥ 5.0 gate applies first)
DEBATE_MIN_SCORE   = 5.0     # Minimum composite score to enter the debate chain
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _save_signal(db, profile: dict, fund: dict, score: dict, regime: str) -> int:
    """
    Saves a full signal row (technical + fundamental + composite) to the DB.
    Returns the new row's ID so the debate chain can reference it.
    """
    t = profile["signals"]
    f = fund["signals"]
    ew = profile.get("earnings_warning", {})

    row = Signal(
        ticker    = profile["ticker"],
        scan_date = datetime.utcnow(),
        regime    = regime,

        uptrend_score  = t["uptrend"]["score"],
        uptrend_raw    = t["uptrend"]["raw"],
        uptrend_detail = t["uptrend"]["detail"],

        rsi_score  = t["rsi"]["score"],
        rsi_raw    = t["rsi"]["raw"],
        rsi_detail = t["rsi"]["detail"],

        rs_score  = t["rs"]["score"],
        rs_raw    = t["rs"]["raw"],
        rs_detail = t["rs"]["detail"],

        volume_score  = t["volume"]["score"],
        volume_raw    = t["volume"]["raw"],
        volume_detail = t["volume"]["detail"],

        position_52w_score  = t["position_52w"]["score"],
        position_52w_raw    = t["position_52w"]["raw"],
        position_52w_detail = t["position_52w"]["detail"],

        vcp_score  = t["vcp"]["score"],
        vcp_raw    = t["vcp"]["raw"],
        vcp_detail = t["vcp"]["detail"],

        technical_total = profile["signal_count"],

        earnings_warning = ew.get("warning", False),
        earnings_detail  = ew.get("detail", ""),

        eps_score         = f["eps"]["score"],
        revenue_score     = f["revenue"]["score"],
        pe_score          = f["pe"]["score"],
        fundamental_total = fund["signal_count"],

        composite_score = score["composite"],
    )
    db.add(row)
    db.flush()   # get the auto-generated ID without committing
    return row.id


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _print_scores_table(rows: list[dict]):
    """Prints a compact scoring table sorted by composite score."""
    header = (
        f"{'Ticker':<8} {'Composite':>10} {'Tech':>6} {'Fund':>6} "
        f"{'UPT':>4} {'RSI':>4} {'RS':>4} {'VOL':>4} {'52W':>4} {'VCP':>4} "
        f"{'EPS':>4} {'REV':>4} {'PE':>4} {'ERN':>4}"
    )
    sep = "=" * len(header)
    print(f"\n{sep}\n{header}\n{sep}")
    for r in rows:
        t  = r["tech"]["signals"]
        f  = r["fund"]["signals"]
        s  = r["score"]
        ew = r["tech"].get("earnings_warning", {})
        print(
            f"{r['ticker']:<8} {s['composite']:>10.2f} {s['tech_score']:>6.2f} {s['fund_score']:>6.2f} "
            f"{t['uptrend']['score']:>4} {t['rsi']['score']:>4} "
            f"{t['rs']['score']:>4} {t['volume']['score']:>4} "
            f"{t['position_52w']['score']:>4} {t['vcp']['score']:>4} "
            f"{f['eps']['score']:>4} {f['revenue']['score']:>4} "
            f"{f['pe']['score']:>4} {'W' if ew.get('warning') else '-':>4}"
        )
    print(sep)


def _print_recommendations(verdicts: list[dict]):
    """Prints the final recommended trades."""
    included = [v for v in verdicts if v["verdict"].get("include")]
    if not included:
        print("\n  No high-conviction recommendations this week.\n")
        return

    print(f"\n{'='*60}")
    print(f"  FINAL RECOMMENDATIONS ({len(included)} trades)")
    print(f"{'='*60}\n")

    for i, v in enumerate(included, 1):
        verdict = v["verdict"]
        ew_detail = v.get("earnings_warning_detail", "")
        print(f"  {i}. {v['ticker']}  |  Conviction: {verdict['conviction_score']:.0f}/10")
        if verdict.get("entry_rationale"):
            print(f"     Entry rationale: {verdict['entry_rationale']}")
        if verdict.get("stop_loss_pct"):
            print(f"     Stop loss: {verdict['stop_loss_pct']:.1f}% below entry")
        if verdict.get("holding_window_days"):
            print(f"     Holding window: {verdict['holding_window_days']} trading days")
        if ew_detail:
            print(f"     Earnings: {ew_detail}")
        print()
        summary = verdict.get("arbiter_summary", "")
        for line in summary.split("\n"):
            print(f"     {line}")
        print()

    skipped = [v for v in verdicts if not v["verdict"].get("include")]
    if skipped:
        print(f"  SKIPPED ({len(skipped)}):")
        for v in skipped:
            reason = v["verdict"].get("skip_reason", "Did not meet conviction threshold")
            print(f"    {v['ticker']}: {reason}")
    print()


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run():
    print("\n" + "=" * 60)
    print("  SWING TRADE SCANNER — FULL PIPELINE")
    print("=" * 60)

    # Step 1: Market regime
    logger.info("Detecting market regime...")
    regime_data = detect_regime()
    regime      = regime_data["regime"]
    print(f"\nMARKET REGIME: {regime.upper()}")
    print(f"  {regime_data['detail']}\n")

    # Step 2: Qualified sectors
    logger.info("Scoring sector ETFs...")
    spy_df    = get_market_snapshot()["spy_bars"]
    qualified = get_qualified_sectors(regime, spy_df)

    if not qualified:
        print("No qualifying sectors — market too weak to scan.")
        return

    qual_names = [q["sector"] for q in qualified]
    print("QUALIFYING SECTORS:")
    for q in qualified:
        crit = ", ".join(f"{k}={'Y' if v['score'] else 'N'}" for k, v in q["criteria"].items())
        print(f"  [{q['total']}/3] {q['sector']} ({q['etf']}) — {crit}")
    print()

    # Step 3: Build universe
    if USE_FULL_UNIVERSE:
        logger.info("Loading universe (S&P 500 + S&P 400 + NASDAQ 100)...")
        raw_universe = get_universe()
        universe = [(t, s) for t, s in raw_universe if s in qual_names]
    else:
        logger.info("Using TEST_UNIVERSE (%d tickers)...", len(TEST_UNIVERSE))
        universe = []
        for ticker in TEST_UNIVERSE:
            details = get_ticker_details(ticker)
            sector  = details.get("sector", "Unknown")
            if sector in qual_names:
                universe.append((ticker, sector))

    if not universe:
        print("No tickers fall within qualifying sectors.")
        return

    print(f"SCANNING {len(universe)} TICKERS in qualifying sectors.\n")

    # Step 4 & 5: Technical + fundamental scoring
    logger.info("Loading Bayesian weights for regime '%s'...", regime)
    weights = get_weights(regime)

    all_rows = []
    for ticker, sector in universe:
        logger.info("Scoring %s...", ticker)

        # Fetch fundamentals first so earnings warning can be checked in tech profile
        fund = fundamental_profile(ticker)
        # Pass fund_data to technical_profile so it can check earnings proximity
        from backend.scanner.data_client import get_fundamentals
        fund_data_raw = get_fundamentals(ticker)

        tech  = technical_profile(ticker, sector, regime, fund_data=fund_data_raw)
        score = compute_composite_score(tech, fund, weights)

        if tech.get("error"):
            logger.warning("%s: %s", ticker, tech["error"])
            continue

        all_rows.append({
            "ticker": ticker,
            "sector": sector,
            "tech":   tech,
            "fund":   fund,
            "score":  score,
        })

    if not all_rows:
        print("No scoreable results.")
        return

    # Sort by composite score descending
    all_rows.sort(key=lambda r: r["score"]["composite"], reverse=True)

    # Step 6: Print scoring table
    _print_scores_table(all_rows)

    # Step 7: Save all scored rows to DB, collect signal IDs
    logger.info("Saving %d scored rows to database...", len(all_rows))
    signal_ids = {}
    db = SessionLocal()
    try:
        for row in all_rows:
            sid = _save_signal(db, row["tech"], row["fund"], row["score"], regime)
            signal_ids[row["ticker"]] = sid
        db.commit()
        print(f"\n  Saved {len(all_rows)} scored rows to signals table.")
    except Exception as e:
        logger.error("Database save failed: %s", e)
        db.rollback()
        print(f"\n  WARNING: DB save failed — {e}")

    # Step 8: Run debate chain — only candidates with composite ≥ DEBATE_MIN_SCORE
    debate_candidates = [
        r for r in all_rows if r["score"]["composite"] >= DEBATE_MIN_SCORE
    ][:DEBATE_TOP_N]

    if not debate_candidates:
        print(f"\n  No candidates scored >= {DEBATE_MIN_SCORE} -- no debates this week.\n")
        _print_recommendations([])
        db.close()
        return

    print(f"\n{'='*60}")
    print(f"  RUNNING DEBATE CHAIN ({len(debate_candidates)} candidates >= {DEBATE_MIN_SCORE})")
    print(f"{'='*60}\n")

    verdicts = []
    for row in debate_candidates:
        ticker = row["ticker"]
        sid    = signal_ids.get(ticker)
        ew     = row["tech"].get("earnings_warning", {})
        print(f"  Debating {ticker} (composite={row['score']['composite']:.2f}/10)...")
        if ew.get("warning"):
            print(f"    [EARNINGS WARNING] {ew.get('detail', '')}")

        if sid is None:
            logger.warning("No signal ID for %s — skipping debate", ticker)
            continue

        verdict = run_debate_chain(
            signal_id       = sid,
            ticker          = ticker,
            tech_profile    = row["tech"],
            fund_profile    = row["fund"],
            composite_score = row["score"],
            regime          = regime,
            db              = db,
        )
        verdicts.append({
            "ticker":                ticker,
            "sector":                row["sector"],
            "verdict":               verdict,
            "earnings_warning_detail": ew.get("detail", ""),
        })
        include_str = "INCLUDE" if verdict.get("include") else "SKIP"
        conv        = verdict.get("conviction_score", 0)
        print(f"    -> {include_str}  (conviction={conv}/10)")

    # Step 9: Portfolio concentration review
    included_recs = [
        {
            "ticker":          v["ticker"],
            "sector":          v["sector"],
            "conviction_score": v["verdict"].get("conviction_score", 0),
        }
        for v in verdicts if v["verdict"].get("include")
    ]

    portfolio_note = ""
    if included_recs:
        logger.info("Running portfolio concentration review...")
        portfolio_note = portfolio_review(included_recs)
        if portfolio_note:
            print(f"\n{'='*60}")
            print("  PORTFOLIO CONCENTRATION NOTE")
            print(f"{'='*60}")
            print(f"  {portfolio_note}\n")

        # Persist portfolio_note on each included recommendation
        if portfolio_note:
            try:
                for v in verdicts:
                    if v["verdict"].get("include"):
                        ticker = v["ticker"]
                        sid    = signal_ids.get(ticker)
                        if sid:
                            rec = (
                                db.query(Recommendation)
                                .filter(Recommendation.signal_id == sid)
                                .first()
                            )
                            if rec:
                                rec.portfolio_note = portfolio_note
                db.commit()
            except Exception as e:
                logger.error("Failed to save portfolio_note: %s", e)
                db.rollback()

    # Step 10: Print final recommendations
    _print_recommendations(verdicts)

    print("Scan complete.\n")

    try:
        db.close()
    except Exception:
        pass


if __name__ == "__main__":
    run()
