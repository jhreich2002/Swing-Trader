"""
Arbiter agent — synthesizes the bull and bear arguments and renders a final verdict.

Uses Gemini 2.0 Flash with function calling so the verdict fields are
machine-readable (conviction score, entry levels, etc.).
The arbiter is the only AI call that writes to the recommendations table.
"""
import json
import logging

from google import genai
from google.genai import types

from backend.config import GOOGLE_API_KEY

logger = logging.getLogger(__name__)

_ARBITER_SYSTEM = """\
You are the head of a swing trading research desk. You receive a bull and bear \
case written by two analysts for the same trade candidate, along with the \
underlying data both arguments were drawn from.

Your job:
1. Weigh both arguments rigorously. Neither analyst is biased toward you approving \
   or rejecting — they were instructed to make the strongest possible one-sided case.
2. Identify which argument is better supported by the data.
3. Render a final verdict using the submit_verdict function.

Criteria for INCLUSION (include=true):
- Bull case is clearly stronger AND well-supported by the data
- At least 3 technical signals fired OR composite score >= 5.0
- Market regime does not strongly contradict the setup
- Risk/reward is reasonable (natural stop not too wide)
- Conviction score >= 6 out of 10

Criteria for EXCLUSION (include=false):
- Bear case raises fatal flaws not rebutted by the bull case
- Setup is weak (< 3 signals, composite < 4.0)
- Regime misalignment is severe
- Late entry with limited remaining upside

For stop loss: recommend 1.5x ATR below entry as default. If you don't have ATR, \
use 5–7% below current price as a rough guide.

Be rigorous. Reject marginal setups. The user trusts these recommendations \
to represent high-conviction ideas only. 3–5 final picks per week is the goal."""

_SUBMIT_VERDICT_DECLARATION = {
    "name": "submit_verdict",
    "description": (
        "Record the final verdict on a swing trade candidate. "
        "Call this once you have weighed the bull and bear arguments."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "include": {
                "type": "boolean",
                "description": "True to include in final recommendations, False to skip.",
            },
            "conviction_score": {
                "type": "number",
                "description": (
                    "Conviction score 1–10. Only meaningful if include=true. "
                    "7+ = high conviction, 5–6 = borderline, < 5 = should be excluded."
                ),
            },
            "arbiter_summary": {
                "type": "string",
                "description": (
                    "2–3 paragraph synthesis: key reasons for the verdict, "
                    "what the bull got right, what the bear got right, and final reasoning."
                ),
            },
            "entry_rationale": {
                "type": "string",
                "description": "One sentence: why enter now specifically.",
            },
            "stop_loss_pct": {
                "type": "number",
                "description": (
                    "Suggested stop loss as % below current price. "
                    "E.g. 5.0 means stop at 5% below entry. Default 5–7%."
                ),
            },
            "holding_window_days": {
                "type": "integer",
                "description": (
                    "Recommended holding window in trading days. "
                    "Should fall within the signal-derived window range provided."
                ),
            },
            "skip_reason": {
                "type": "string",
                "description": "If include=false, brief reason for skipping (1–2 sentences).",
            },
        },
        "required": ["include", "conviction_score", "arbiter_summary"],
    },
}

_client = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        if not GOOGLE_API_KEY:
            raise RuntimeError("GOOGLE_API_KEY is not set in .env")
        _client = genai.Client(api_key=GOOGLE_API_KEY)
    return _client


def arbitrate(
    ticker: str,
    bull_arg: str,
    bear_arg: str,
    tech_profile: dict,
    fund_profile: dict,
    composite_score: dict,
) -> dict:
    """
    Synthesizes the bull and bear arguments and returns a structured verdict dict.

    Returns:
      {
        "include":            bool,
        "conviction_score":   float,
        "arbiter_summary":    str,
        "entry_rationale":    str,
        "stop_loss_pct":      float,
        "holding_window_days":int,
        "skip_reason":        str,
      }
    """
    user_content = _build_context(ticker, bull_arg, bear_arg, tech_profile, fund_profile, composite_score)

    client = _get_client()
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=user_content,
        config=types.GenerateContentConfig(
            system_instruction=_ARBITER_SYSTEM,
            max_output_tokens=3000,
            temperature=0.3,
            tools=[types.Tool(function_declarations=[_SUBMIT_VERDICT_DECLARATION])],
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode="ANY",
                    allowed_function_names=["submit_verdict"],
                )
            ),
        ),
    )

    # Extract the function call block
    for part in response.candidates[0].content.parts:
        if part.function_call and part.function_call.name == "submit_verdict":
            verdict = dict(part.function_call.args)
            verdict.setdefault("entry_rationale", "")
            verdict.setdefault("stop_loss_pct", 6.0)
            window = composite_score.get("holding_window", {})
            verdict.setdefault("holding_window_days", window.get("max", 10))
            verdict.setdefault("skip_reason", "")
            return verdict

    logger.error("Arbiter did not call submit_verdict for %s — defaulting to skip", ticker)
    return {
        "include":             False,
        "conviction_score":    0,
        "arbiter_summary":     "Arbiter failed to render a verdict.",
        "entry_rationale":     "",
        "stop_loss_pct":       6.0,
        "holding_window_days": 10,
        "skip_reason":         "Arbiter API error — no verdict returned.",
    }


def _build_context(ticker, bull_arg, bear_arg, tech_profile, fund_profile, composite_score) -> str:
    window = composite_score.get("holding_window", {})
    lines = [
        f"CANDIDATE: {ticker}",
        f"SECTOR:    {tech_profile.get('sector', 'Unknown')}",
        f"REGIME:    {tech_profile.get('regime', 'unknown').upper()}",
        f"COMPOSITE SCORE: {composite_score['composite']}/10  "
        f"(tech {composite_score['tech_score']}/10 | fundamental {composite_score['fund_score']}/10)",
        f"SIGNALS FIRED: {len(composite_score['fired_signals'])}/7 technical, "
        f"{fund_profile.get('signal_count', 0)}/4 fundamental",
        f"SIGNAL-DERIVED HOLDING WINDOW: {window.get('min', 5)}–{window.get('max', 10)} trading days",
        "",
        "--- BULL ARGUMENT ---",
        bull_arg,
        "",
        "--- BEAR ARGUMENT ---",
        bear_arg,
        "",
        "--- UNDERLYING DATA (for verification) ---",
        "Technical signals:",
    ]
    for name, sig in tech_profile.get("signals", {}).items():
        flag = "FIRED" if sig.get("score") else "  -- "
        lines.append(f"  [{flag}] {name.upper():<12}  {sig.get('detail', 'N/A')}")

    lines.append("Fundamental signals:")
    for name, sig in fund_profile.get("signals", {}).items():
        flag = "FIRED" if sig.get("score") else "  -- "
        lines.append(f"  [{flag}] {name.upper():<12}  {sig.get('detail', 'N/A')}")

    return "\n".join(lines)
