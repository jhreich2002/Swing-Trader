"""
Portfolio concentration agent.

Reviews the full set of included recommendations and flags sector
over-concentration. This is NOT a scored signal — it runs after the
debate chain as a post-processing advisory step.

The note is stored on each Recommendation.portfolio_note column and
surfaced through the API.
"""
import logging

from google import genai
from google.genai import types

from backend.config import GOOGLE_API_KEY

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=GOOGLE_API_KEY)
    return _client


_SYSTEM = (
    "You are a portfolio risk manager reviewing a list of proposed swing trades. "
    "Your only job is to flag sector concentration risk in plain English. "
    "Be direct and specific — name the sectors that are over-represented and suggest "
    "a maximum. Do not rate individual stocks. Keep your response under 3 sentences."
)


def review(recommendations: list[dict]) -> str:
    """
    Analyzes sector concentration across included recommendations.

    Args:
        recommendations: list of dicts with keys: ticker, sector, conviction_score

    Returns:
        Plain-English concentration note string, or empty string on error.
    """
    if not recommendations:
        return ""

    # Build sector summary
    from collections import Counter
    sectors = [r.get("sector", "Unknown") for r in recommendations]
    counts  = Counter(sectors)
    total   = len(recommendations)

    sector_lines = "\n".join(
        f"  {sector}: {count} picks ({count/total*100:.0f}%)"
        for sector, count in counts.most_common()
    )

    ticker_lines = "\n".join(
        f"  {r['ticker']} ({r.get('sector', 'Unknown')}) — conviction {r.get('conviction_score', 0):.0f}/10"
        for r in recommendations
    )

    prompt = (
        f"Proposed trades ({total} total):\n{ticker_lines}\n\n"
        f"Sector breakdown:\n{sector_lines}\n\n"
        "Flag any concentration risk and suggest adjustments if needed."
    )

    try:
        client   = _get_client()
        response = client.models.generate_content(
            model    = "gemini-2.5-flash",
            contents = prompt,
            config   = types.GenerateContentConfig(
                system_instruction = _SYSTEM,
                max_output_tokens  = 300,
                temperature        = 0.4,
            ),
        )
        return response.text.strip()
    except Exception as e:
        logger.error("Portfolio agent failed: %s", e)
        return ""
