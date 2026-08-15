import json
import math
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


CHALLENGER_MODEL_VERSION = "0.1.0-test"
CORE_FEATURES = (
    "net_epa_diff",
    "early_down_success_diff",
    "qb_epa_diff",
    "sack_rate_diff",
    "explosive_play_diff",
)
OPTIONAL_FEATURES = (
    "dvoa_diff",
    "pace_diff",
    "proe_diff",
    "drive_efficiency_sum",
    "weather_total_adjustment",
    "home_field",
    "rest_adjustment",
)


@dataclass(frozen=True)
class ChallengerConfig:
    side_a: float = 7.0
    side_b: float = 5.0
    side_c: float = 3.0
    scoring_threshold: float = 2.5


def safe_number(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def normalize_features(raw_features):
    if isinstance(raw_features, str):
        try:
            raw_features = json.loads(raw_features)
        except (TypeError, ValueError):
            raw_features = {}
    if not isinstance(raw_features, dict):
        return {}
    return {
        str(key): safe_number(value)
        for key, value in raw_features.items()
        if safe_number(value) is not None
    }


def feature_coverage(features):
    available = sum(features.get(name) is not None for name in CORE_FEATURES)
    return available, len(CORE_FEATURES)


def challenger_confidence(margin, config=None):
    config = config or ChallengerConfig()
    edge = abs(float(margin))
    if edge >= config.side_a:
        return "A"
    if edge >= config.side_b:
        return "B"
    if edge >= config.side_c:
        return "C"
    return "Pass"


def feature_factors(features, home, away):
    labels = {
        "net_epa_diff": "net EPA/play",
        "early_down_success_diff": "early-down success rate",
        "qb_epa_diff": "QB EPA/dropback",
        "sack_rate_diff": "sack-rate matchup",
        "explosive_play_diff": "explosive-play rate",
        "dvoa_diff": "weighted DVOA",
    }
    ranked = []
    for key, label in labels.items():
        value = features.get(key)
        if value is None:
            continue
        team = home if value > 0 else away
        ranked.append((abs(value), f"{label} favors {team}"))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [label for _, label in ranked[:4]]


def evaluate_challenger(row, raw_features=None, config=None):
    config = config or ChallengerConfig()
    features = normalize_features(
        raw_features if raw_features is not None else row.get("Challenger Features")
    )
    available, required = feature_coverage(features)
    base = {
        "version": CHALLENGER_MODEL_VERSION,
        "status": "Awaiting features",
        "coverage": f"{available}/{required} core features",
        "features": features,
        "factors": [],
        "model_signal": "Not Tracked",
        "side_edge": "Not Tracked",
        "predicted_winner": None,
        "confidence": "Pass",
        "model_margin": None,
        "scoring_edge": "Not Tracked",
        "projected_total": None,
        "side_result": "No Signal",
        "scoring_result": "No Signal",
    }
    if available < required:
        return base

    home = str(row.get("Home") or "Home")
    away = str(row.get("Away") or "Away")
    home_field = safe_number(features.get("home_field")) or 0.0
    rest_adjustment = safe_number(features.get("rest_adjustment")) or 0.0
    margin = (
        features["net_epa_diff"] * 20.0
        + features["early_down_success_diff"] * 25.0
        + features["qb_epa_diff"] * 10.0
        + features["sack_rate_diff"] * 15.0
        + features["explosive_play_diff"] * 20.0
        + (features.get("dvoa_diff") or 0.0) * 8.0
        + home_field
        + rest_adjustment
    )
    confidence = challenger_confidence(margin, config)
    predicted_winner = None
    if confidence != "Pass":
        predicted_winner = home if margin > 0 else away
    side_edge = (
        f"{predicted_winner} Edge" if predicted_winner else "Pass"
    )

    baseline_total = safe_number(row.get("League Total Baseline")) or 44.0
    total_adjustment = (
        (features.get("pace_diff") or 0.0) * 0.18
        + (features.get("proe_diff") or 0.0) * 8.0
        + (features.get("drive_efficiency_sum") or 0.0) * 2.0
        + (features.get("weather_total_adjustment") or 0.0)
    )
    projected_total = baseline_total + total_adjustment
    if total_adjustment >= config.scoring_threshold:
        scoring_edge = "High Scoring Environment"
    elif total_adjustment <= -config.scoring_threshold:
        scoring_edge = "Low Scoring Environment"
    else:
        scoring_edge = "Neutral Scoring Environment"

    signals = []
    if side_edge != "Pass":
        signals.append(side_edge)
    if scoring_edge != "Neutral Scoring Environment":
        signals.append(scoring_edge)

    return {
        **base,
        "status": "Tracked",
        "factors": feature_factors(features, home, away),
        "model_signal": " / ".join(signals) if signals else "Pass",
        "side_edge": side_edge,
        "predicted_winner": predicted_winner,
        "confidence": confidence,
        "model_margin": round(margin, 2),
        "scoring_edge": scoring_edge,
        "projected_total": round(projected_total, 2),
    }


def challenger_row_values(row, raw_features=None):
    result = evaluate_challenger(row, raw_features)
    return {
        "Challenger Model Version": result["version"],
        "Challenger Status": result["status"],
        "Challenger Coverage": result["coverage"],
        "Challenger Model Signal": result["model_signal"],
        "Challenger Side Edge": result["side_edge"],
        "Challenger Predicted Winner": result["predicted_winner"],
        "Challenger Confidence": result["confidence"],
        "Challenger Model Margin": result["model_margin"],
        "Challenger Scoring Edge": result["scoring_edge"],
        "Challenger Projected Total": result["projected_total"],
        "Challenger Features": result["features"],
        "Challenger Factors": result["factors"],
        "Challenger Side Result": result["side_result"],
        "Challenger Scoring Result": result["scoring_result"],
    }


def load_feature_file(path):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"NFL challenger feature file not found: {path}")
    frame = pd.read_csv(path)
    required_columns = {"game_id", *CORE_FEATURES}
    missing = sorted(required_columns - set(frame.columns))
    if missing:
        raise ValueError(
            "NFL challenger feature file is missing columns: "
            + ", ".join(missing)
        )
    return frame


def attach_features(games, feature_frame):
    feature_columns = [
        column
        for column in (*CORE_FEATURES, *OPTIONAL_FEATURES)
        if column in feature_frame.columns
    ]
    feature_map = {
        str(row["game_id"]): {
            column: safe_number(row.get(column))
            for column in feature_columns
            if safe_number(row.get(column)) is not None
        }
        for _, row in feature_frame.iterrows()
    }
    enriched = games.copy()
    enriched["challenger_features"] = enriched["game_id"].apply(
        lambda game_id: feature_map.get(str(game_id), {})
    )
    return enriched
