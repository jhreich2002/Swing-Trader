"""
Full-company digest for a watchlist ticker.
Fetches price, ratios, fundamentals, news, and runs long-term bull/bear analysis.
Stores result as JSON in the watchlist_items.digest_json column.
"""
import json
import logging
from datetime import datetime, timezone

import yfinance as yf

from backend.scanner.data_client import (
    get_ticker_details,
    get_fundamentals,
    get_key_ratios,
    get_analyst_ratings,
)
from backend.watchlist.analyst import make_long_term_bull, make_long_term_bear, evaluate_cramer_checklist

logger = logging.getLogger(__name__)


def _get_news(ticker: str) -> list[dict]:
    """Fetch recent news headlines via yfinance (no Finnhub dependency for watchlist)."""
    try:
        tk = yf.Ticker(ticker)
        raw = tk.news or []
        articles = []
        for item in raw[:12]:
            content = item.get("content") or {}
            # yfinance news format varies by version — handle both structures
            title      = content.get("title") or item.get("title", "")
            summary    = content.get("summary") or item.get("summary", "")
            pub_date   = content.get("pubDate") or item.get("providerPublishTime")
            source     = (content.get("provider") or {}).get("displayName") or item.get("publisher", "")
            url        = (content.get("canonicalUrl") or {}).get("url") or item.get("link", "")
            thumbnail  = (
                ((content.get("thumbnail") or {}).get("resolutions") or [{}])[0].get("url")
                or item.get("thumbnail", {}).get("resolutions", [{}])[0].get("url", "")
                if isinstance(item.get("thumbnail"), dict) else ""
            )
            if title:
                articles.append({
                    "headline": title,
                    "summary":  summary,
                    "source":   source,
                    "url":      url,
                    "datetime": str(pub_date) if pub_date else "",
                    "image":    thumbnail,
                })
        return articles
    except Exception as e:
        logger.error("News fetch failed for %s: %s", ticker, e)
        return []


def _get_current_price(ticker: str) -> float | None:
    try:
        return getattr(yf.Ticker(ticker).fast_info, "last_price", None)
    except Exception:
        return None


def _compute_quant_checks(fund: dict, ratios: dict) -> list[dict]:
    """
    Evaluates 6 quantitative Cramer criteria from ratio / fundamental data.
    Returns list of {id, label, category, status, rationale} dicts.
    """
    checks = []

    def _check(id_, label, category, condition, pass_str, fail_str, unknown_str="Insufficient data."):
        if condition is None:
            checks.append({"id": id_, "label": label, "category": category,
                           "status": "unknown", "rationale": unknown_str})
        elif condition:
            checks.append({"id": id_, "label": label, "category": category,
                           "status": "pass", "rationale": pass_str})
        else:
            checks.append({"id": id_, "label": label, "category": category,
                           "status": "fail", "rationale": fail_str})

    # 1. Revenue growth
    rev_g = ratios.get("revenue_growth")
    if rev_g is not None:
        _check("revenue_growth", "Revenue growing YoY", "fundamentals",
               rev_g > 0,
               f"Revenue growing at {rev_g*100:.1f}% YoY.",
               f"Revenue declining at {rev_g*100:.1f}% YoY — top-line weakness.")
    else:
        _check("revenue_growth", "Revenue growing YoY", "fundamentals",
               None, "", "", "Revenue growth data unavailable.")

    # 2. EPS momentum — last 2 quarters both positive and growing vs prior year
    eps_qs = fund.get("eps_quarters", [])
    if len(eps_qs) >= 3:
        recent = [q.get("epsActual", 0) for q in eps_qs[:3]]
        both_pos  = recent[0] > 0 and recent[1] > 0
        growing   = recent[0] > recent[1] > recent[2]
        if both_pos and growing:
            status, rationale = "pass", f"EPS positive and accelerating: ${recent[0]:.2f}, ${recent[1]:.2f}, ${recent[2]:.2f}."
        elif both_pos:
            status, rationale = "partial", f"EPS positive last 2 quarters (${recent[0]:.2f}, ${recent[1]:.2f}) but not accelerating."
        else:
            status, rationale = "fail", f"EPS not consistently positive: ${recent[0]:.2f}, ${recent[1]:.2f}."
        checks.append({"id": "eps_momentum", "label": "EPS positive & growing (2+ qtrs)", "category": "fundamentals",
                        "status": status, "rationale": rationale})
    else:
        checks.append({"id": "eps_momentum", "label": "EPS positive & growing (2+ qtrs)", "category": "fundamentals",
                        "status": "unknown", "rationale": "Insufficient EPS history."})

    # 3. Healthy margins
    gm = ratios.get("gross_margin")
    om = ratios.get("operating_margin")
    if gm is not None and om is not None:
        if gm > 0.25 and om > 0:
            status = "pass"
            rationale = f"Gross margin {gm*100:.1f}% and operating margin {om*100:.1f}% — healthy."
        elif gm > 0.10 and om > 0:
            status = "partial"
            rationale = f"Gross margin {gm*100:.1f}% is below the 25% threshold but operating margin {om*100:.1f}% is positive."
        else:
            status = "fail"
            rationale = f"Margin concern: gross {gm*100:.1f}%, operating {om*100:.1f}%."
        checks.append({"id": "healthy_margins", "label": "Healthy margins (gross >25%, op >0%)", "category": "fundamentals",
                        "status": status, "rationale": rationale})
    else:
        checks.append({"id": "healthy_margins", "label": "Healthy margins (gross >25%, op >0%)", "category": "fundamentals",
                        "status": "unknown", "rationale": "Margin data unavailable."})

    # 4. Balance sheet
    de  = ratios.get("debt_to_equity")
    cr  = ratios.get("current_ratio")
    if de is not None and cr is not None:
        if de < 2.0 and cr > 1.0:
            status = "pass"
            rationale = f"Debt/equity {de:.1f}x and current ratio {cr:.1f}x — manageable leverage."
        elif de < 3.0 and cr > 0.8:
            status = "partial"
            rationale = f"Balance sheet borderline: D/E {de:.1f}x, current ratio {cr:.1f}x."
        else:
            status = "fail"
            rationale = f"Elevated leverage or liquidity risk: D/E {de:.1f}x, current ratio {cr:.1f}x."
        checks.append({"id": "balance_sheet", "label": "Strong balance sheet (D/E <2x, CR >1)", "category": "fundamentals",
                        "status": status, "rationale": rationale})
    elif de is not None:
        cond = de < 2.0
        checks.append({"id": "balance_sheet", "label": "Strong balance sheet (D/E <2x, CR >1)", "category": "fundamentals",
                        "status": "pass" if cond else "fail",
                        "rationale": f"Debt/equity {de:.1f}x (current ratio data missing)."})
    else:
        checks.append({"id": "balance_sheet", "label": "Strong balance sheet (D/E <2x, CR >1)", "category": "fundamentals",
                        "status": "unknown", "rationale": "Balance sheet data unavailable."})

    # 5. Positive FCF
    fcf = ratios.get("free_cashflow")
    if fcf is not None:
        def _fmt(v):
            if abs(v) >= 1e9: return f"${v/1e9:.1f}B"
            if abs(v) >= 1e6: return f"${v/1e6:.0f}M"
            return f"${v:,.0f}"
        _check("positive_fcf", "Positive free cash flow", "fundamentals",
               fcf > 0,
               f"Free cash flow positive at {_fmt(fcf)}.",
               f"Negative free cash flow of {_fmt(fcf)} — cash burn concern.")
    else:
        checks.append({"id": "positive_fcf", "label": "Positive free cash flow", "category": "fundamentals",
                        "status": "unknown", "rationale": "FCF data unavailable."})

    # 6. Reasonable valuation
    pe_fwd = ratios.get("pe_forward")
    pe_tr  = ratios.get("pe_trailing")
    if pe_fwd is not None:
        if pe_fwd < 30:
            status, rationale = "pass", f"Forward P/E of {pe_fwd:.1f}x is reasonable."
        elif pe_fwd < 50:
            status, rationale = "partial", f"Forward P/E of {pe_fwd:.1f}x is elevated but not extreme."
        else:
            status, rationale = "fail", f"Forward P/E of {pe_fwd:.1f}x is high — limited margin of safety."
        checks.append({"id": "reasonable_valuation", "label": "Reasonable valuation (fwd P/E <50x)", "category": "fundamentals",
                        "status": status, "rationale": rationale})
    elif pe_tr is not None:
        if pe_tr < 40:
            status, rationale = "pass", f"Trailing P/E of {pe_tr:.1f}x is reasonable."
        elif pe_tr < 60:
            status, rationale = "partial", f"Trailing P/E of {pe_tr:.1f}x is elevated."
        else:
            status, rationale = "fail", f"Trailing P/E of {pe_tr:.1f}x is high."
        checks.append({"id": "reasonable_valuation", "label": "Reasonable valuation (fwd P/E <50x)", "category": "fundamentals",
                        "status": status, "rationale": rationale})
    else:
        checks.append({"id": "reasonable_valuation", "label": "Reasonable valuation (fwd P/E <50x)", "category": "fundamentals",
                        "status": "unknown", "rationale": "P/E data unavailable."})

    return checks


# Labels and categories for AI qualitative checks
_QUALITATIVE_META = {
    "business_clarity":  ("Business model clarity",          "quality"),
    "secular_growth":    ("Secular growth (not cyclical)",    "quality"),
    "growth_runway":     ("Large TAM / growth runway",        "quality"),
    "competitive_moat":  ("Competitive moat / edge",          "quality"),
    "management_quality":("Management execution quality",     "quality"),
    "disruption_risk":   ("No disruption / obsolescence risk","risk"),
    "concentration_risk":("No dangerous concentration risk",  "risk"),
}


def run_digest(ticker: str) -> dict:
    """
    Run a complete digest for the ticker.
    Returns the digest dict (also suitable for JSON serialisation).
    """
    ticker = ticker.upper().strip()
    logger.info("Digesting %s...", ticker)

    details  = get_ticker_details(ticker)
    fund     = get_fundamentals(ticker)
    ratios   = get_key_ratios(ticker)
    analyst  = get_analyst_ratings(ticker)
    news     = _get_news(ticker)
    price    = _get_current_price(ticker) or analyst.get("current_price")

    logger.info("Running long-term bull/bear analysis for %s...", ticker)
    bull_case = make_long_term_bull(ticker, details, fund, ratios, analyst)
    bear_case = make_long_term_bear(ticker, details, fund, ratios, analyst)

    # Cramer checklist — quantitative (Python) + qualitative (AI)
    logger.info("Evaluating Cramer checklist for %s...", ticker)
    quant_checks = _compute_quant_checks(fund, ratios)
    ai_checks_raw = evaluate_cramer_checklist(ticker, details, fund, ratios, analyst)
    # Attach labels/categories to AI results
    ai_checks = []
    for c in ai_checks_raw:
        meta = _QUALITATIVE_META.get(c["id"], (c["id"], "quality"))
        ai_checks.append({
            "id":        c["id"],
            "label":     meta[0],
            "category":  meta[1],
            "status":    c.get("status", "unknown"),
            "rationale": c.get("rationale", ""),
        })
    cramer_checklist = quant_checks + ai_checks

    digest = {
        "ticker":             ticker,
        "name":               details.get("name", ticker),
        "sector":             details.get("sector", "Unknown"),
        "market_cap":         ratios.get("market_cap"),
        "current_price":      price,
        "analyst_consensus":  analyst.get("consensus", "unknown"),
        "analyst_target":     analyst.get("price_target"),
        "ratios":             ratios,
        "eps_quarters":       fund.get("eps_quarters", []),
        "revenue_quarters":   fund.get("revenue_qoq_quarters", []),
        "earnings_date":      fund.get("earnings_date"),
        "bull_case":          bull_case,
        "bear_case":          bear_case,
        "news":               news,
        "cramer_checklist":   cramer_checklist,
        "digested_at":        datetime.now(timezone.utc).isoformat(),
    }
    logger.info("Digest complete for %s", ticker)
    return digest


def digest_and_save(ticker: str, db) -> None:
    """
    Runs run_digest() and persists the result into the watchlist_items row.
    Updates digest_status to 'running' before starting, then 'complete'/'error'.
    Designed to be called from a background thread.
    """
    from backend.database import WatchlistItem

    ticker = ticker.upper().strip()

    # Mark as running
    item = db.query(WatchlistItem).filter(WatchlistItem.ticker == ticker).first()
    if not item:
        logger.error("WatchlistItem not found for %s", ticker)
        return

    item.digest_status = "running"
    db.commit()

    try:
        digest = run_digest(ticker)
        item.digest_status = "complete"
        item.digest_json   = json.dumps(digest)
        item.digested_at   = datetime.now(timezone.utc)
        item.name          = digest["name"]
        item.sector        = digest["sector"]
        db.commit()
        logger.info("Digest saved for %s", ticker)
    except Exception as e:
        logger.error("Digest failed for %s: %s", ticker, e)
        item.digest_status = "error"
        item.digest_json   = json.dumps({"error": str(e)})
        db.commit()
