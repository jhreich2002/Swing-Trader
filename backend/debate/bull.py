"""
Bull analyst agent.
Constructs the strongest possible buy case for a swing trade candidate.
Uses Gemini 2.0 Flash.
"""
import logging

from google import genai
from google.genai import types

from backend.config import GOOGLE_API_KEY

logger = logging.getLogger(__name__)

_BULL_SYSTEM = """\
You are a bullish swing trading analyst. You specialize in identifying \
high-probability short-to-medium-term trade setups in the S&P 500.

Given a stock's technical and fundamental profile, construct the strongest \
possible bull case for entering this trade right now.

Focus on:
- Which technical signals fired and WHY they matter in this specific regime
- Signal confluence — multiple confirming signals reinforce each other
- Sector momentum and how the regime aligns with the setup
- Fundamental support or tailwinds that validate the technicals
- Realistic upside target range and time horizon

Be concrete and data-driven. Reference the exact signal values provided. \
2–3 paragraphs maximum. Do not hedge excessively — your role is to make the \
strongest possible bull case, not to be balanced."""

_client = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        if not GOOGLE_API_KEY:
            raise RuntimeError("GOOGLE_API_KEY is not set in .env")
        _client = genai.Client(api_key=GOOGLE_API_KEY)
    return _client


def make_bull_argument(
    ticker: str,
    tech_profile: dict,
    fund_profile: dict,
    composite_score: dict,
    regime: str,
) -> str:
    """
    Returns the bull argument as a plain text string.
    Raises on API failure (caller handles gracefully).
    """
    user_content = _build_context(ticker, tech_profile, fund_profile, composite_score, regime)

    client = _get_client()
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=user_content,
        config=types.GenerateContentConfig(
            system_instruction=_BULL_SYSTEM,
            max_output_tokens=1500,
            temperature=0.7,
        ),
    )
    return response.text.strip()


def _build_context(ticker, tech_profile, fund_profile, composite_score, regime) -> str:
    lines = [
        f"CANDIDATE: {ticker}",
        f"SECTOR:    {tech_profile.get('sector', 'Unknown')}",
        f"REGIME:    {regime.upper()}",
        f"COMPOSITE SCORE: {composite_score['composite']}/10  "
        f"(tech {composite_score['tech_score']}/10 | fundamental {composite_score['fund_score']}/10)",
        f"SIGNALS FIRED: {len(composite_score['fired_signals'])}/7 technical, "
        f"{fund_profile.get('signal_count', 0)}/4 fundamental",
        f"RECOMMENDED HOLDING WINDOW: "
        f"{composite_score['holding_window']['min']}–{composite_score['holding_window']['max']} trading days",
        "",
        "TECHNICAL SIGNALS:",
    ]
    for name, sig in tech_profile.get("signals", {}).items():
        flag = "[FIRED]" if sig.get("score") else "[  --  ]"
        w = composite_score.get("breakdown", {}).get(name, {}).get("weight", "?")
        lines.append(f"  {flag} {name.upper():<12} (weight={w})  {sig.get('detail', 'N/A')}")

    lines.extend(["", "FUNDAMENTAL SIGNALS:"])
    for name, sig in fund_profile.get("signals", {}).items():
        flag = "[FIRED]" if sig.get("score") else "[  --  ]"
        lines.append(f"  {flag} {name.upper():<12}  {sig.get('detail', 'N/A')}")

    return "\n".join(lines)
