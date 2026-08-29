import os
from datetime import date, timedelta

import pandas as pd
import requests


CFBD_BASE_URL = "https://api.collegefootballdata.com"
ESPN_CFB_SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/football/"
    "college-football/scoreboard"
)
ESPN_CFB_TEAMS_URL = (
    "https://site.web.api.espn.com/apis/site/v2/sports/football/"
    "college-football/teams"
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
        params={
            "dates": target_date.strftime("%Y%m%d"),
            "groups": 80,
            "limit": 1000,
        },
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def fetch_espn_season(
    start_date: date,
    end_date: date,
) -> dict:
    response = requests.get(
        ESPN_CFB_SCOREBOARD_URL,
        params={
            "dates": (
                f"{start_date.strftime('%Y%m%d')}-"
                f"{end_date.strftime('%Y%m%d')}"
            ),
            "groups": 80,
            "limit": 1000,
        },
        timeout=45,
    )
    response.raise_for_status()
    return response.json()


def fetch_espn_fbs_teams() -> dict[str, str]:
    response = requests.get(
        ESPN_CFB_TEAMS_URL,
        params={
            "groups": 80,
            "groupType": "conference",
            "enable": "groups",
            "limit": 1000,
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    sports = payload.get("sports") or []
    leagues = (sports[0].get("leagues") or []) if sports else []
    groups = (leagues[0].get("groups") or []) if leagues else []
    teams = {}
    for group in groups:
        conference = group.get("name")
        for team in group.get("teams") or []:
            team_id = str(team.get("id") or "").strip()
            if team_id:
                teams[team_id] = conference
    return teams


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
                "away_team_id": None,
                "home_team_id": None,
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
        team.get("location")
        or team.get("shortDisplayName")
        or team.get("displayName")
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


def espn_notes(competition: dict):
    notes = competition.get("notes") or []
    if isinstance(notes, str):
        return notes
    values = []
    for note in notes:
        if isinstance(note, dict):
            value = note.get("headline") or note.get("text")
        else:
            value = note
        if value:
            values.append(str(value))
    return "; ".join(values) or None


def espn_status(event: dict, competition: dict):
    status_type = (
        (event.get("status") or {}).get("type")
        or (competition.get("status") or {}).get("type")
        or {}
    )
    return (
        bool(status_type.get("completed")),
        status_type.get("description")
        or status_type.get("shortDetail")
        or status_type.get("name")
        or "Scheduled",
    )


def normalize_espn_games(
    events: list[dict],
    fbs_teams: dict[str, str] | None,
) -> pd.DataFrame:
    rows = []
    for event in events:
        competition = (event.get("competitions") or [{}])[0]
        away = espn_competitor(competition, "away")
        home = espn_competitor(competition, "home")
        away_team = away.get("team") or {}
        home_team = home.get("team") or {}
        season = event.get("season") or {}
        raw_season_type = str(season.get("slug") or "regular").lower()
        season_type = (
            "postseason"
            if season.get("type") == 3 or "post" in raw_season_type
            else "regular"
        )
        notes = espn_notes(competition)
        if season_type == "postseason" and not postseason_game_allowed(
            {"notes": notes}
        ):
            continue

        completed, status = espn_status(event, competition)
        if fbs_teams is None:
            away_classification = "UNKNOWN"
            home_classification = "UNKNOWN"
        else:
            away_classification = (
                "FBS" if str(away_team.get("id")) in fbs_teams else "FCS"
            )
            home_classification = (
                "FBS" if str(home_team.get("id")) in fbs_teams else "FCS"
            )
        if "FBS" not in {away_classification, home_classification} and fbs_teams:
            continue

        venue = competition.get("venue") or {}
        rows.append(
            {
                "game_id": str(event.get("id") or competition.get("id") or ""),
                "season": season.get("year"),
                "week": (event.get("week") or {}).get("number"),
                "season_type": season_type,
                "game_date": event.get("date") or competition.get("date"),
                "away_team_id": str(away_team.get("id") or ""),
                "home_team_id": str(home_team.get("id") or ""),
                "away_team": espn_team_name(away),
                "home_team": espn_team_name(home),
                "away_conference": fbs_teams.get(str(away_team.get("id")))
                if fbs_teams
                else None,
                "home_conference": fbs_teams.get(str(home_team.get("id")))
                if fbs_teams
                else None,
                "away_classification": away_classification,
                "home_classification": home_classification,
                "away_score": espn_score(away),
                "home_score": espn_score(home),
                "away_first_half": espn_first_half(away),
                "home_first_half": espn_first_half(home),
                "neutral_site": bool(competition.get("neutralSite")),
                "conference_game": bool(
                    competition.get("conferenceCompetition")
                ),
                "venue": venue.get("fullName"),
                "notes": notes,
                "completed": completed,
                "status": status,
                "source": "ESPN",
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


def normalize_espn_events(events: list[dict]) -> list[dict]:
    rows = []
    for event in events:
        competition = (event.get("competitions") or [{}])[0]
        away = espn_competitor(competition, "away")
        home = espn_competitor(competition, "home")
        completed, status = espn_status(event, competition)
        rows.append(
            {
                "away_team": espn_team_name(away),
                "home_team": espn_team_name(home),
                "away_score": espn_score(away),
                "home_score": espn_score(home),
                "away_first_half": espn_first_half(away),
                "home_first_half": espn_first_half(home),
                "completed": completed,
                "status": status,
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
    return target_date.year - 1 if target_date.month <= 2 else target_date.year


def load_cfb_prior_season(season: int) -> pd.DataFrame:
    prior_season = int(season) - 1
    season_start = date(prior_season, 7, 1)
    season_end = date(prior_season + 1, 1, 31)
    try:
        fbs_teams = fetch_espn_fbs_teams()
        payload = fetch_espn_season(season_start, season_end)
    except (requests.RequestException, ValueError):
        return pd.DataFrame()
    games = normalize_espn_games(payload.get("events", []), fbs_teams)
    if games.empty:
        return games
    return games[games["completed"]].reset_index(drop=True)


def apply_cfbd_enrichment(
    games: pd.DataFrame,
    season: int,
    include_postseason: bool,
) -> pd.DataFrame:
    if games.empty or not cfbd_api_key():
        return games
    try:
        fbs_teams = fetch_cfbd_fbs_teams(season)
        source_games = fetch_cfbd_games(season, "regular")
        if include_postseason:
            source_games.extend(fetch_cfbd_games(season, "postseason"))
        enrichment = normalize_cfbd_games(source_games, fbs_teams=fbs_teams)
    except (requests.RequestException, RuntimeError, ValueError):
        return games
    if enrichment.empty:
        return games

    enrichment_by_game = {
        (
            team_key(row["away_team"], row["home_team"]),
            row["game_date_dt"].date(),
        ): row
        for _, row in enrichment.iterrows()
    }
    enriched = games.copy()
    columns = [
        "away_conference",
        "home_conference",
        "away_classification",
        "home_classification",
        "away_first_half",
        "home_first_half",
        "venue",
        "notes",
    ]
    for index, game in enriched.iterrows():
        row = enrichment_by_game.get(
            (
                team_key(game["away_team"], game["home_team"]),
                game["game_date_dt"].date(),
            )
        )
        if row is None:
            continue
        for column in columns:
            current = game.get(column)
            if current is None or pd.isna(current) or current == "UNKNOWN":
                value = row.get(column)
                if value is not None and not pd.isna(value):
                    enriched.at[index, column] = value
        enriched.at[index, "source"] = "ESPN + CFBD enrichment"
    return enriched


def load_cfb_season(
    season: int | None = None,
    today: date | None = None,
    days_ahead: int = 14,
) -> pd.DataFrame:
    today = today or date.today()
    season = int(season or season_for_date(today))
    window_end = today + timedelta(days=max(0, int(days_ahead)))
    season_start = date(season, 7, 1)
    season_end = date(season + 1, 1, 31)
    # ESPN can return no events for a range ending on the requested day.
    # Query one extra day, then trim by the game's Eastern slate date.
    query_end = min(window_end + timedelta(days=1), season_end)
    if query_end < season_start:
        return pd.DataFrame()

    try:
        fbs_teams = fetch_espn_fbs_teams()
    except (requests.RequestException, ValueError):
        fbs_teams = None
    payload = fetch_espn_season(season_start, query_end)
    games = normalize_espn_games(payload.get("events", []), fbs_teams)
    if games.empty:
        return games
    eastern_dates = games["game_date_dt"].dt.tz_convert(
        "America/New_York"
    ).dt.date
    games = games[eastern_dates <= window_end].reset_index(drop=True)
    return apply_cfbd_enrichment(
        games,
        season,
        include_postseason=window_end.month in {1, 12},
    )
