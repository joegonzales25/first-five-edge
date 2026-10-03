"""CFB team comparisons captured from completed games before kickoff."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import tempfile

import pandas as pd
import requests

from cfb_data import fetch_espn_fbs_teams, normalize_espn_games

SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/football/college-football/summary"
METRICS = ("points", "passing", "rushing", "points_allowed", "passing_allowed", "rushing_allowed")


def load_analysis_season(season):
    teams = fetch_espn_fbs_teams()
    if not teams:
        raise ValueError("FBS team directory unavailable")

    def schedule(team_id):
        for attempt in range(3):
            try:
                response = requests.get(
                    f"https://site.api.espn.com/apis/site/v2/sports/football/college-football/teams/{team_id}/schedule",
                    params={"season": int(season), "seasontype": 2}, timeout=15,
                )
                response.raise_for_status()
                break
            except requests.RequestException:
                if attempt == 2:
                    raise
        payload = response.json()
        if number((payload.get("season") or {}).get("year")) != int(season):
            raise ValueError("CFB schedule returned a different season")
        if "events" not in payload:
            raise ValueError("CFB team schedule is missing events")
        return payload["events"]

    events = {}
    # Team schedules include games omitted by the general scoreboard endpoint.
    with ThreadPoolExecutor(max_workers=6) as pool:
        for schedule_events in pool.map(schedule, teams):
            for event in schedule_events:
                if not event.get("id"):
                    raise ValueError("CFB schedule event is missing its id")
                for competition in event.get("competitions") or []:
                    for competitor in competition.get("competitors") or []:
                        score = competitor.get("score")
                        if isinstance(score, dict):
                            competitor["score"] = score.get("value")
                events[str(event["id"])] = event
    return normalize_espn_games(list(events.values()), teams)


def number(value):
    try:
        value = float(str(value).replace(",", ""))
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def summarize(records):
    result = {"games": len(records)}
    for metric in METRICS:
        values = [r[metric] for r in records if r[metric] is not None]
        result[metric] = round(sum(values) / len(values), 2) if values else None
        result[metric + "_games"] = len(values)
    return result


def load_game_stats(game_id):
    game_id = str(game_id)
    if not game_id.isdigit():
        raise ValueError("Invalid ESPN game id")
    cache = Path(os.environ.get("CFB_STATS_CACHE", Path(tempfile.gettempdir()) / "cfb-team-stats"))
    path = cache / f"{game_id}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    response = requests.get(SUMMARY_URL, params={"event": game_id}, timeout=15)
    response.raise_for_status()
    payload = response.json()
    stats = {}
    for team in (payload.get("boxscore") or {}).get("teams") or []:
        values = {item.get("name"): item.get("displayValue") for item in team.get("statistics") or []}
        stats[str(team["team"]["id"])] = {
            "passing": number(values.get("netPassingYards")),
            "rushing": number(values.get("rushingYards")),
        }
    # Cache only complete final boxscores; missing statistics can be retried.
    if len(stats) == 2 and all(all(value is not None for value in row.values()) for row in stats.values()):
        try:
            cache.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(stats, allow_nan=False), encoding="utf-8")
        except OSError:
            pass
    return stats


def eligible_games(games, season, cutoff):
    if games.empty:
        return games
    cutoff = pd.to_datetime(cutoff, utc=True)
    return games[
        (games["season"] == int(season))
        & (games["season_type"] == "regular")
        & games["completed"].fillna(False).astype(bool)
        & (games["game_date_dt"] + pd.Timedelta(hours=6) < cutoff)
    ].drop_duplicates("game_id")


def build_analysis(games, stats, season, away, home, cutoff):
    records = []
    for _, game in eligible_games(games, season, cutoff).iterrows():
        away_score, home_score = number(game.get("away_score")), number(game.get("home_score"))
        if away_score is None or home_score is None:
            continue
        box = stats.get(str(game["game_id"]), {})
        for side, other, scored, allowed in (("away", "home", away_score, home_score), ("home", "away", home_score, away_score)):
            own = box.get(str(game.get(side + "_team_id")), {})
            opponent = box.get(str(game.get(other + "_team_id")), {})
            records.append({
                "team": game[side + "_team"], "opponent": game[other + "_team"],
                "fbs": game.get(side + "_classification") == "FBS",
                "venue": "Neutral" if game.get("neutral_site") else "Home" if side == "home" else "Away",
                "date": game["game_date_dt"].tz_convert("America/New_York").date().isoformat(),
                "kickoff": game["game_date_dt"].isoformat(),
                "result": "W" if scored > allowed else "L" if scored < allowed else "T",
                "points": scored, "points_allowed": allowed,
                "passing": number(own.get("passing")), "rushing": number(own.get("rushing")),
                "passing_allowed": number(opponent.get("passing")), "rushing_allowed": number(opponent.get("rushing")),
            })
    teams = {}
    for team in (away, home):
        rows = [r for r in records if r["team"] == team]
        teams[team] = {**summarize(rows), "last_five": sorted(rows, key=lambda r: r["kickoff"], reverse=True)[:5]}
    return {
        "version": 1, "season": int(season), "as_of": pd.to_datetime(cutoff, utc=True).isoformat(),
        "source": "ESPN", "through": max((r["date"] for r in records), default=None),
        "teams": teams, "league": summarize([r for r in records if r["fbs"]]),
    }


def attach_pregame_analysis(slate, now=None):
    result = slate.copy()
    result["Pregame Analysis"] = None
    cutoff = pd.to_datetime(now or datetime.now(timezone.utc), utc=True)
    pending = result[
        (pd.to_datetime(result["Scheduled Kickoff"], utc=True, errors="coerce") > cutoff)
        & result["Status"].str.lower().isin(["scheduled", "pre-game", "preview"])
    ]
    for season, rows in pending.groupby("Season"):
        games = load_analysis_season(int(season))
        eligible = eligible_games(games, season, cutoff)
        failures = []

        def fetch(game_id):
            try:
                return str(game_id), load_game_stats(game_id)
            except (requests.RequestException, ValueError, KeyError):
                failures.append(str(game_id))
                return str(game_id), {}

        with ThreadPoolExecutor(max_workers=6) as pool:
            stats = dict(pool.map(fetch, eligible.get("game_id", pd.Series(dtype=object))))
        if failures:
            print(f"CFB pregame analysis: {len(failures)} boxscores unavailable; missing yards remain unavailable.")
        for index, row in rows.iterrows():
            analysis = build_analysis(games, stats, season, row["Away"], row["Home"], cutoff)
            result.at[index, "Pregame Analysis"] = json.dumps(analysis, allow_nan=False)
    return result
