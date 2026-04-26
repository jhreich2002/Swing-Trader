"""
Long-term bull and bear analyst for watchlist digests.
Separate from the swing-trade debate agents — these focus on 6–18 month outlook,
business fundamentals, competitive position, and macro tailwinds/risks.
Uses Gemini 2.5 Flash via google-genai SDK.
"""
import logging

from google import genai
from google.genai import types

from backend.config import GOOGLE_API_KEY

logger = logging.getLogger(__name__)

_BULL_SYSTEM = """\
You are a long-term equity analyst making the strongest possible bull case for a stock.
Focus on a 6–18 month investment horizon.

Your analysis should cover:
- Business quality: competitive moat, pricing power, market position
- Growth drivers: revenue growth trajectory, expanding addressable market, new products/services
- Financial strength: margins trend, cash generation, balance sheet health
- Valuation: is the current price compelling relative to earnings power or growth?
- Macro tailwinds: sector trends, regulatory environment, rates/inflation impact
- Why the stock can outperform from here

Be specific, cite the data provided, and make a confident, concrete case.
2–4 paragraphs. Do not hedge excessively — your job is to make the strongest bull case."""

_BEAR_SYSTEM = """\
You are a long-term equity analyst making the strongest possible bear case for a stock.
Focus on a 6–18 month investment horizon.

Your analysis should cover:
- Business risks: competitive threats, disruption, customer concentration, pricing pressure
- Financial concerns: margins compression, debt burden, cash flow sustainability
- Valuation risk: is the stock priced for perfection? What multiple compression looks like
- Execution risks: management credibility, recent earnings misses, guidance cuts
- Macro headwinds: rate sensitivity, consumer exposure, regulatory risk
- What could go wrong and what the downside scenario looks like

Be specific, cite the data provided, and make a candid, unflinching bear case.
2–4 paragraphs. Do not soften concerns — your job is to stress-test the thesis."""

_client = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        if not GOOGLE_API_KEY:
            raise RuntimeError("GOOGLE_API_KEY is not set in .env")
        _client = genai.Client(api_key=GOOGLE_API_KEY)
    return _client


def _build_context(ticker: str, details: dict, fund: dict, ratios: dict, analyst: dict) -> str:
    def fmt(v, pct=False, x=False):
        if v is None:
            return "N/A"
        if pct:
            return f"{v * 100:.1f}%"
        if x:
            return f"{v:.1f}x"
        return f"{v:.2f}"

    def fmt_large(v):
        if v is None:
            return "N/A"
        if v >= 1e12:
            return f"${v/1e12:.2f}T"
        if v >= 1e9:
            return f"${v/1e9:.2f}B"
        if v >= 1e6:
            return f"${v/1e6:.2f}M"
        return f"${v:,.0f}"

    # EPS trend
    eps_qs = fund.get("eps_quarters", [])
    eps_str = "N/A"
    if eps_qs:
        eps_str = "  |  ".join(
            f"{q.get('period','?')}: ${q.get('epsActual', 0):.2f}"
            for q in eps_qs[:6]
        )

    # Revenue trend (quarterly, in $B)
    rev_qs = fund.get("revenue_qoq_quarters", [])
    rev_str = "N/A"
    if rev_qs:
        rev_str = "  |  ".join(f"${v/1e9:.2f}B" for v in rev_qs[:6])

    lines = [
        f"COMPANY:  {details.get('name', ticker)} ({ticker})",
        f"SECTOR:   {details.get('sector', 'Unknown')}",
        f"MARKET CAP: {fmt_large(ratios.get('market_cap'))}",
        f"ENTERPRISE VALUE: {fmt_large(ratios.get('enterprise_value'))}",
        f"CURRENT PRICE: ${analyst.get('current_price') or 'N/A'}",
        f"52-WEEK RANGE: ${fmt(ratios.get('week52_low'))} – ${fmt(ratios.get('week52_high'))}",
        f"ANALYST CONSENSUS: {analyst.get('consensus', 'unknown').upper()}",
        f"ANALYST PRICE TARGET: ${fmt(analyst.get('price_target'))}",
        "",
        "VALUATION:",
        f"  P/E (trailing): {fmt(ratios.get('pe_trailing'), x=True)}",
        f"  P/E (forward):  {fmt(ratios.get('pe_forward'), x=True)}",
        f"  P/S:            {fmt(ratios.get('ps_ratio'), x=True)}",
        f"  P/B:            {fmt(ratios.get('pb_ratio'), x=True)}",
        f"  EV/EBITDA:      {fmt(ratios.get('ev_ebitda'), x=True)}",
        f"  Beta:           {fmt(ratios.get('beta'))}",
        f"  Dividend Yield: {fmt(ratios.get('dividend_yield'), pct=True)}",
        "",
        "FINANCIAL HEALTH:",
        f"  Gross Margin:      {fmt(ratios.get('gross_margin'), pct=True)}",
        f"  Operating Margin:  {fmt(ratios.get('operating_margin'), pct=True)}",
        f"  Net Margin:        {fmt(ratios.get('net_margin'), pct=True)}",
        f"  ROE:               {fmt(ratios.get('roe'), pct=True)}",
        f"  ROA:               {fmt(ratios.get('roa'), pct=True)}",
        f"  Debt/Equity:       {fmt(ratios.get('debt_to_equity'), x=True)}",
        f"  Current Ratio:     {fmt(ratios.get('current_ratio'), x=True)}",
        f"  Free Cash Flow:    {fmt_large(ratios.get('free_cashflow'))}",
        f"  Total Debt:        {fmt_large(ratios.get('total_debt'))}",
        "",
        "GROWTH:",
        f"  Revenue Growth (YoY):  {fmt(ratios.get('revenue_growth'), pct=True)}",
        f"  Earnings Growth (YoY): {fmt(ratios.get('earnings_growth'), pct=True)}",
        "",
        f"EPS (quarterly, most recent first):\n  {eps_str}",
        "",
        f"REVENUE (quarterly $B, most recent first):\n  {rev_str}",
    ]

    ed = fund.get("earnings_date")
    if ed:
        lines.append(f"\nNEXT EARNINGS DATE: {ed}")

    return "\n".join(lines)


_CHECKLIST_SYSTEM = """\
You are a rigorous equity analyst evaluating a stock against Jim Cramer's pre-buy checklist.
For each criterion, return: 'pass', 'fail', 'partial', or 'unknown'.
Base your assessment on the financial data provided. Be honest and conservative —
a 'pass' should mean genuinely clear, not just marginally okay.
Keep each rationale to one concise sentence."""

_CHECKLIST_ITEMS = [
    {
        "id": "business_clarity",
        "question": "Is the business model simple enough to explain in plain English, with a clear and understandable way of making money?",
    },
    {
        "id": "secular_growth",
        "question": "Is the company's revenue and earnings growth secular (persists across economic cycles), not just a one-off cyclical upswing?",
    },
    {
        "id": "growth_runway",
        "question": "Does the company have a visible runway to scale — large addressable market, room for product expansion, or geographic growth?",
    },
    {
        "id": "competitive_moat",
        "question": "Does the company have a clear competitive edge (brand, network effect, technology, cost structure, or regulatory moat) that explains why its growth and margins are sustainable?",
    },
    {
        "id": "management_quality",
        "question": "Is management trustworthy — do they have a track record of execution, realistic guidance, and honest communication?",
    },
    {
        "id": "disruption_risk",
        "question": "Is the company safe from obvious disruption or obsolescence risk — no clear technology disruption threat or fad-driven demand?",
    },
    {
        "id": "concentration_risk",
        "question": "Is the company NOT dangerously over-reliant on a single customer, product line, or volatile commodity?",
    },
]

_SUBMIT_CHECKLIST_DECLARATION = {
    "name": "submit_checklist",
    "description": "Submit the Cramer pre-buy checklist evaluation for all 7 qualitative criteria.",
    "parameters": {
        "type": "object",
        "properties": {
            "checks": {
                "type": "array",
                "description": "Evaluation for each checklist item.",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "Criterion ID (exactly as given in the prompt).",
                        },
                        "status": {
                            "type": "string",
                            "enum": ["pass", "fail", "partial", "unknown"],
                            "description": "pass=clearly meets the bar, fail=clearly does not, partial=mixed/borderline, unknown=insufficient data.",
                        },
                        "rationale": {
                            "type": "string",
                            "description": "One concise sentence explaining the assessment.",
                        },
                    },
                    "required": ["id", "status", "rationale"],
                },
            }
        },
        "required": ["checks"],
    },
}


def evaluate_cramer_checklist(
    ticker: str,
    details: dict,
    fund: dict,
    ratios: dict,
    analyst: dict,
) -> list[dict]:
    """
    Evaluates 7 qualitative Cramer checklist criteria via a single Gemini function-calling call.
    Returns list of {id, status, rationale} dicts — one per qualitative criterion.
    Falls back to 'unknown' for each item if the API call fails.
    """
    ctx = _build_context(ticker, details, fund, ratios, analyst)
    questions = "\n".join(
        f'{i+1}. [{item["id"]}] {item["question"]}'
        for i, item in enumerate(_CHECKLIST_ITEMS)
    )
    prompt = (
        f"{ctx}\n\n"
        f"Evaluate each of the following criteria for {ticker}:\n\n"
        f"{questions}\n\n"
        "Call submit_checklist with your assessments for all 7 criteria."
    )

    client = _get_client()
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=_CHECKLIST_SYSTEM,
                max_output_tokens=2000,
                temperature=0.2,
                tools=[types.Tool(function_declarations=[_SUBMIT_CHECKLIST_DECLARATION])],
                tool_config=types.ToolConfig(
                    function_calling_config=types.FunctionCallingConfig(
                        mode="ANY",
                        allowed_function_names=["submit_checklist"],
                    )
                ),
            ),
        )
        for part in response.candidates[0].content.parts:
            if part.function_call and part.function_call.name == "submit_checklist":
                checks = list(part.function_call.args.get("checks", []))
                # Ensure all expected IDs are present
                found_ids = {c["id"] for c in checks}
                for item in _CHECKLIST_ITEMS:
                    if item["id"] not in found_ids:
                        checks.append({"id": item["id"], "status": "unknown", "rationale": "Not evaluated."})
                return checks
    except Exception as e:
        logger.error("Cramer checklist evaluation failed for %s: %s", ticker, e)

    # Fallback
    return [{"id": item["id"], "status": "unknown", "rationale": "AI evaluation unavailable."} for item in _CHECKLIST_ITEMS]


def make_long_term_bull(ticker: str, details: dict, fund: dict, ratios: dict, analyst: dict) -> str:
    ctx = _build_context(ticker, details, fund, ratios, analyst)
    client = _get_client()
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=ctx,
            config=types.GenerateContentConfig(
                system_instruction=_BULL_SYSTEM,
                max_output_tokens=1800,
                temperature=0.7,
            ),
        )
        return response.text.strip()
    except Exception as e:
        logger.error("Bull analyst failed for %s: %s", ticker, e)
        return "Bull analysis unavailable."


def make_long_term_bear(ticker: str, details: dict, fund: dict, ratios: dict, analyst: dict) -> str:
    ctx = _build_context(ticker, details, fund, ratios, analyst)
    client = _get_client()
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=ctx,
            config=types.GenerateContentConfig(
                system_instruction=_BEAR_SYSTEM,
                max_output_tokens=1800,
                temperature=0.7,
            ),
        )
        return response.text.strip()
    except Exception as e:
        logger.error("Bear analyst failed for %s: %s", ticker, e)
        return "Bear analysis unavailable."
