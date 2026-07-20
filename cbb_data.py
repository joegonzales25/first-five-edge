from datetime import date, timedelta

import pandas as pd
import requests


ESPN_CBB_SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/basketball/"
    "mens-college-basketball/scoreboard"
)


def date_range_param(start_date: date, end_date: date) -> str:
    return f"{start_date:%Y%m%d}-{end_date:%Y%m%d}"


def fetch_cbb_scoreboard(start_date: date, end_date: date, limit: int = 1000) -> dict:
    response = requests.get(
        ESPN_CBB_SCOREBOARD_URL,
        params={"dates": date_range_param(start_date, end_date), "limit": limit},
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def competitor_by_side(competition: dict, side: str) -> dict:
    for competitor in competition.get("competitors", []):
        if competitor.get("homeAway") == side:
            return competitor
    return {}


def team_label(competitor: dict) -> str:
    team = competitor.get("team", {})
    return (
        team.get("displayName")
        or team.get("shortDisplayName")
        or team.get("abbreviation")
    )


def parse_score(competitor: dict):
    score = competitor.get("score")
    if score in [None, ""]:
        return None
    try:
        return int(score)
    except Exception:
        return None


def is_neutral_site(competition: dict) -> bool:
    if competition.get("neutralSite") is not None:
        return bool(competition.get("neutralSite"))
    venue = competition.get("venue") or {}
    return bool(venue.get("neutralSite"))


def normalize_cbb_events(events: list[dict]) -> pd.DataFrame:
    rows = []
    for event in events:
        competition = (event.get("competitions") or [{}])[0]
        home = competitor_by_side(competition, "home")
        away = competitor_by_side(competition, "away")
        status_type = (event.get("status") or {}).get("type") or {}
        season = event.get("season") or {}
        season_type = season.get("type")

        if season_type not in [None, 2, 3]:
            continue

        rows.append(
            {
                "game_id": event.get("id"),
                "season": season.get("year"),
                "season_type": season_type,
                "game_date": event.get("date"),
                "away_team": team_label(away),
                "home_team": team_label(home),
                "away_score": parse_score(away),
                "home_score": parse_score(home),
                "neutral_site": is_neutral_site(competition),
                "completed": bool(status_type.get("completed")),
                "status": status_type.get("description")
                or status_type.get("shortDetail")
                or status_type.get("name"),
            }
        )

    games = pd.DataFrame(rows)
    if games.empty:
        return games

    games["game_date_dt"] = pd.to_datetime(games["game_date"], errors="coerce")
    games = games.dropna(subset=["game_date_dt", "away_team", "home_team"]).copy()
    games["season"] = pd.to_numeric(games["season"], errors="coerce").astype("Int64")
    games = games.sort_values(["game_date_dt", "game_id"]).reset_index(drop=True)
    return add_rest_days(games)


def add_rest_days(games: pd.DataFrame) -> pd.DataFrame:
    games = games.copy()
    last_game_date = {}
    away_rest = []
    home_rest = []

    for _, game in games.iterrows():
        game_day = game["game_date_dt"].date()
        away = game["away_team"]
        home = game["home_team"]

        away_previous = last_game_date.get(away)
        home_previous = last_game_date.get(home)
        away_rest.append((game_day - away_previous).days if away_previous else 0)
        home_rest.append((game_day - home_previous).days if home_previous else 0)

        last_game_date[away] = game_day
        last_game_date[home] = game_day

    games["away_rest"] = away_rest
    games["home_rest"] = home_rest
    return games


def cbb_season_start(today: date) -> date:
    season_start_year = today.year if today.month >= 10 else today.year - 1
    return date(season_start_year, 11, 1)


def load_cbb_current_season(
    season: int | None = None,
    today: date | None = None,
    days_ahead: int = 14,
) -> pd.DataFrame:
    today = today or date.today()
    start_date = date(int(season) - 1, 11, 1) if season else cbb_season_start(today)
    end_date = today + timedelta(days=days_ahead)
    data = fetch_cbb_scoreboard(start_date, end_date)
    return normalize_cbb_events(data.get("events", []))
