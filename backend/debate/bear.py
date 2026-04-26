"""
Bear analyst agent.
Constructs the strongest possible bear case against a swing trade candidate.
Uses Gemini 2.0 Flash.
"""
import logging

from google import genai
from google.genai import types

from backend.config import GOOGLE_API_KEY

logger = logging.getLogger(__name__)

_BEAR_SYSTEM = """\
You are a risk manager and skeptical analyst at a swing trading desk. \
Your job is to stress-test every trade idea before capital is committed.

Given a stock's technical and fundamental profile, construct the strongest \
possible bear case AGAINST entering this trade right now.

Focus on:
- Signal weaknesses — which signals didn't fire and why that matters
- Timing risks — is this a late entry, a false breakout, or an exhausted move?
- Regime misalignment — does the market environment work against this setup?
- Fundamental red flags — valuation concerns, weak earnings, analyst skepticism
- Worst-case scenario — if this trade goes wrong, how wrong can it go?
- Stop-loss risk — is the natural stop too wide or the reward-to-risk unfavorable?

Be direct and specific. Reference the exact signal values provided. \
2–3 paragraphs maximum. Do not soften the bear case — your role is adversarial."""

_client = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        if not GOOGLE_API_KEY:
            raise RuntimeError("GOOGLE_API_KEY is not set in .env")
        _client = genai.Client(api_key=GOOGLE_API_KEY)
    return _client


def make_bear_argument(
    ticker: str,
    tech_profile: dict,
    fund_profile: dict,
    composite_score: dict,
    regime: str,
) -> str:
    """
    Returns the bear argument as a plain text string.
    Raises on API failure (caller handles gracefully).
    """
    user_content = _build_context(ticker, tech_profile, fund_profile, composite_score, regime)

    client = _get_client()
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=user_content,
        config=types.GenerateContentConfig(
            system_instruction=_BEAR_SYSTEM,
            max_output_tokens=1500,
            temperature=0.7,
        ),
    )
    return response.text.strip()


def _build_context(ticker, tech_profile, fund_profile, composite_score, regime) -> str:
    not_fired = [
        name for name, sig in tech_profile.get("signals", {}).items()
        if not sig.get("score")
    ]
    fund_not_fired = [
        name for name, sig in fund_profile.get("signals", {}).items()
        if not sig.get("score")
    ]

    lines = [
        f"CANDIDATE: {ticker}",
        f"SECTOR:    {tech_profile.get('sector', 'Unknown')}",
        f"REGIME:    {regime.upper()}",
        f"COMPOSITE SCORE: {composite_score['composite']}/10  "
        f"(tech {composite_score['tech_score']}/10 | fundamental {composite_score['fund_score']}/10)",
        f"SIGNALS FIRED: {len(composite_score['fired_signals'])}/7 technical, "
        f"{fund_profile.get('signal_count', 0)}/4 fundamental",
        f"SIGNALS NOT FIRED (technical): {', '.join(not_fired) if not_fired else 'none'}",
        f"SIGNALS NOT FIRED (fundamental): {', '.join(fund_not_fired) if fund_not_fired else 'none'}",
        f"RECOMMENDED HOLDING WINDOW: "
        f"{composite_score['holding_window']['min']}–{composite_score['holding_window']['max']} trading days",
        "",
        "ALL TECHNICAL SIGNALS (fired and unfired):",
    ]
    for name, sig in tech_profile.get("signals", {}).items():
        flag = "[FIRED]" if sig.get("score") else "[FAILED]"
        w = composite_score.get("breakdown", {}).get(name, {}).get("weight", "?")
        lines.append(f"  {flag} {name.upper():<12} (backtest weight={w})  {sig.get('detail', 'N/A')}")

    lines.extend(["", "ALL FUNDAMENTAL SIGNALS:"])
    for name, sig in fund_profile.get("signals", {}).items():
        flag = "[FIRED]" if sig.get("score") else "[FAILED]"
        lines.append(f"  {flag} {name.upper():<12}  {sig.get('detail', 'N/A')}")

    return "\n".join(lines)
