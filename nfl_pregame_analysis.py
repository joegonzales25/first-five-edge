"""Informational, current-season comparisons captured before kickoff."""

from datetime import datetime, timezone
from io import StringIO
import json
import math

import pandas as pd
import requests

from nfl_agent import parse_schedule_kickoff

TEAM_STATS_URL = "https://github.com/nflverse/nflverse-data/releases/download/stats_team/stats_team_week_{season}.csv"
ALIASES = {"LAR": "LA", "WSH": "WAS"}
METRICS = ("points", "passing", "rushing", "points_allowed", "passing_allowed", "rushing_allowed")


def load_team_stats(season):
    response = requests.get(TEAM_STATS_URL.format(season=int(season)), timeout=30)
    response.raise_for_status()
    stats = pd.read_csv(StringIO(response.text))
    required = {"game_id", "team", "season", "season_type", "passing_yards", "rushing_yards"}
    if not required.issubset(stats.columns):
        raise ValueError("NFL team statistics are missing required columns")
    return stats


def number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def summarize(rows):
    result = {"games": len(rows)}
    for metric in METRICS:
        values = [r[metric] for r in rows if r[metric] is not None]
        result[metric] = round(sum(values) / len(values), 2) if values else None
        result[metric + "_games"] = len(values)
    return result


def build_analysis(games, stats, season, away, home, cutoff):
    cutoff = pd.to_datetime(cutoff, utc=True)
    stat_map = {}
    for _, row in stats.iterrows():
        if number(row.get("season")) != int(season) or row.get("season_type") != "REG":
            continue
        team = ALIASES.get(row.get("team"), row.get("team"))
        key = (str(row.get("game_id")), team)
        if key in stat_map:
            raise ValueError("Duplicate NFL team-game statistics")
        stat_map[key] = row
    records = []
    seen = set()
    for _, game in games.iterrows():
        if number(game.get("season")) != int(season) or game.get("game_type") != "REG":
            continue
        kickoff = parse_schedule_kickoff(game)
        # Conservatively exclude same-window games even when final scores exist.
        if kickoff is None or kickoff + pd.Timedelta(hours=6) >= cutoff:
            continue
        game_id = str(game.get("game_id"))
        if game_id in seen:
            continue
        away_score, home_score = number(game.get("away_score")), number(game.get("home_score"))
        if away_score is None or home_score is None:
            continue
        seen.add(game_id)
        for side, other, scored, allowed in (("away", "home", away_score, home_score),
                                             ("home", "away", home_score, away_score)):
            team = ALIASES.get(game[side + "_team"], game[side + "_team"])
            opponent = ALIASES.get(game[other + "_team"], game[other + "_team"])
            own = stat_map.get((game_id, team), {})
            opp = stat_map.get((game_id, opponent), {})
            records.append({
                "team": team, "opponent": opponent,
                "venue": "Neutral" if game.get("location") == "Neutral" else "Home" if side == "home" else "Away",
                "date": str(game["gameday"]), "kickoff": kickoff.isoformat(),
                "result": "W" if scored > allowed else "L" if scored < allowed else "T",
                "points": scored, "points_allowed": allowed,
                "passing": number(own.get("passing_yards")), "rushing": number(own.get("rushing_yards")),
                "passing_allowed": number(opp.get("passing_yards")), "rushing_allowed": number(opp.get("rushing_yards")),
            })
    teams = {}
    for team in (away, home):
        rows = [r for r in records if r["team"] == team]
        recent = sorted(rows, key=lambda r: r["kickoff"], reverse=True)[:5]
        teams[team] = {**summarize(rows), "last_five": recent, "last_five_summary": summarize(recent)}
    return {"version": 1, "season": int(season), "as_of": cutoff.isoformat(),
            "through": max((r["date"] for r in records), default=None),
            "source": "nflverse", "teams": teams, "league": summarize(records)}


def attach_pregame_analysis(slate, games, stats, now=None):
    now = pd.Timestamp(now or datetime.now(timezone.utc))
    result = slate.copy()
    result["Pregame Analysis"] = None
    for index, row in result.iterrows():
        kickoff = pd.to_datetime(row.get("Scheduled Kickoff"), utc=True, errors="coerce")
        if pd.isna(kickoff) or now >= kickoff or str(row.get("Status")).lower() not in {"scheduled", "pre-game", "preview"}:
            continue
        analysis = build_analysis(games, stats, row["Season"], row["Away"], row["Home"], now)
        result.at[index, "Pregame Analysis"] = json.dumps(analysis, allow_nan=False)
    return result
