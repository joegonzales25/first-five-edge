"""Pregame challenger inputs from recent nflverse regular-season plays."""

from datetime import datetime, timezone
from io import BytesIO

import pandas as pd
import requests

from nfl_agent import parse_schedule_kickoff
from nfl_backtest import ModelConfig
from nfl_challenger import CORE_FEATURES, safe_number

FEATURE_VERSION = "0.2.0-pbp"
FEATURE_SOURCE = "nflverse-pbp-last5-v1"
PBP_URL = "https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{season}.csv.gz"
COLUMNS = (
    "game_id", "play_id", "season", "season_type", "posteam", "defteam",
    "play_type", "down", "epa", "qb_epa", "qb_dropback", "sack",
    "yards_gained", "pass_attempt", "rush_attempt", "qb_kneel", "qb_spike",
)
ALIASES = {"LAR": "LA", "WSH": "WAS"}


def load_play_by_play(season):
    response = requests.get(PBP_URL.format(season=int(season)), timeout=60)
    response.raise_for_status()
    frame = pd.read_csv(BytesIO(response.content), compression="gzip", usecols=lambda column: column in COLUMNS, low_memory=False)
    missing = set(COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"NFL play-by-play missing columns: {sorted(missing)}")
    if not frame.empty and not frame["season"].eq(int(season)).all():
        raise ValueError("NFL play-by-play returned a different season")
    if frame.duplicated(["game_id", "play_id"]).any():
        raise ValueError("NFL play-by-play has duplicate plays")
    return frame


def valid_plays(pbp):
    missing = set(COLUMNS) - set(pbp.columns)
    if missing:
        raise ValueError(f"NFL play-by-play missing columns: {sorted(missing)}")
    result = pbp.copy()
    for column in COLUMNS:
        if column not in {"game_id", "season_type", "posteam", "defteam", "play_type"}:
            result[column] = pd.to_numeric(result[column], errors="coerce").replace([float("inf"), float("-inf")], float("nan"))
    result["posteam"] = result["posteam"].replace(ALIASES)
    result["defteam"] = result["defteam"].replace(ALIASES)
    result = result[
        result["season_type"].eq("REG") & result["play_type"].isin(["pass", "run"])
        & result["qb_kneel"].eq(0) & result["qb_spike"].eq(0)
        & result["posteam"].notna() & result["defteam"].notna()
    ].copy()
    result["explosive"] = (
        (result["pass_attempt"].eq(1) & result["yards_gained"].ge(20))
        | (result["rush_attempt"].eq(1) & result["yards_gained"].ge(10))
    ).astype(float).where(
        result["yards_gained"].notna()
        & (result["pass_attempt"].eq(1) | result["rush_attempt"].eq(1))
    )
    return result


def mean_with_sample(values, minimum):
    values = values.dropna()
    return float(values.mean()) if len(values) >= minimum else None


def team_profile(plays, history, team):
    recent = history[(history.away_team == team) | (history.home_team == team)].tail(5)
    ids = set(recent["game_id"].astype(str))
    sample = plays[plays.game_id.astype(str).isin(ids)]
    own = sample[sample.posteam == team]
    opponent = sample[sample.defteam == team]
    # Both offense and defense must cover at least two completed games.
    if own.game_id.nunique() < 2 or opponent.game_id.nunique() < 2:
        return {}
    offense_epa = mean_with_sample(own.epa, 60)
    defense_epa = mean_with_sample(opponent.epa, 60)
    early_offense = mean_with_sample(own.loc[own.down.isin([1, 2]), "epa"].dropna().gt(0).astype(float), 40)
    early_defense = mean_with_sample(opponent.loc[opponent.down.isin([1, 2]), "epa"].dropna().gt(0).astype(float), 40)
    dropbacks = own[own.qb_dropback == 1]
    defensive_dropbacks = opponent[opponent.qb_dropback == 1]
    difference = lambda a, b: a - b if a is not None and b is not None else None
    return {
        "net_epa": difference(offense_epa, defense_epa),
        "early_success": difference(early_offense, early_defense),
        "qb_epa": mean_with_sample(dropbacks.qb_epa, 30),
        "sacks_allowed": mean_with_sample(dropbacks.sack, 30),
        "sacks_forced": mean_with_sample(defensive_dropbacks.sack, 30),
        "explosive": difference(mean_with_sample(own.explosive, 60), mean_with_sample(opponent.explosive, 60)),
    }


def build_feature_frame(games, pbp, now=None):
    cutoff = pd.to_datetime(now or datetime.now(timezone.utc), utc=True)
    schedule = games.copy()
    schedule["away_team"] = schedule.away_team.replace(ALIASES)
    schedule["home_team"] = schedule.home_team.replace(ALIASES)
    schedule["_kickoff"] = schedule.apply(parse_schedule_kickoff, axis=1)
    schedule["_kickoff"] = pd.to_datetime(schedule["_kickoff"], utc=True, errors="coerce")
    schedule = schedule[schedule.game_type.eq("REG")].drop_duplicates("game_id")
    plays = valid_plays(pbp)
    rows = []
    for season in plays.season.dropna().unique():
        season_games = schedule[schedule.season.eq(season)]
        history = season_games[
            (season_games._kickoff + pd.Timedelta(hours=6) < cutoff)
            & season_games.away_score.notna() & season_games.home_score.notna()
        ].sort_values(["_kickoff", "game_id"])
        season_plays = plays[plays.season.eq(season)]
        targets = season_games[
            (season_games._kickoff > cutoff)
            & (season_games._kickoff <= cutoff + pd.Timedelta(days=14))
            & season_games.away_score.isna() & season_games.home_score.isna()
        ]
        profiles = {}
        for _, game in targets.iterrows():
            for team in (game.away_team, game.home_team):
                if team not in profiles:
                    profiles[team] = team_profile(season_plays, history, team)
            home, away = profiles[game.home_team], profiles[game.away_team]
            row = {"game_id": str(game.game_id), "as_of": cutoff.isoformat()}
            for feature, metric in (("net_epa_diff", "net_epa"), ("early_down_success_diff", "early_success"),
                                    ("qb_epa_diff", "qb_epa"), ("explosive_play_diff", "explosive")):
                h, a = home.get(metric), away.get(metric)
                row[feature] = h - a if h is not None and a is not None else None
            sacks = [home.get("sacks_forced"), away.get("sacks_allowed"), away.get("sacks_forced"), home.get("sacks_allowed")]
            row["sack_rate_diff"] = (sacks[0] + sacks[1] - sacks[2] - sacks[3]) / 2 if all(value is not None for value in sacks) else None
            config = ModelConfig()
            row["home_field"] = config.home_field if game.get("location") == "Home" else 0.0
            home_rest, away_rest = safe_number(game.get("home_rest")), safe_number(game.get("away_rest"))
            if home_rest is not None and away_rest is not None:
                row["rest_adjustment"] = (home_rest - away_rest) * config.rest_weight
            for feature in CORE_FEATURES:
                value = row[feature]
                if value is not None and safe_number(value) is None:
                    raise ValueError(f"Nonfinite challenger feature: {feature}")
                limit = 1 if feature == "sack_rate_diff" else 2
                if value is not None and feature in {"early_down_success_diff", "sack_rate_diff", "explosive_play_diff"} and abs(value) > limit:
                    raise ValueError(f"Invalid challenger rate: {feature}")
            rows.append(row)
    return pd.DataFrame(rows)


def collect_feature_frame(games, now=None):
    cutoff = pd.to_datetime(now or datetime.now(timezone.utc), utc=True)
    # Current-season history only; no silent substitution of last year's teams/QBs.
    season = cutoff.year if cutoff.month >= 3 else cutoff.year - 1
    return build_feature_frame(games, load_play_by_play(season), cutoff)
