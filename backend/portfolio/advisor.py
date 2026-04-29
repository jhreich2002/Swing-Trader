"""
Portfolio AI advisor — uses Gemini to suggest buy/sell/hold actions for the
Roth IRA, Passive, and Total portfolios. Mirrors the arbiter pattern (function
calling for structured output).
"""
import json
import logging
from typing import Optional

from google import genai
from google.genai import types

from backend.config import GOOGLE_API_KEY
from backend.debate.arbiter import _get_client  # reuse the same singleton client

logger = logging.getLogger(__name__)


_INDEX_TICKERS = {"SPY","VOO","IVV","VTI","QQQ","SCHB","SCHX","VEA","VXUS","IEFA","EFA","ITOT","SPLG"}
_GOLD_BOND_TICKERS = {"GLD","IAU","SGOL","TLT","IEF","AGG","BND","LQD","SHY","GOVT","BNDX","TIP"}


def classify_bucket(ticker: str) -> str:
    t = (ticker or "").upper()
    if t in _INDEX_TICKERS:
        return "index"
    if t in _GOLD_BOND_TICKERS:
        return "gold_bonds"
    return "long_term_hold"


# ---------------------------------------------------------------------------
# Function-calling schema — every advisor response must conform.
# ---------------------------------------------------------------------------
_SUBMIT_RECOMMENDATIONS = {
    "name": "submit_recommendations",
    "description": "Returns a structured summary plus an ordered list of suggested actions.",
    "parameters": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "2-4 sentence plain-English assessment of the portfolio and the most important next move.",
            },
            "actions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "action":    {"type": "string", "enum": ["buy", "sell", "hold", "trim", "add"]},
                        "ticker":    {"type": "string"},
                        "rationale": {"type": "string"},
                        "suggested_pct_of_portfolio": {
                            "type": "number",
                            "description": "Target weight % of this position in the portfolio after the action.",
                        },
                    },
                    "required": ["action", "ticker", "rationale"],
                },
            },
        },
        "required": ["summary", "actions"],
    },
}


_ROTH_SYSTEM = """\
You are a personal portfolio advisor for a Roth IRA. The investor's strategy is:
  • 50% broad index funds (e.g. SPY, VOO, VTI, QQQ)
  • 10% gold + bonds for downside protection (e.g. GLD, TLT, AGG)
  • 40% across approximately 5 long-term, high-conviction buy-and-hold positions
Your goal is multi-decade wealth compounding inside a tax-advantaged account.

Given the user's current Roth holdings and target buckets, recommend specific buy/sell/trim/add/hold
actions to converge toward the targets. Be conservative — favor index ETFs over individual stocks
when the user is below the 50% index target. Suggest no more than 6 actions per call.
Always call submit_recommendations with your verdict.
"""


_PASSIVE_SYSTEM = """\
You are a personal portfolio advisor for a long-term passive investing account that holds the
majority of the user's wealth. The strategy is:
  • Broad index funds and long-term hold positions only
  • Minimize trading; this is NOT a swing-trading account
  • Diversification, low fees, tax efficiency
  • Flag any single position above 20% of the portfolio as a concentration risk

Recommend buy/sell/trim/add/hold actions that move the portfolio toward a diversified, low-cost,
long-term posture. Suggest no more than 6 actions per call.
Always call submit_recommendations with your verdict.
"""


_TOTAL_SYSTEM = """\
You are the senior portfolio manager overseeing the user's three accounts:
  • Active swing-trading book
  • Roth IRA (long-term tax-advantaged)
  • Passive (bulk of net worth, long-term ETFs)

Given the aggregated view across all three, identify cross-portfolio rebalances. Examples:
  • "You're overweight tech across the Active and Roth — trim NVDA in Active first (highest tax cost)"
  • "Cash is 35% of grand total — deploy into the Passive index sleeve"
  • "Sector concentration in Technology exceeds 50% — add an Industrials or Healthcare ETF"

Suggest no more than 6 actions, each tagged with the ticker. Be specific about WHICH portfolio to
trade in (mention it in the rationale). Always call submit_recommendations with your verdict.
"""


def _call_gemini(system_prompt: str, user_payload: dict) -> dict:
    client = _get_client()
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=json.dumps(user_payload, default=str),
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            max_output_tokens=3000,
            temperature=0.4,
            tools=[types.Tool(function_declarations=[_SUBMIT_RECOMMENDATIONS])],
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode="ANY",
                    allowed_function_names=["submit_recommendations"],
                )
            ),
        ),
    )

    for part in response.candidates[0].content.parts:
        if part.function_call and part.function_call.name == "submit_recommendations":
            data = dict(part.function_call.args)
            actions_raw = data.get("actions") or []
            data["actions"] = [dict(a) for a in actions_raw]
            data.setdefault("summary", "")
            return data
    return {"summary": "Advisor returned no structured response.", "actions": []}


def _roth_payload(actual: dict) -> dict:
    """Extract just what the model needs for Roth advice."""
    by_bucket = {"index": 0.0, "gold_bonds": 0.0, "long_term_hold": 0.0}
    holdings = []
    grand = actual["total_market_value"] or 1
    for p in actual["positions"]:
        b = p.get("bucket") or classify_bucket(p["ticker"])
        by_bucket[b] = by_bucket.get(b, 0.0) + (p["market_value"] or 0.0)
        holdings.append({
            "ticker":     p["ticker"],
            "shares":     p["shares"],
            "market_value": p["market_value"],
            "weight_pct": p["weight_pct"],
            "bucket":     b,
            "pnl_pct":    p.get("pnl_pct"),
        })
    bucket_pct = {k: round(v / grand * 100, 2) for k, v in by_bucket.items()}
    return {
        "cash":              actual["cash"],
        "cash_weight_pct":   actual["cash_weight_pct"],
        "total_market_value": actual["total_market_value"],
        "current_bucket_weights_pct": bucket_pct,
        "target_bucket_weights_pct":  {"index": 50, "gold_bonds": 10, "long_term_hold": 40},
        "long_term_hold_count":  sum(1 for p in actual["positions"] if (p.get("bucket") or classify_bucket(p["ticker"])) == "long_term_hold"),
        "long_term_hold_target_count": 5,
        "holdings":          holdings,
    }


def _passive_payload(actual: dict) -> dict:
    holdings = []
    for p in actual["positions"]:
        holdings.append({
            "ticker":     p["ticker"],
            "shares":     p["shares"],
            "market_value": p["market_value"],
            "weight_pct": p["weight_pct"],
            "kind":       classify_bucket(p["ticker"]),
            "pnl_pct":    p.get("pnl_pct"),
        })
    holdings.sort(key=lambda x: -(x.get("weight_pct") or 0))
    return {
        "cash":              actual["cash"],
        "cash_weight_pct":   actual["cash_weight_pct"],
        "total_market_value": actual["total_market_value"],
        "return_pct":        actual["return_pct"],
        "holdings":          holdings,
        "top_position_weight_pct": holdings[0]["weight_pct"] if holdings else 0.0,
    }


def _total_payload(total: dict) -> dict:
    return {
        "portfolios":               total["portfolios"],
        "grand_total_market_value": total["grand_total_market_value"],
        "grand_return_pct":         total["grand_return_pct"],
        "asset_class_exposure":     total["asset_class_exposure"],
        "sector_exposure":          total["sector_exposure"][:8],
        "top_combined_positions":   total["combined_positions"][:10],
        "concentration":            total["concentration"],
    }


def generate_for_portfolio(portfolio_type: str, payload: dict) -> dict:
    """
    Dispatch to the correct system prompt + payload shaper. Returns
    {summary: str, actions: [{action, ticker, rationale, suggested_pct_of_portfolio}]}.
    """
    if not GOOGLE_API_KEY:
        return {
            "summary": "GOOGLE_API_KEY is not configured on the backend; cannot generate AI recommendations.",
            "actions": [],
        }
    try:
        if portfolio_type == "roth_ira":
            return _call_gemini(_ROTH_SYSTEM, _roth_payload(payload))
        if portfolio_type == "passive":
            return _call_gemini(_PASSIVE_SYSTEM, _passive_payload(payload))
        if portfolio_type == "total":
            return _call_gemini(_TOTAL_SYSTEM, _total_payload(payload))
        # active portfolio: not supported here (it has its own scanner-driven recs)
        return {
            "summary": f"AI recommendations are not implemented for portfolio_type={portfolio_type}.",
            "actions": [],
        }
    except Exception as e:
        logger.exception("advisor failed for %s", portfolio_type)
        return {
            "summary": f"Advisor error: {e}",
            "actions": [],
        }
