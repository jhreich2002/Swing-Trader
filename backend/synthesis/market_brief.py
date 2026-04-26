"""
AI market synthesis — one Gemini call per day.

get_market_brief() returns a structured market overview:
  {"synthesis": str, "themes": list[str], "generated_at": str}

Caches to .cache/synthesis_YYYY-MM-DD.json. On second call in the same
day the result is served instantly from disk.

FastAPI startup hook calls this once so the first user request
doesn't block on a cold API call.
"""
import json
import logging
from datetime import date
from pathlib import Path

import finnhub
from google import genai
from google.genai import types

from backend.config import GOOGLE_API_KEY, FINNHUB_API_KEY
from backend.scanner.regime import detect_regime
from backend.scanner.sector_filter import get_qualified_sectors
from backend.scanner.data_client import get_market_snapshot

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache"
CACHE_DIR.mkdir(exist_ok=True)

_SYNTHESIS_SYSTEM = """\
You are a senior market strategist at a swing trading research firm. \
You write concise, actionable market briefings for professional traders.

Focus on: current regime context, sector rotation, near-term catalysts, \
and what setups are working right now. Be specific. Avoid generic disclaimers."""

_SUBMIT_TOOL_DECLARATION = {
    "name": "submit_synthesis",
    "description": "Submit the completed market synthesis briefing.",
    "parameters": {
        "type": "object",
        "properties": {
            "synthesis": {
                "type": "string",
                "description": "2-3 paragraph market synthesis for swing traders.",
            },
            "themes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "3-5 key market themes in one short phrase each.",
            },
        },
        "required": ["synthesis", "themes"],
    },
}


def _cache_path() -> Path:
    return CACHE_DIR / f"synthesis_{date.today().isoformat()}.json"


def _load_cached() -> dict | None:
    path = _cache_path()
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return None


def _save_cached(data: dict):
    _cache_path().write_text(json.dumps(data))


def _build_user_message() -> str:
    """Assembles current market context for the prompt."""
    lines = []

    try:
        regime_data = detect_regime()
        spy_df = get_market_snapshot()["spy_bars"]
        qualified = get_qualified_sectors(regime_data["regime"], spy_df)

        lines += [
            "CURRENT MARKET REGIME:",
            f"  Regime: {regime_data['regime'].upper()}",
            f"  VIX: {regime_data.get('vix', 'N/A')}",
            f"  S&P breadth (% above 200-MA): {regime_data.get('breadth_pct', 'N/A')}%",
            f"  SPY vs 20-SMA: {'above' if regime_data.get('spy_above_20sma') else 'below'}",
            f"  SPY vs 50-SMA: {'above' if regime_data.get('spy_above_50sma') else 'below'}",
            "",
            "QUALIFYING SECTORS (passing momentum filter):",
        ]
        for q in qualified:
            lines.append(f"  [{q['total']}/3] {q['sector']} ({q['etf']})")
    except Exception as e:
        logger.warning("Could not fetch regime for synthesis: %s", e)
        lines.append("(Regime data unavailable)")

    lines += ["", "RECENT MARKET HEADLINES:"]
    try:
        fh = finnhub.Client(api_key=FINNHUB_API_KEY)
        news = fh.general_news(category="general", min_id=0)[:10]
        for item in news:
            lines.append(f"  - {item.get('headline', '')}")
    except Exception as e:
        logger.warning("Could not fetch Finnhub news for synthesis: %s", e)
        lines.append("  (News unavailable)")

    lines += [
        "",
        "Based on the above, write a market synthesis for swing traders.",
        "Then submit it using the submit_synthesis function.",
    ]
    return "\n".join(lines)


def get_market_brief() -> dict:
    """
    Returns today's market brief. Cached to disk — subsequent calls are instant.
    On first call, runs a Gemini API request (~5-15s).
    """
    cached = _load_cached()
    if cached:
        logger.info("Market synthesis served from cache.")
        return cached

    logger.info("Generating market synthesis via Gemini...")

    if not GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY is not set in .env")

    client = genai.Client(api_key=GOOGLE_API_KEY)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=_build_user_message(),
        config=types.GenerateContentConfig(
            system_instruction=_SYNTHESIS_SYSTEM,
            max_output_tokens=1500,
            temperature=0.5,
            tools=[types.Tool(function_declarations=[_SUBMIT_TOOL_DECLARATION])],
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode="ANY",
                    allowed_function_names=["submit_synthesis"],
                )
            ),
        ),
    )

    result = {"synthesis": "", "themes": [], "generated_at": date.today().isoformat()}

    for part in response.candidates[0].content.parts:
        if part.function_call and part.function_call.name == "submit_synthesis":
            result["synthesis"] = part.function_call.args.get("synthesis", "")
            result["themes"]    = list(part.function_call.args.get("themes", []))
            break

    _save_cached(result)
    logger.info("Market synthesis generated and cached.")
    return result
