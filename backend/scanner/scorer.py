"""
Composite scorer — combines technical (60%) and fundamental (40%) signals,
weighted by Bayesian priors calibrated from real trade outcomes.

compute_composite_score() is the main entry point. It returns a full
breakdown dict that both the database saver and the AI debate chain consume.
"""
from backend.config import SIGNAL_WINDOWS


def get_holding_window(fired_signals: list) -> dict:
    """
    Determines recommended holding window from the signals that fired.
    Strategy: use the maximum window across all fired signals.
    Returns {"min": int, "max": int} in trading days.
    """
    if not fired_signals:
        return {"min": 5, "max": 15}  # conservative default

    valid = [s for s in fired_signals if s in SIGNAL_WINDOWS]
    if not valid:
        return {"min": 5, "max": 15}

    min_days = max(SIGNAL_WINDOWS[s]["min"] for s in valid)
    max_days = max(SIGNAL_WINDOWS[s]["max"] for s in valid)
    return {"min": min_days, "max": max_days}


def compute_composite_score(
    tech_profile: dict,
    fund_profile: dict,
    weights: dict,
) -> dict:
    """
    Computes a 0–10 composite score combining technical and fundamental signals.

    Technical component (60%):
      Each of the 4 binary signal scores is multiplied by its Bayesian weight
      (win rate from real trade outcomes). Weighted sum normalized to 0–10.

    Fundamental component (40%):
      3 binary signals, equal weight. fund_count / 3 * 10.

    Args:
      tech_profile: output of technical_profile()
      fund_profile: output of fundamental_profile()
      weights: dict from bayesian.get_weights(regime)

    Returns:
      {
        "composite":      float,        # 0–10, primary ranking score
        "tech_score":     float,        # 0–10 (weighted tech component)
        "fund_score":     float,        # 0–10 (unweighted fund component)
        "fired_signals":  list[str],    # technical signals that scored 1
        "holding_window": {"min": int, "max": int},
        "breakdown":      dict,         # per-signal detail for AI context
      }
    """
    TECH_WEIGHT = 0.60
    FUND_WEIGHT = 0.40

    signal_names  = ["uptrend", "rsi", "rs", "volume", "position_52w", "vcp"]
    fired_signals = []
    breakdown     = {}

    weighted_sum  = 0.0
    total_weight  = 0.0

    for name in signal_names:
        sig   = tech_profile.get("signals", {}).get(name, {})
        score = sig.get("score", 0) or 0
        w     = weights.get(name, 0.5)

        weighted_sum += score * w
        total_weight += w
        breakdown[name] = {"score": score, "weight": round(w, 3)}

        if score == 1:
            fired_signals.append(name)

    tech_score = (weighted_sum / total_weight * 10) if total_weight > 0 else 0.0

    # Fundamental: 3 binary signals, equal weight
    fund_count = fund_profile.get("signal_count", 0)
    fund_score = (fund_count / 3) * 10

    for name, sig in fund_profile.get("signals", {}).items():
        breakdown[f"fund_{name}"] = {"score": sig.get("score", 0), "weight": 1.0}

    composite = round(TECH_WEIGHT * tech_score + FUND_WEIGHT * fund_score, 2)

    return {
        "composite":      composite,
        "tech_score":     round(tech_score, 2),
        "fund_score":     round(fund_score, 2),
        "fired_signals":  fired_signals,
        "holding_window": get_holding_window(fired_signals),
        "breakdown":      breakdown,
    }
