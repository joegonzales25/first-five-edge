from datetime import date, timedelta

import pandas as pd
import requests


NHL_SCHEDULE_URL = "https://api-web.nhle.com/v1/schedule/{date_value}"


def fetch_nhl_schedule(day: date) -> dict:
    response = requests.get(
        NHL_SCHEDULE_URL.format(date_value=f"{day:%Y-%m-%d}"),
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def team_label(team: dict) -> str:
    if not team:
        return ""
    name = team.get("placeName") or {}
    common = team.get("commonName") or {}
    return (
        team.get("name", {}).get("default")
        or f"{name.get('default', '')} {common.get('default', '')}".strip()
        or team.get("abbrev")
    )


def parse_score(team: dict):
    score = team.get("score")
    if score in [None, ""]:
        return None
    try:
        return int(score)
    except Exception:
        return None


def is_completed_state(game_state: str) -> bool:
    return str(game_state or "").upper() in ["OFF", "FINAL"]


def status_label(game: dict) -> str:
    state = str(game.get("gameState") or "")
    if state.upper() in ["FUT", "PRE"]:
        return "Scheduled"
    if state.upper() in ["LIVE", "CRIT"]:
        return "In Progress"
    if state.upper() in ["OFF", "FINAL"]:
        return "Final"
    return state or "Scheduled"


def season_start(today: date) -> date:
    season_year = today.year if today.month >= 9 else today.year - 1
    return date(season_year, 10, 1)


def normalize_nhl_games(raw_games: list[dict]) -> pd.DataFrame:
    rows = []
    for game in raw_games:
        away = game.get("awayTeam") or {}
        home = game.get("homeTeam") or {}
        game_state = game.get("gameState")
        rows.append(
            {
                "game_id": game.get("id"),
                "season": game.get("season"),
                "game_date": game.get("startTimeUTC") or game.get("gameDate"),
                "away_team": team_label(away),
                "home_team": team_label(home),
                "away_score": parse_score(away),
                "home_score": parse_score(home),
                "completed": is_completed_state(game_state),
                "status": status_label(game),
                "game_state": game_state,
            }
        )

    games = pd.DataFrame(rows)
    if games.empty:
        return games

    games["game_date_dt"] = pd.to_datetime(games["game_date"], errors="coerce")
    games = games.dropna(subset=["game_date_dt", "away_team", "home_team"]).copy()
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


def load_nhl_current_season(
    season: int | None = None,
    today: date | None = None,
    days_ahead: int = 14,
) -> pd.DataFrame:
    today = today or date.today()
    start_date = date(season, 10, 1) if season else season_start(today)
    end_date = today + timedelta(days=days_ahead)
    raw_games = []
    current = start_date
    while current <= end_date:
        data = fetch_nhl_schedule(current)
        for week in data.get("gameWeek", []):
            raw_games.extend(week.get("games", []))
        current += timedelta(days=7)

    games = normalize_nhl_games(raw_games)
    if games.empty:
        return games

    return games.drop_duplicates(subset=["game_id"]).reset_index(drop=True)
