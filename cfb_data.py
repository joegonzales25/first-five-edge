import os
from datetime import date, timedelta

import pandas as pd
import requests


CFBD_BASE_URL = "https://api.collegefootballdata.com"
ESPN_CFB_SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/football/"
    "college-football/scoreboard"
)
POSTSEASON_KEYWORDS = (
    "college football playoff",
    "cfp",
    "semifinal",
    "national championship",
)


def cfbd_api_key():
    return (
        os.environ.get("CFBD_API_KEY")
        or os.environ.get("COLLEGE_FOOTBALL_DATA_API_KEY")
        or ""
    ).strip()


def cfbd_headers():
    api_key = cfbd_api_key()
    if not api_key:
        raise RuntimeError(
            "CFB requires CFBD_API_KEY (or COLLEGE_FOOTBALL_DATA_API_KEY)."
        )
    return {"Authorization": f"Bearer {api_key}"}


def fetch_cfbd_games(year: int, season_type: str) -> list[dict]:
    response = requests.get(
        f"{CFBD_BASE_URL}/games",
        headers=cfbd_headers(),
        params={
            "year": int(year),
            "seasonType": season_type,
            "classification": "fbs",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def fetch_cfbd_fbs_teams(year: int) -> set[str]:
    response = requests.get(
        f"{CFBD_BASE_URL}/teams/fbs",
        headers=cfbd_headers(),
        params={"year": int(year)},
        timeout=30,
    )
    response.raise_for_status()
    return {
        str(team.get("school") or "").strip().casefold()
        for team in response.json()
        if team.get("school")
    }


def fetch_espn_scoreboard(target_date: date) -> dict:
    response = requests.get(
        ESPN_CFB_SCOREBOARD_URL,
        params={"dates": target_date.strftime("%Y%m%d"), "limit": 1000},
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def normalize_classification(value):
    text = str(value or "").strip().upper()
    return text if text else "UNKNOWN"


def postseason_game_allowed(game: dict) -> bool:
    notes = str(game.get("notes") or "").lower()
    return any(keyword in notes for keyword in POSTSEASON_KEYWORDS)


def first_half_points(line_scores):
    if not isinstance(line_scores, list) or len(line_scores) < 2:
        return None
    try:
        return int(line_scores[0] or 0) + int(line_scores[1] or 0)
    except Exception:
        return None


def normalize_cfbd_games(
    games: list[dict],
    fbs_teams: set[str] | None = None,
) -> pd.DataFrame:
    fbs_teams = fbs_teams or set()
    rows = []
    for game in games:
        season_type = str(game.get("season_type") or "").lower()
        if season_type == "postseason" and not postseason_game_allowed(game):
            continue

        away_team = game.get("away_team")
        home_team = game.get("home_team")
        away_classification = (
            "FBS"
            if str(away_team or "").strip().casefold() in fbs_teams
            else normalize_classification(game.get("away_classification"))
        )
        home_classification = (
            "FBS"
            if str(home_team or "").strip().casefold() in fbs_teams
            else normalize_classification(game.get("home_classification"))
        )
        if "FBS" not in {away_classification, home_classification}:
            continue

        away_points = game.get("away_points")
        home_points = game.get("home_points")
        completed = bool(game.get("completed"))
        if not completed and away_points is not None and home_points is not None:
            completed = True

        rows.append(
            {
                "game_id": str(game.get("id") or ""),
                "season": game.get("season"),
                "week": game.get("week"),
                "season_type": season_type or "regular",
                "game_date": game.get("start_date"),
                "away_team": away_team,
                "home_team": home_team,
                "away_conference": game.get("away_conference"),
                "home_conference": game.get("home_conference"),
                "away_classification": away_classification,
                "home_classification": home_classification,
                "away_score": away_points,
                "home_score": home_points,
                "away_first_half": first_half_points(
                    game.get("away_line_scores")
                ),
                "home_first_half": first_half_points(
                    game.get("home_line_scores")
                ),
                "neutral_site": bool(game.get("neutral_site")),
                "conference_game": bool(game.get("conference_game")),
                "venue": game.get("venue"),
                "notes": game.get("notes"),
                "completed": completed,
                "status": "Final" if completed else "Scheduled",
                "source": "CFBD",
            }
        )

    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    frame["game_date_dt"] = pd.to_datetime(
        frame["game_date"], errors="coerce", utc=True
    )
    frame = frame.dropna(
        subset=["game_id", "game_date_dt", "away_team", "home_team"]
    ).copy()
    return frame.sort_values(["game_date_dt", "game_id"]).reset_index(drop=True)


def espn_competitor(competition: dict, side: str) -> dict:
    for competitor in competition.get("competitors", []):
        if competitor.get("homeAway") == side:
            return competitor
    return {}


def espn_team_name(competitor: dict):
    team = competitor.get("team") or {}
    return (
        team.get("displayName")
        or team.get("shortDisplayName")
        or team.get("abbreviation")
    )


def espn_score(competitor: dict):
    value = competitor.get("score")
    try:
        return int(value) if value not in [None, ""] else None
    except Exception:
        return None


def espn_first_half(competitor: dict):
    linescores = competitor.get("linescores") or []
    if len(linescores) < 2:
        return None
    try:
        return int(linescores[0].get("value") or 0) + int(
            linescores[1].get("value") or 0
        )
    except Exception:
        return None


def normalize_espn_events(events: list[dict]) -> list[dict]:
    rows = []
    for event in events:
        competition = (event.get("competitions") or [{}])[0]
        away = espn_competitor(competition, "away")
        home = espn_competitor(competition, "home")
        status_type = (event.get("status") or {}).get("type") or {}
        rows.append(
            {
                "away_team": espn_team_name(away),
                "home_team": espn_team_name(home),
                "away_score": espn_score(away),
                "home_score": espn_score(home),
                "away_first_half": espn_first_half(away),
                "home_first_half": espn_first_half(home),
                "completed": bool(status_type.get("completed")),
                "status": status_type.get("description")
                or status_type.get("shortDetail")
                or status_type.get("name")
                or "Scheduled",
            }
        )
    return rows


def team_key(away_team, home_team):
    return (
        str(away_team or "").strip().casefold(),
        str(home_team or "").strip().casefold(),
    )


def apply_espn_status(games: pd.DataFrame, target_dates) -> pd.DataFrame:
    if games.empty:
        return games

    overlays = {}
    for target_date in sorted(set(target_dates)):
        try:
            payload = fetch_espn_scoreboard(target_date)
        except requests.RequestException:
            continue
        for row in normalize_espn_events(payload.get("events", [])):
            overlays[team_key(row["away_team"], row["home_team"])] = row

    if not overlays:
        return games

    updated = games.copy()
    for index, game in updated.iterrows():
        overlay = overlays.get(team_key(game["away_team"], game["home_team"]))
        if not overlay:
            continue
        for column in [
            "away_score",
            "home_score",
            "away_first_half",
            "home_first_half",
            "completed",
            "status",
        ]:
            value = overlay.get(column)
            if value is not None:
                updated.at[index, column] = value
        updated.at[index, "source"] = "CFBD + ESPN status"
    return updated


def season_for_date(target_date: date) -> int:
    return target_date.year


def load_cfb_season(
    season: int | None = None,
    today: date | None = None,
    days_ahead: int = 14,
) -> pd.DataFrame:
    today = today or date.today()
    season = int(season or season_for_date(today))
    fbs_teams = fetch_cfbd_fbs_teams(season)
    regular = fetch_cfbd_games(season, "regular")
    postseason = (
        fetch_cfbd_games(season, "postseason")
        if today.month in {1, 12}
        else []
    )
    games = normalize_cfbd_games(
        [*regular, *postseason],
        fbs_teams=fbs_teams,
    )
    if games.empty:
        return games

    window_end = today + timedelta(days=max(0, int(days_ahead)))
    relevant_dates = [
        timestamp.date()
        for timestamp in games["game_date_dt"]
        if today <= timestamp.date() <= window_end
    ]
    return apply_espn_status(games, relevant_dates)
