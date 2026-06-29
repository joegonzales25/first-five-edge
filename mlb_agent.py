import os
import requests
import pandas as pd

from datetime import date, datetime, timedelta
from functools import lru_cache
from time import perf_counter, sleep
from zoneinfo import ZoneInfo


UNAVAILABLE = "N/A"
ENABLE_LOAD_PROFILING = os.getenv("MLB_AGENT_PROFILE", "0") == "1"
PITCHER_STATS_CACHE = {}

TEAM_ABBREVIATIONS = {
    "Arizona Diamondbacks": "ARI",
    "Athletics": "ATH",
    "Atlanta Braves": "ATL",
    "Baltimore Orioles": "BAL",
    "Boston Red Sox": "BOS",
    "Chicago Cubs": "CHC",
    "Chicago White Sox": "CWS",
    "Cincinnati Reds": "CIN",
    "Cleveland Guardians": "CLE",
    "Colorado Rockies": "COL",
    "Detroit Tigers": "DET",
    "Houston Astros": "HOU",
    "Kansas City Royals": "KC",
    "Los Angeles Angels": "LAA",
    "Los Angeles Dodgers": "LAD",
    "Miami Marlins": "MIA",
    "Milwaukee Brewers": "MIL",
    "Minnesota Twins": "MIN",
    "New York Mets": "NYM",
    "New York Yankees": "NYY",
    "Philadelphia Phillies": "PHI",
    "Pittsburgh Pirates": "PIT",
    "San Diego Padres": "SD",
    "San Francisco Giants": "SF",
    "Seattle Mariners": "SEA",
    "St. Louis Cardinals": "STL",
    "Tampa Bay Rays": "TB",
    "Texas Rangers": "TEX",
    "Toronto Blue Jays": "TOR",
    "Washington Nationals": "WSH",
}


try:
    from team_stats import get_team_hitting_stats
    TEAM_OFFENSE = get_team_hitting_stats()
except Exception:
    try:
        from team_data import TEAM_OFFENSE
    except Exception:
        TEAM_OFFENSE = {}


try:
    from bullpen_stats import get_recent_bullpen_fatigue
    BULLPEN_FATIGUE = get_recent_bullpen_fatigue(days_back=3)
except Exception:
    try:
        from bullpen_data import BULLPEN_FATIGUE
    except Exception:
        BULLPEN_FATIGUE = {}


try:
    from first_inning_data import FIRST_INNING_RISK
except Exception:
    FIRST_INNING_RISK = {}


try:
    from first_inning_stats import get_first_inning_stats
    FIRST_INNING_LIVE = get_first_inning_stats(days_back=60)
except Exception:
    FIRST_INNING_LIVE = {}


try:
    from pitcher_first_inning_stats import (
        estimate_pitcher_first_inning_stats,
        get_pitcher_first_inning_stats,
    )
except Exception:
    estimate_pitcher_first_inning_stats = None
    get_pitcher_first_inning_stats = None


def safe_float(value):
    try:
        return float(value)
    except Exception:
        return None


def profile_add(profile, label, elapsed):
    if not ENABLE_LOAD_PROFILING:
        return

    profile[label] = profile.get(label, 0) + elapsed


def profile_print(profile):
    if not ENABLE_LOAD_PROFILING:
        return

    print("\nMLB agent load profile:")
    for label, elapsed in sorted(
        profile.items(),
        key=lambda item: item[1],
        reverse=True,
    ):
        print(f"  {label}: {elapsed:.2f}s")


def average_metric(records, metric_name):
    values = []

    for record in records.values():
        value = safe_float(record.get(metric_name))
        if value is not None:
            values.append(value)

    if not values:
        return UNAVAILABLE

    return round(sum(values) / len(values), 1)


LEAGUE_YRFI_AVG = average_metric(FIRST_INNING_LIVE, "Offense YRFI %")


def parse_baseball_innings(value):
    if value in [None, "", UNAVAILABLE]:
        return None

    text = str(value)
    whole, _, partial = text.partition(".")

    try:
        innings = int(whole)
    except ValueError:
        return None

    if partial == "1":
        innings += 1 / 3
    elif partial == "2":
        innings += 2 / 3
    elif partial:
        try:
            innings += float(f"0.{partial}")
        except ValueError:
            return None

    return innings


def format_ip_per_start(innings_pitched, starts):
    innings = parse_baseball_innings(innings_pitched)

    try:
        starts = int(starts)
    except Exception:
        return UNAVAILABLE

    if innings is None or starts <= 0:
        return UNAVAILABLE

    return round(innings / starts, 1)


def baseball_innings_to_outs(value):
    if value in [None, "", UNAVAILABLE]:
        return 0

    text = str(value)
    whole, _, partial = text.partition(".")

    try:
        outs = int(whole) * 3
    except ValueError:
        return 0

    if partial:
        try:
            outs += min(int(partial[0]), 2)
        except ValueError:
            return 0

    return outs


@lru_cache(maxsize=512)
def get_start_only_ip_per_start(pitcher_id, season=None):
    if not pitcher_id:
        return UNAVAILABLE

    season_param = f"&season={season}" if season else ""
    url = (
        f"https://statsapi.mlb.com/api/v1/people/{pitcher_id}/stats"
        f"?stats=gameLog&group=pitching{season_param}"
    )

    try:
        data = requests.get(url, timeout=10).json()
        splits = data.get("stats", [{}])[0].get("splits", [])
    except Exception:
        return UNAVAILABLE

    start_outs = 0
    starts = 0

    for split in splits:
        stat = split.get("stat", {})
        if int(stat.get("gamesStarted", 0) or 0) <= 0:
            continue

        starts += 1
        start_outs += baseball_innings_to_outs(stat.get("inningsPitched"))

    if starts <= 0 or start_outs <= 0:
        return UNAVAILABLE

    return round((start_outs / 3) / starts, 1)


def calculate_factor_confidence(nrfi_signals, yrfi_signals):
    dominant_signals = max(nrfi_signals, yrfi_signals)
    opposing_signals = min(nrfi_signals, yrfi_signals)

    if dominant_signals == 0:
        return "D"

    if opposing_signals == 0:
        if dominant_signals >= 5:
            return "A+"
        if dominant_signals >= 4:
            return "A"
        if dominant_signals >= 3:
            return "B"
        if dominant_signals >= 2:
            return "C"
        return "D"

    net_agreement = dominant_signals - opposing_signals
    if dominant_signals >= 5 and net_agreement >= 3:
        return "B"
    if dominant_signals >= 3 and net_agreement >= 2:
        return "C"
    return "D"


def get_team_offense_score(team_name):
    return TEAM_OFFENSE.get(team_name, 5)


def get_first_inning_risk(team_name):
    return FIRST_INNING_RISK.get(team_name, 5)


def get_live_first_inning_stats(team_name):
    return FIRST_INNING_LIVE.get(team_name, {
        "Offense YRFI %": UNAVAILABLE,
        "1st Run Avg": UNAVAILABLE,
    })


@lru_cache(maxsize=512)
def get_pitcher_first_stats(pitcher_id, season=None):
    fallback = {
        "Pitcher YRFI %": UNAVAILABLE,
        "1st ERA": UNAVAILABLE,
        "1st WHIP": UNAVAILABLE,
        "1st IP": UNAVAILABLE,
        "1st Games": 0,
        "1st R": UNAVAILABLE,
        "1st ER": UNAVAILABLE,
        "1st H": UNAVAILABLE,
        "1st BB": UNAVAILABLE,
        "1st HR": UNAVAILABLE,
        "1st BF": UNAVAILABLE,
        "1st Split Source": "Unavailable",
        "Starts": 0,
    }

    if get_pitcher_first_inning_stats is None:
        return fallback

    try:
        return get_pitcher_first_inning_stats(pitcher_id, season)
    except Exception:
        return fallback


@lru_cache(maxsize=512)
def get_pitcher_first_baseline_stats(pitcher_id, season=None):
    fallback = {
        "Pitcher YRFI %": UNAVAILABLE,
        "1st ERA": UNAVAILABLE,
        "1st WHIP": UNAVAILABLE,
        "Starts": 0,
    }

    if estimate_pitcher_first_inning_stats is None:
        return fallback

    try:
        stats = estimate_pitcher_first_inning_stats(pitcher_id, season)
    except Exception:
        return fallback

    return {**fallback, **stats}


def get_bullpen_data(team_name):
    fallback = {
        "Fatigue Score": 5,
        "Yesterday Relievers": UNAVAILABLE,
        "Yesterday Pitches": UNAVAILABLE,
        "Last 3 Days IP": UNAVAILABLE,
        "Last 3 Days Pitches": UNAVAILABLE,
        "Last 3 Days Relievers": UNAVAILABLE,
        "Back-to-Back Arms": UNAVAILABLE,
    }

    data = BULLPEN_FATIGUE.get(team_name, fallback)

    if isinstance(data, dict):
        return {**fallback, **data}

    return {**fallback, "Fatigue Score": data}


def get_bullpen_fatigue_score(team_name):
    return get_bullpen_data(team_name)["Fatigue Score"]


def bullpen_label(score):
    if score <= 3:
        return "Fresh"
    if score <= 5:
        return "Normal"
    if score <= 7:
        return "Moderate"
    if score <= 9:
        return "Heavy"
    return "Extreme"


def parse_game_datetime(raw_time):
    if not raw_time:
        return None

    try:
        return datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
    except Exception:
        return None


def format_game_time(raw_time, timezone_name="America/New_York"):
    utc_dt = parse_game_datetime(raw_time)

    if utc_dt is None:
        return raw_time

    try:
        display_tz = ZoneInfo(timezone_name)
    except Exception:
        display_tz = ZoneInfo("America/New_York")

    display_dt = utc_dt.astimezone(display_tz)
    timezone_label = display_dt.tzname() or "Local"

    return f'{display_dt.strftime("%I:%M %p").lstrip("0")} {timezone_label}'


def game_status_sort_value(status):
    status_text = str(status).lower()

    if any(term in status_text for term in ["scheduled", "pre-game", "warmup"]):
        return 0
    if any(term in status_text for term in ["in progress", "delayed", "suspended"]):
        return 1
    return 2


def is_game_not_started(status):
    return game_status_sort_value(status) == 0


def get_inning_runs(linescore, inning_number):
    for inning in linescore.get("innings", []):
        if inning.get("num") == inning_number:
            away_runs = inning.get("away", {}).get("runs")
            home_runs = inning.get("home", {}).get("runs")

            if away_runs is None or home_runs is None:
                return None

            return away_runs, home_runs

    return None


def format_score_result(label, away_team, away_score, home_team, home_score):
    if away_score is None or home_score is None:
        return "Pending"

    return f"{label}: {away_team} {away_score}, {home_team} {home_score}"


def team_abbreviation(team_name):
    return TEAM_ABBREVIATIONS.get(team_name, str(team_name)[:3].upper())


@lru_cache(maxsize=512)
def get_pitcher_throwing_side(player_id):
    if not player_id:
        return UNAVAILABLE

    try:
        url = f"https://statsapi.mlb.com/api/v1/people/{player_id}"
        person = requests.get(url, timeout=10).json().get("people", [{}])[0]
        return person.get("pitchHand", {}).get("code", UNAVAILABLE)
    except Exception:
        return UNAVAILABLE


def format_compact_score_result(label, away_team, away_score, home_team, home_score):
    if away_score is None or home_score is None:
        return "Pending"

    away_abbr = team_abbreviation(away_team)
    home_abbr = team_abbreviation(home_team)
    return f"{label}: {away_abbr} {away_score}, {home_abbr} {home_score}"


def build_first_inning_result(linescore, status):
    if is_game_not_started(status):
        return "Pending"

    first_inning_runs = get_inning_runs(linescore, 1)
    if first_inning_runs is None:
        return "In Progress"

    away_runs, home_runs = first_inning_runs
    return "YRFI" if (away_runs + home_runs) > 0 else "NRFI"


def build_f5_result(linescore, status, away_team, home_team, compact=False):
    innings = linescore.get("innings", [])

    if is_game_not_started(status):
        return "Pending"

    completed_first_five = [
        inning for inning in innings
        if inning.get("num") in [1, 2, 3, 4, 5]
        and inning.get("away", {}).get("runs") is not None
        and inning.get("home", {}).get("runs") is not None
    ]

    if len(completed_first_five) >= 5:
        away_score = sum(inning["away"]["runs"] for inning in completed_first_five)
        home_score = sum(inning["home"]["runs"] for inning in completed_first_five)
        if compact:
            return format_compact_score_result("F5", away_team, away_score, home_team, home_score)
        return format_score_result("After 5", away_team, away_score, home_team, home_score)

    away_score = linescore.get("teams", {}).get("away", {}).get("runs")
    home_score = linescore.get("teams", {}).get("home", {}).get("runs")
    if compact:
        return format_compact_score_result("Live", away_team, away_score, home_team, home_score)
    return format_score_result("In Progress", away_team, away_score, home_team, home_score)


def build_full_game_result(linescore, status, away_team, home_team, compact=False):
    if is_game_not_started(status):
        return "Pending"

    away_score = linescore.get("teams", {}).get("away", {}).get("runs")
    home_score = linescore.get("teams", {}).get("home", {}).get("runs")
    status_text = str(status).lower()
    label = "Final" if game_status_sort_value(status) == 2 or "game over" in status_text else "In Progress"
    if compact:
        compact_label = "Final" if label == "Final" else "Live"
        return format_compact_score_result(compact_label, away_team, away_score, home_team, home_score)

    return format_score_result(label, away_team, away_score, home_team, home_score)


def parse_slate_date(slate_date):
    try:
        return datetime.strptime(str(slate_date), "%Y-%m-%d").date()
    except ValueError:
        return date.today()


def format_recent_game_date(game_date):
    try:
        return datetime.fromisoformat(game_date.replace("Z", "+00:00")).strftime("%m/%d")
    except Exception:
        return UNAVAILABLE


@lru_cache(maxsize=256)
def get_team_last_5_results(team_id, team_name, slate_date):
    if not team_id:
        return []

    end_date = parse_slate_date(slate_date) - timedelta(days=1)
    start_date = end_date - timedelta(days=30)
    url = (
        "https://statsapi.mlb.com/api/v1/schedule"
        f"?sportId=1&teamId={team_id}&startDate={start_date.isoformat()}"
        f"&endDate={end_date.isoformat()}&hydrate=linescore"
    )

    try:
        data = requests.get(url, timeout=15).json()
    except Exception:
        return []

    results = []

    for day in data.get("dates", []):
        for game in day.get("games", []):
            status = game.get("status", {}).get("detailedState", "")
            if game_status_sort_value(status) != 2:
                continue

            teams = game.get("teams", {})
            away = teams.get("away", {})
            home = teams.get("home", {})
            away_team = away.get("team", {})
            home_team = home.get("team", {})
            away_score = away.get("score")
            home_score = home.get("score")

            if away_score is None or home_score is None:
                continue

            is_away = away_team.get("id") == team_id
            opponent = home_team.get("name") if is_away else away_team.get("name")
            team_score = away_score if is_away else home_score
            opponent_score = home_score if is_away else away_score
            location = "@" if is_away else "vs"
            opponent_label = team_abbreviation(opponent)

            results.append({
                "Team": team_name,
                "Date": format_recent_game_date(game.get("gameDate", "")),
                "Sort Date": game.get("gameDate", ""),
                "Opponent": f"{location} {opponent_label}",
                "Result": "W" if team_score > opponent_score else "L",
                "Score": f"{team_score}-{opponent_score}",
            })

    results = sorted(results, key=lambda result: result.get("Sort Date", ""), reverse=True)
    return results[:5]


def get_pitcher_stats(pitcher_id, season=None):
    fallback = {
        "ERA": None,
        "WHIP": None,
        "W": UNAVAILABLE,
        "L": UNAVAILABLE,
        "IP": UNAVAILABLE,
        "GS": 0,
        "IP/Start": UNAVAILABLE,
        "K": UNAVAILABLE,
        "Last 7 ERA": UNAVAILABLE,
        "Last 7 WHIP": UNAVAILABLE,
        "Last 7 K/BB": UNAVAILABLE,
        "Last 7 P/IP": UNAVAILABLE,
        "Last 7 OPS": UNAVAILABLE,
        "Last 15 ERA": UNAVAILABLE,
        "Last 15 WHIP": UNAVAILABLE,
        "Last 15 K/BB": UNAVAILABLE,
        "Last 15 P/IP": UNAVAILABLE,
        "Last 15 OPS": UNAVAILABLE,
        "Last 30 ERA": UNAVAILABLE,
        "Last 30 WHIP": UNAVAILABLE,
        "Last 30 K/BB": UNAVAILABLE,
        "Last 30 P/IP": UNAVAILABLE,
        "Last 30 OPS": UNAVAILABLE,
    }

    if not pitcher_id:
        return fallback

    cache_key = (pitcher_id, season)
    if cache_key in PITCHER_STATS_CACHE:
        return PITCHER_STATS_CACHE[cache_key]

    season_param = f"&season={season}" if season else ""
    url = (
        f"https://statsapi.mlb.com/api/v1/people/"
        f"{pitcher_id}/stats?stats=season&group=pitching{season_param}"
    )

    try:
        data = requests.get(url, timeout=10).json()
        stats = data["stats"][0]["splits"][0]["stat"]

        pitcher_stats = {
            "ERA": safe_float(stats.get("era")),
            "WHIP": safe_float(stats.get("whip")),
            "W": stats.get("wins", UNAVAILABLE),
            "L": stats.get("losses", UNAVAILABLE),
            "IP": stats.get("inningsPitched", UNAVAILABLE),
            "GS": stats.get("gamesStarted", 0),
            "IP/Start": get_start_only_ip_per_start(pitcher_id, season),
            "K": stats.get("strikeOuts", UNAVAILABLE),
        }
        if pitcher_stats["IP/Start"] == UNAVAILABLE:
            pitcher_stats["IP/Start"] = format_ip_per_start(
                pitcher_stats["IP"],
                pitcher_stats["GS"],
            )
        # Recent form remains available via get_pitcher_recent_form(), but it is
        # not fetched during normal slate loads until the UI promotes it again.
        result = {**fallback, **pitcher_stats}
        PITCHER_STATS_CACHE[cache_key] = result
        return result

    except Exception:
        return fallback


@lru_cache(maxsize=512)
def get_pitcher_recent_form(pitcher_id, season=None):
    if not pitcher_id:
        return {}

    season = season or date.today().year
    recent = {}

    for games in [7, 15, 30]:
        url = (
            f"https://statsapi.mlb.com/api/v1/people/{pitcher_id}/stats"
            f"?stats=lastXGames&group=pitching&season={season}&limit={games}"
        )
        try:
            data = requests.get(url, timeout=10).json()
            splits = data.get("stats", [])[0].get("splits", [])
            stat = splits[0].get("stat", {}) if splits else {}
        except Exception:
            stat = {}

        recent.update({
            f"Last {games} ERA": stat.get("era", UNAVAILABLE),
            f"Last {games} WHIP": stat.get("whip", UNAVAILABLE),
            f"Last {games} K/BB": stat.get("strikeoutWalkRatio", UNAVAILABLE),
            f"Last {games} P/IP": stat.get("pitchesPerInning", UNAVAILABLE),
            f"Last {games} OPS": stat.get("ops", UNAVAILABLE),
        })

    return recent


@lru_cache(maxsize=16)
def get_team_records(season=None):
    season = season or date.today().year

    url = (
        "https://statsapi.mlb.com/api/v1/standings"
        f"?leagueId=103,104&season={season}"
    )

    try:
        data = requests.get(url, timeout=10).json()
    except Exception:
        return {}

    records = {}

    for league in data.get("records", []):
        for team_record in league.get("teamRecords", []):
            team_name = team_record["team"]["name"]
            wins = team_record.get("wins", 0)
            losses = team_record.get("losses", 0)
            games_played = wins + losses
            runs_scored = safe_float(team_record.get("runsScored"))
            runs_per_game = UNAVAILABLE

            if runs_scored is not None and games_played > 0:
                runs_per_game = round(runs_scored / games_played, 2)

            records[team_name] = {
                "record": f"{wins}-{losses}",
                "runs_per_game": runs_per_game,
            }

    return records


def format_team_record(team_side, fallback=UNAVAILABLE):
    if isinstance(fallback, dict):
        fallback = fallback.get("record", UNAVAILABLE)

    record = team_side.get("leagueRecord", {})
    wins = record.get("wins")
    losses = record.get("losses")

    if wins is None or losses is None:
        return fallback

    return f"{wins}-{losses}"


def get_team_runs_per_game(team_records, team_name):
    record = team_records.get(team_name, {})

    if not record:
        for record_team_name, record_data in team_records.items():
            if (
                str(record_team_name).lower() in str(team_name).lower()
                or str(team_name).lower() in str(record_team_name).lower()
            ):
                record = record_data
                break

    if isinstance(record, dict):
        return record.get("runs_per_game", UNAVAILABLE)

    return UNAVAILABLE


def calculate_nrfi_score(
    away_stats,
    home_stats,
    away_offense,
    home_offense,
    away_first_inning,
    home_first_inning,
    away_pitcher_yrfi=None,
    home_pitcher_yrfi=None,
    away_offense_yrfi=None,
    home_offense_yrfi=None,
    away_first_era=None,
    home_first_era=None,
    away_first_whip=None,
    home_first_whip=None,
    away_first_run_avg=None,
    home_first_run_avg=None,
):
    if away_stats["ERA"] is None or home_stats["ERA"] is None:
        return None, "Pending", "Waiting on probable pitchers", "Pending", "N/A"

    avg_era = (away_stats["ERA"] + home_stats["ERA"]) / 2

    if away_stats["WHIP"] is None or home_stats["WHIP"] is None:
        avg_whip = 1.30
    else:
        avg_whip = (away_stats["WHIP"] + home_stats["WHIP"]) / 2

    score = 50
    reasons = []
    nrfi_signals = 0
    yrfi_signals = 0

    if avg_era <= 3.25:
        score += 5
        reasons.append("Strong starter ERA profile")
        nrfi_signals += 1
    elif avg_era >= 5.00:
        score -= 5
        reasons.append("High starter ERA creates YRFI risk")
        yrfi_signals += 1

    if avg_whip <= 1.10:
        score += 4
        reasons.append("Low WHIP limits early baserunners")
        nrfi_signals += 1
    elif avg_whip >= 1.45:
        score -= 4
        reasons.append("High WHIP creates traffic risk")
        yrfi_signals += 1

    combined_offense = away_offense + home_offense
    if combined_offense >= 17:
        score -= 4
        reasons.append("Elite offense profile increases YRFI risk")
        yrfi_signals += 1
    elif combined_offense <= 8:
        score += 3
        reasons.append("Weak offensive matchup supports NRFI")
        nrfi_signals += 1

    combined_first_inning = away_first_inning + home_first_inning
    if combined_first_inning >= 15:
        score -= 4
        reasons.append("High first-inning scoring risk")
        yrfi_signals += 1
    elif combined_first_inning <= 8:
        score += 3
        reasons.append("Low first-inning scoring risk")
        nrfi_signals += 1

    pitcher_yrfi_values = [
        value for value in [
            safe_float(away_pitcher_yrfi),
            safe_float(home_pitcher_yrfi),
        ] if value is not None
    ]
    if pitcher_yrfi_values:
        avg_pitcher_yrfi = sum(pitcher_yrfi_values) / len(pitcher_yrfi_values)
        if avg_pitcher_yrfi <= 18:
            score += 6
            reasons.append("Low pitcher YRFI rate supports NRFI")
            nrfi_signals += 1
        elif avg_pitcher_yrfi >= 38:
            score -= 6
            reasons.append("High pitcher YRFI rate increases early scoring risk")
            yrfi_signals += 1

    offense_yrfi_values = [
        value for value in [
            safe_float(away_offense_yrfi),
            safe_float(home_offense_yrfi),
        ] if value is not None
    ]
    if offense_yrfi_values:
        avg_offense_yrfi = sum(offense_yrfi_values) / len(offense_yrfi_values)
        if avg_offense_yrfi <= 20:
            score += 5
            reasons.append("Low offense YRFI rate supports NRFI")
            nrfi_signals += 1
        elif avg_offense_yrfi >= 35:
            score -= 5
            reasons.append("High offense YRFI rate creates YRFI risk")
            yrfi_signals += 1

    first_era_values = [
        value for value in [
            safe_float(away_first_era),
            safe_float(home_first_era),
        ] if value is not None
    ]
    if first_era_values:
        avg_first_era = sum(first_era_values) / len(first_era_values)
        if avg_first_era <= 3.00:
            score += 5
            reasons.append("Low first-inning ERA supports NRFI")
            nrfi_signals += 1
        elif avg_first_era >= 6.00:
            score -= 5
            reasons.append("High first-inning ERA creates YRFI risk")
            yrfi_signals += 1

    first_whip_values = [
        value for value in [
            safe_float(away_first_whip),
            safe_float(home_first_whip),
        ] if value is not None
    ]
    if first_whip_values:
        avg_first_whip = sum(first_whip_values) / len(first_whip_values)
        if avg_first_whip <= 1.00:
            score += 5
            reasons.append("Low first-inning WHIP limits traffic")
            nrfi_signals += 1
        elif avg_first_whip >= 1.60:
            score -= 5
            reasons.append("High first-inning WHIP creates traffic risk")
            yrfi_signals += 1

    first_run_values = [
        value for value in [
            safe_float(away_first_run_avg),
            safe_float(home_first_run_avg),
        ] if value is not None
    ]
    if first_run_values:
        avg_first_run = sum(first_run_values) / len(first_run_values)
        if avg_first_run <= 0.30:
            score += 5
            reasons.append("Low first-run average supports NRFI")
            nrfi_signals += 1
        elif avg_first_run >= 0.60:
            score -= 5
            reasons.append("High first-run average creates YRFI risk")
            yrfi_signals += 1

    score = max(20, min(90, score))

    if score >= 75:
        lean = "Strong NRFI"
    elif score >= 65:
        lean = "NRFI"
    elif score >= 50:
        lean = "Pass"
    elif score < 40:
        lean = "Strong YRFI"
    else:
        lean = "YRFI"

    if away_stats["ERA"] < home_stats["ERA"] and away_offense >= home_offense:
        f5_edge = "Away F5 Lean"
    elif home_stats["ERA"] < away_stats["ERA"] and home_offense >= away_offense:
        f5_edge = "Home F5 Lean"
    else:
        f5_edge = "F5 Pass"

    confidence = calculate_factor_confidence(nrfi_signals, yrfi_signals)

    summary = "; ".join(reasons) if reasons else "Neutral profile"

    return round(score, 1), lean, summary, f5_edge, confidence


def generate_recommendation(lean, f5_edge, away_bullpen, home_bullpen):
    notes = []

    if lean in ["Strong NRFI", "NRFI"]:
        notes.append(lean)

    if lean in ["Strong YRFI", "YRFI"]:
        notes.append("YRFI Look")

    if f5_edge != "F5 Pass":
        notes.append(f5_edge)

    if away_bullpen >= 8:
        notes.append("Away Bullpen Risk")

    if home_bullpen >= 8:
        notes.append("Home Bullpen Risk")

    return " / ".join(notes) if notes else "Pass"


def calculate_edge_score(nrfi_score, confidence, away_bullpen, home_bullpen):
    if nrfi_score is None:
        return None

    edge_score = nrfi_score

    if away_bullpen >= 8:
        edge_score += 2

    if home_bullpen >= 8:
        edge_score += 2

    return round(edge_score, 1)


def add_offensive_edge_points(away_score, home_score, away_value, home_value, weight, cap):
    away_value = safe_float(away_value)
    home_value = safe_float(home_value)

    if away_value is None or home_value is None:
        return away_score, home_score

    margin = abs(away_value - home_value)
    points = min(cap, round(margin * weight, 1))

    if points == 0:
        return away_score, home_score

    if away_value > home_value:
        away_score += points
    else:
        home_score += points

    return away_score, home_score


def calculate_offensive_edge(
    away_offense,
    home_offense,
    away_runs_per_game,
    home_runs_per_game,
    away_offense_yrfi,
    home_offense_yrfi,
    away_first_run_avg,
    home_first_run_avg,
):
    away_score = 50
    home_score = 50

    away_score, home_score = add_offensive_edge_points(
        away_score,
        home_score,
        away_offense,
        home_offense,
        weight=2,
        cap=9,
    )
    away_score, home_score = add_offensive_edge_points(
        away_score,
        home_score,
        away_runs_per_game,
        home_runs_per_game,
        weight=4,
        cap=9,
    )
    away_score, home_score = add_offensive_edge_points(
        away_score,
        home_score,
        away_offense_yrfi,
        home_offense_yrfi,
        weight=0.25,
        cap=7.5,
    )
    away_score, home_score = add_offensive_edge_points(
        away_score,
        home_score,
        away_first_run_avg,
        home_first_run_avg,
        weight=10,
        cap=4.5,
    )

    margin = round(abs(away_score - home_score), 1)

    if margin == 0:
        winner = "Even"
    elif away_score > home_score:
        winner = "Away"
    else:
        winner = "Home"

    return round(away_score, 1), round(home_score, 1), winner, margin


def add_starter_edge_points(
    away_score,
    home_score,
    away_value,
    home_value,
    weight,
    cap,
    lower_is_better=False,
):
    away_value = safe_float(away_value)
    home_value = safe_float(home_value)

    if away_value is None or home_value is None:
        return away_score, home_score

    margin = abs(away_value - home_value)
    points = min(cap, round(margin * weight, 1))

    if points == 0:
        return away_score, home_score

    away_has_edge = away_value < home_value if lower_is_better else away_value > home_value

    if away_has_edge:
        away_score += points
    else:
        home_score += points

    return away_score, home_score


def calculate_starter_edge(
    away_era,
    home_era,
    away_whip,
    home_whip,
    away_ip,
    home_ip,
    away_k,
    home_k,
    away_first_era,
    home_first_era,
    away_first_whip,
    home_first_whip,
    away_pitcher_yrfi,
    home_pitcher_yrfi,
):
    away_score = 50
    home_score = 50

    away_score, home_score = add_starter_edge_points(
        away_score,
        home_score,
        away_era,
        home_era,
        weight=2,
        cap=10,
        lower_is_better=True,
    )
    away_score, home_score = add_starter_edge_points(
        away_score,
        home_score,
        away_whip,
        home_whip,
        weight=12,
        cap=10,
        lower_is_better=True,
    )
    away_score, home_score = add_starter_edge_points(
        away_score,
        home_score,
        away_ip,
        home_ip,
        weight=0.08,
        cap=8,
    )
    away_score, home_score = add_starter_edge_points(
        away_score,
        home_score,
        away_k,
        home_k,
        weight=0.12,
        cap=8,
    )
    away_score, home_score = add_starter_edge_points(
        away_score,
        home_score,
        away_first_era,
        home_first_era,
        weight=2,
        cap=8,
        lower_is_better=True,
    )
    away_score, home_score = add_starter_edge_points(
        away_score,
        home_score,
        away_first_whip,
        home_first_whip,
        weight=12,
        cap=8,
        lower_is_better=True,
    )
    away_score, home_score = add_starter_edge_points(
        away_score,
        home_score,
        away_pitcher_yrfi,
        home_pitcher_yrfi,
        weight=0.25,
        cap=8,
        lower_is_better=True,
    )

    margin = round(abs(away_score - home_score), 1)

    if margin == 0:
        winner = "Even"
    elif away_score > home_score:
        winner = "Away"
    else:
        winner = "Home"

    return round(away_score, 1), round(home_score, 1), winner, margin


def add_bullpen_edge_points(away_score, home_score, away_value, home_value, weight, cap):
    away_value = safe_float(away_value)
    home_value = safe_float(home_value)

    if away_value is None or home_value is None:
        return away_score, home_score

    margin = abs(away_value - home_value)
    points = min(cap, round(margin * weight, 1))

    if points == 0:
        return away_score, home_score

    if away_value < home_value:
        away_score += points
    else:
        home_score += points

    return away_score, home_score


def calculate_bullpen_edge(
    away_fatigue,
    home_fatigue,
    away_yesterday_relievers,
    home_yesterday_relievers,
    away_yesterday_pitches,
    home_yesterday_pitches,
    away_three_day_pitches,
    home_three_day_pitches,
    away_back_to_back,
    home_back_to_back,
):
    away_score = 50
    home_score = 50

    away_score, home_score = add_bullpen_edge_points(
        away_score,
        home_score,
        away_fatigue,
        home_fatigue,
        weight=2,
        cap=10,
    )
    away_score, home_score = add_bullpen_edge_points(
        away_score,
        home_score,
        away_yesterday_relievers,
        home_yesterday_relievers,
        weight=2,
        cap=8,
    )
    away_score, home_score = add_bullpen_edge_points(
        away_score,
        home_score,
        away_yesterday_pitches,
        home_yesterday_pitches,
        weight=0.08,
        cap=8,
    )
    away_score, home_score = add_bullpen_edge_points(
        away_score,
        home_score,
        away_three_day_pitches,
        home_three_day_pitches,
        weight=0.04,
        cap=10,
    )
    away_score, home_score = add_bullpen_edge_points(
        away_score,
        home_score,
        away_back_to_back,
        home_back_to_back,
        weight=2,
        cap=8,
    )

    margin = round(abs(away_score - home_score), 1)

    if margin == 0:
        winner = "Even"
    elif away_score > home_score:
        winner = "Away"
    else:
        winner = "Home"

    return round(away_score, 1), round(home_score, 1), winner, margin


def confidence_from_margin(margin):
    margin = safe_float(margin)

    if margin is None:
        return "Pass"
    if margin >= 30:
        return "A+"
    if margin >= 20:
        return "A"
    if margin >= 12:
        return "B"
    if margin >= 7:
        return "C"
    return "Pass"


def cap_confidence(confidence, max_confidence):
    confidence_order = {
        "Pass": 0,
        "No Edge": 0,
        "C": 1,
        "B": 2,
        "A": 3,
        "A+": 4,
    }
    confidence = confidence if confidence in confidence_order else "Pass"
    max_confidence = max_confidence if max_confidence in confidence_order else "Pass"

    if confidence_order[confidence] <= confidence_order[max_confidence]:
        return confidence

    for candidate, rank in confidence_order.items():
        if rank == confidence_order[max_confidence]:
            return candidate

    return "Pass"


def legacy_first_inning_confidence(nrfi_signals, yrfi_signals):
    dominant_signals = max(nrfi_signals, yrfi_signals)
    opposing_signals = min(nrfi_signals, yrfi_signals)

    if dominant_signals == 0:
        return "No Edge"

    if opposing_signals == 0:
        if dominant_signals >= 5:
            return "A+"
        if dominant_signals >= 4:
            return "A"
        if dominant_signals >= 3:
            return "B"
        return "No Edge"

    net_agreement = dominant_signals - opposing_signals
    if dominant_signals >= 5 and net_agreement >= 3:
        return "B"
    if dominant_signals >= 3 and net_agreement >= 2:
        return "No Edge"

    return "No Edge"


def legacy_first_inning_pick_from_score(score):
    if score >= 65:
        return "NRFI"
    if score < 50:
        return "YRFI"
    return "No Edge"


def average_available(values):
    available = [safe_float(value) for value in values]
    available = [value for value in available if value is not None]

    if not available:
        return None

    return sum(available) / len(available)


def weighted_relative_impact(value, neutral, factor_weight, cap):
    value = safe_float(value)
    neutral = safe_float(neutral)

    if value is None or neutral in [None, 0]:
        return 0

    return max(
        -cap,
        min(cap, round(((value - neutral) / neutral) * factor_weight, 1)),
    )


def classify_first_inning_matchup_pressure(
    offense_yrfi,
    opposing_pitcher_yrfi,
    league_yrfi=LEAGUE_YRFI_AVG,
):
    offense_yrfi = safe_float(offense_yrfi)
    opposing_pitcher_yrfi = safe_float(opposing_pitcher_yrfi)
    league_yrfi = safe_float(league_yrfi) or 32
    meaningful_gap = 3

    if offense_yrfi is None or opposing_pitcher_yrfi is None:
        return "Neutral", 0

    strength = round(
        ((offense_yrfi - league_yrfi) + (opposing_pitcher_yrfi - league_yrfi)) / 2,
        1,
    )

    if (
        offense_yrfi >= league_yrfi + meaningful_gap
        and opposing_pitcher_yrfi >= league_yrfi + meaningful_gap
    ):
        return "Strong YRFI", strength
    if offense_yrfi >= league_yrfi and opposing_pitcher_yrfi >= league_yrfi:
        return "YRFI", strength
    if (
        offense_yrfi <= league_yrfi - meaningful_gap
        and opposing_pitcher_yrfi <= league_yrfi - meaningful_gap
    ):
        return "Strong NRFI", strength
    if offense_yrfi <= league_yrfi and opposing_pitcher_yrfi <= league_yrfi:
        return "NRFI", strength

    return "Neutral", strength


def summarize_first_inning_matchup_pressure(away_pressure, home_pressure):
    yrfi_pressures = {"YRFI", "Strong YRFI"}
    nrfi_pressures = {"NRFI", "Strong NRFI"}
    away_yrfi = away_pressure in yrfi_pressures
    home_yrfi = home_pressure in yrfi_pressures
    away_nrfi = away_pressure in nrfi_pressures
    home_nrfi = home_pressure in nrfi_pressures

    if away_yrfi and home_yrfi:
        return "Both sides support YRFI"
    if (away_yrfi and home_pressure == "Neutral") or (home_yrfi and away_pressure == "Neutral"):
        return "One-sided YRFI path"
    if (away_yrfi and home_nrfi) or (home_yrfi and away_nrfi):
        return "Mixed profile; one-sided YRFI path"
    if away_nrfi and home_nrfi:
        return "Both sides suppress first-inning scoring"
    if (away_nrfi and home_pressure == "Neutral") or (home_nrfi and away_pressure == "Neutral"):
        return "Weak NRFI support"

    return "No clear matchup pressure"


def classify_first_inning_signal_type(away_pressure, home_pressure):
    yrfi_pressures = {"YRFI", "Strong YRFI"}
    nrfi_pressures = {"NRFI", "Strong NRFI"}
    away_yrfi = away_pressure in yrfi_pressures
    home_yrfi = home_pressure in yrfi_pressures
    away_nrfi = away_pressure in nrfi_pressures
    home_nrfi = home_pressure in nrfi_pressures

    if away_yrfi and home_yrfi:
        return "two_sided_yrfi"
    if (away_yrfi and home_pressure == "Neutral") or (home_yrfi and away_pressure == "Neutral"):
        return "one_sided_yrfi"
    if (away_yrfi and home_nrfi) or (home_yrfi and away_nrfi):
        return "mixed_yrfi_nrfi"
    if away_nrfi and home_nrfi:
        return "two_sided_nrfi"
    if (away_nrfi and home_pressure == "Neutral") or (home_nrfi and away_pressure == "Neutral"):
        return "one_sided_nrfi"

    return "neutral"


def calculate_first_inning_matchup_modifier(away_pressure, home_pressure):
    summary = summarize_first_inning_matchup_pressure(away_pressure, home_pressure)

    if summary == "Both sides support YRFI":
        return 4
    if summary == "One-sided YRFI path":
        return 2
    if summary == "Mixed profile; one-sided YRFI path":
        if "Strong YRFI" in [away_pressure, home_pressure]:
            return 2
        return 0
    if summary == "Both sides suppress first-inning scoring":
        return -4
    if summary == "Weak NRFI support":
        return -1

    return 0


def calculate_first_inning_decision(
    away_pitcher_yrfi,
    home_pitcher_yrfi,
    away_offense_yrfi,
    home_offense_yrfi,
    away_first_era,
    home_first_era,
    away_first_whip,
    home_first_whip,
    away_first_run_avg,
    home_first_run_avg,
    league_yrfi=LEAGUE_YRFI_AVG,
):
    score = 50
    nrfi_signals = 0
    yrfi_signals = 0

    def add_signal(condition, score_delta, signal_side):
        nonlocal score, nrfi_signals, yrfi_signals
        if not condition:
            return
        score += score_delta
        if signal_side == "NRFI":
            nrfi_signals += 1
        elif signal_side == "YRFI":
            yrfi_signals += 1

    pitcher_yrfi = average_available([away_pitcher_yrfi, home_pitcher_yrfi])
    offense_yrfi = average_available([away_offense_yrfi, home_offense_yrfi])
    first_era = average_available([away_first_era, home_first_era])
    first_whip = average_available([away_first_whip, home_first_whip])
    first_run_avg = average_available([away_first_run_avg, home_first_run_avg])

    add_signal(pitcher_yrfi is not None and pitcher_yrfi <= 18, 6, "NRFI")
    add_signal(pitcher_yrfi is not None and pitcher_yrfi >= 38, -6, "YRFI")
    add_signal(offense_yrfi is not None and offense_yrfi <= 20, 5, "NRFI")
    add_signal(offense_yrfi is not None and offense_yrfi >= 35, -5, "YRFI")
    add_signal(first_era is not None and first_era <= 3.00, 5, "NRFI")
    add_signal(first_era is not None and first_era >= 6.00, -5, "YRFI")
    add_signal(first_whip is not None and first_whip <= 1.00, 5, "NRFI")
    add_signal(first_whip is not None and first_whip >= 1.60, -5, "YRFI")
    add_signal(first_run_avg is not None and first_run_avg <= 0.30, 5, "NRFI")
    add_signal(first_run_avg is not None and first_run_avg >= 0.60, -5, "YRFI")

    score = max(20, min(90, round(score, 1)))
    pick = legacy_first_inning_pick_from_score(score)
    confidence = legacy_first_inning_confidence(nrfi_signals, yrfi_signals)

    if pick == "No Edge" or confidence == "No Edge":
        return "No Edge", "No Edge", score

    return pick, confidence, score


def calculate_f5_decision(
    starter_winner,
    starter_margin,
    offensive_winner,
    offensive_margin,
    away_team,
    home_team,
):
    starter_margin = safe_float(starter_margin) or 0
    offensive_margin = safe_float(offensive_margin) or 0
    pick_side = None
    margin = 0

    def is_no_edge_winner(winner):
        return winner in ["Even", "No Edge", "Pass", None, ""]

    def team_for_side(side):
        if side == "Away":
            return away_team
        if side == "Home":
            return home_team
        return "No Edge"

    if starter_winner == offensive_winner and starter_winner in ["Away", "Home"]:
        pick_side = starter_winner
        margin = round((starter_margin * 0.60) + (offensive_margin * 0.40), 1)
    elif starter_winner in ["Away", "Home"] and is_no_edge_winner(offensive_winner):
        if starter_margin >= 12:
            pick_side = starter_winner
            margin = starter_margin
    elif offensive_winner in ["Away", "Home"] and is_no_edge_winner(starter_winner):
        if offensive_margin >= 16:
            pick_side = offensive_winner
            margin = offensive_margin
    elif starter_winner in ["Away", "Home"] and offensive_winner in ["Away", "Home"]:
        if starter_margin >= 20 and offensive_margin < 7:
            pick_side = starter_winner
            margin = starter_margin
        elif offensive_margin >= 20 and starter_margin < 7:
            pick_side = offensive_winner
            margin = offensive_margin

    margin = round(max(0, margin), 1)
    confidence = confidence_from_margin(margin)

    if pick_side is None or confidence == "Pass":
        return "No Edge", "No Edge", margin

    return team_for_side(pick_side), confidence, margin


def calculate_full_game_decision(
    starter_winner,
    starter_margin,
    offensive_winner,
    offensive_margin,
    bullpen_winner,
    bullpen_margin,
    away_starter_edge,
    home_starter_edge,
    away_offensive_edge,
    home_offensive_edge,
    away_bullpen_edge,
    home_bullpen_edge,
    away_team,
    home_team,
):
    away_starter_edge = safe_float(away_starter_edge) or 50
    home_starter_edge = safe_float(home_starter_edge) or 50
    away_offensive_edge = safe_float(away_offensive_edge) or 50
    home_offensive_edge = safe_float(home_offensive_edge) or 50
    away_bullpen_edge = safe_float(away_bullpen_edge) or 50
    home_bullpen_edge = safe_float(home_bullpen_edge) or 50

    away_score = round(
        (away_starter_edge * 0.35)
        + (away_offensive_edge * 0.30)
        + (away_bullpen_edge * 0.30),
        1,
    )
    home_score = round(
        (home_starter_edge * 0.35)
        + (home_offensive_edge * 0.30)
        + (home_bullpen_edge * 0.30),
        1,
    )

    if away_score > home_score:
        winner = "Away"
        winner_name = away_team
        margin = round(away_score - home_score, 1)
    elif home_score > away_score:
        winner = "Home"
        winner_name = home_team
        margin = round(home_score - away_score, 1)
    else:
        return "No Edge", "No Edge", 0, 0, "No Edge"

    agreement = sum(
        1
        for pillar_winner in [starter_winner, offensive_winner, bullpen_winner]
        if pillar_winner == winner
    )
    edge_label = f"{winner_name} +{margin:g}"
    confidence = confidence_from_margin(margin)

    if confidence == "Pass":
        return "No Edge", "No Edge", margin, agreement, edge_label
    if agreement >= 2:
        return winner_name, confidence, margin, agreement, edge_label
    if agreement == 1 and margin >= 20:
        return winner_name, confidence, margin, agreement, edge_label

    return "No Edge", "No Edge", margin, agreement, edge_label


MODEL_REQUIRED_COLUMNS = [
    "Game",
    "Game Time",
    "Status",
    "First Inning Pick",
    "First Inning Confidence",
    "First Inning Score",
    "F5 Pick",
    "F5 Confidence",
    "F5 Score",
    "Full Game Pick",
    "Full Game Confidence",
    "Full Game Score",
    "Full Game Agreement",
    "Away Starter Edge",
    "Home Starter Edge",
    "Starter Edge Winner",
    "Starter Edge Margin",
    "Away Offensive Edge",
    "Home Offensive Edge",
    "Offensive Edge Winner",
    "Offensive Edge Margin",
    "Away Bullpen Edge",
    "Home Bullpen Edge",
    "Bullpen Edge Winner",
    "Bullpen Edge Margin",
    "Probable Pitcher Status",
    "Pitcher 1st Inning Data Status",
    "Bullpen Data Status",
    "Game Result Status",
    "Model Data Quality",
    "Model Data Quality Notes",
]

FIRST_INNING_ALLOWED_PICKS = {"YRFI", "NRFI", "No Edge"}
MODEL_ALLOWED_CONFIDENCE = {"A+", "A", "B", "C", "No Edge"}
SIDE_ALLOWED_WINNERS = {"Away", "Home", "Even", "No Edge"}
LEGACY_OUTPUT_TERMS = [
    "Pass",
    "YRFI Yes",
    "NRFI Yes",
    "Away F5",
    "Home F5",
    "Away Full Game",
    "Home Full Game",
]

# Kept for compatibility/debugging only. Product UI should use the V2 columns:
# First Inning Pick, F5 Pick, Full Game Pick, and Market Watch display logic.
LEGACY_INTERNAL_COLUMNS = [
    "Recommendation",
    "Confidence",
    "Edge Score",
    "NRFI Score",
    "Lean",
    "F5 Edge",
    "Agent Notes",
]


def parse_game_teams(game_label):
    if not isinstance(game_label, str) or " @ " not in game_label:
        return None, None

    away_team, home_team = game_label.split(" @ ", 1)
    return away_team.strip(), home_team.strip()


def validate_model_contract(df):
    if df.empty:
        return df

    missing_columns = [
        column for column in MODEL_REQUIRED_COLUMNS
        if column not in df.columns
    ]
    if missing_columns:
        raise KeyError(
            "Model contract missing required columns: "
            + ", ".join(missing_columns)
        )

    errors = []

    for index, row in df.iterrows():
        game = row.get("Game", f"row {index}")
        away_team, home_team = parse_game_teams(game)
        allowed_team_picks = {"No Edge"}
        if away_team:
            allowed_team_picks.add(away_team)
        if home_team:
            allowed_team_picks.add(home_team)

        first_pick = row.get("First Inning Pick")
        if first_pick not in FIRST_INNING_ALLOWED_PICKS:
            errors.append(f"{game}: invalid First Inning Pick '{first_pick}'")

        for pick_column in ["F5 Pick", "Full Game Pick"]:
            pick = row.get(pick_column)
            if pick not in allowed_team_picks:
                errors.append(f"{game}: invalid {pick_column} '{pick}'")

        for confidence_column in [
            "First Inning Confidence",
            "F5 Confidence",
            "Full Game Confidence",
        ]:
            confidence = row.get(confidence_column)
            if confidence not in MODEL_ALLOWED_CONFIDENCE:
                errors.append(f"{game}: invalid {confidence_column} '{confidence}'")

        for winner_column in [
            "Starter Edge Winner",
            "Offensive Edge Winner",
            "Bullpen Edge Winner",
        ]:
            winner = row.get(winner_column)
            if winner not in SIDE_ALLOWED_WINNERS:
                errors.append(f"{game}: invalid {winner_column} '{winner}'")

        for output_column in [
            "First Inning Pick",
            "F5 Pick",
            "Full Game Pick",
        ]:
            output = str(row.get(output_column, ""))
            for legacy_term in LEGACY_OUTPUT_TERMS:
                if legacy_term in output:
                    errors.append(
                        f"{game}: legacy term '{legacy_term}' found in {output_column}"
                    )

    if errors:
        error_preview = "\n".join(errors[:20])
        if len(errors) > 20:
            error_preview += f"\n... {len(errors) - 20} more validation errors"
        raise ValueError("Model contract validation failed:\n" + error_preview)

    return df


def probable_pitcher_status(away_pitcher_id, home_pitcher_id):
    if away_pitcher_id and home_pitcher_id:
        return "Confirmed"
    if away_pitcher_id or home_pitcher_id:
        return "Partial"
    return "Missing"


def pitcher_first_inning_data_status(away_first_stats, home_first_stats):
    sources = [
        str(away_first_stats.get("1st Split Source", "Unavailable")),
        str(home_first_stats.get("1st Split Source", "Unavailable")),
    ]

    if all(source == "MLB actual split" for source in sources):
        return "Actual Split"
    if any(source == "MLB actual split" for source in sources):
        return "Partial Actual Split"
    if all(source == "Estimated" for source in sources):
        return "Estimated"
    if any(source == "Estimated" for source in sources):
        return "Partial Estimated"
    return "Missing"


def bullpen_data_status(away_bullpen_data, home_bullpen_data):
    core_bullpen_fields = [
        "Last 3 Days Pitches",
        "Last 3 Days Relievers",
        "Back-to-Back Arms",
    ]

    def complete(data):
        return all(data.get(field) != UNAVAILABLE for field in core_bullpen_fields)

    away_complete = complete(away_bullpen_data)
    home_complete = complete(home_bullpen_data)

    if away_complete and home_complete:
        return "Complete"
    if away_complete or home_complete:
        return "Partial"
    return "Missing"


def game_result_status(status):
    sort_value = game_status_sort_value(status)
    if sort_value == 0:
        return "Pre-Game"
    if sort_value == 1:
        return "In Progress"
    return "Final"


def model_data_quality_status(
    pitcher_status,
    first_inning_status,
    bullpen_status,
):
    notes = []

    if pitcher_status == "Missing":
        notes.append("Probable pitchers missing")
    elif pitcher_status == "Partial":
        notes.append("One probable pitcher missing")

    if first_inning_status in ["Missing", "Partial Estimated"]:
        notes.append("Pitcher first-inning data limited")
    elif first_inning_status == "Estimated":
        notes.append("Pitcher first-inning data estimated")

    if bullpen_status == "Missing":
        notes.append("Bullpen workload data missing")

    if pitcher_status == "Missing" or first_inning_status == "Missing":
        quality = "Poor"
    elif notes:
        quality = "Limited"
    else:
        quality = "Good"

    return quality, "; ".join(notes) if notes else "All core model inputs available"


def get_today_games(selected_date=None, timezone_name="America/New_York"):
    profile = {}
    total_start = perf_counter()
    slate_date = selected_date or date.today().isoformat()
    season = int(str(slate_date)[0:4])

    url = (
        "https://statsapi.mlb.com/api/v1/schedule"
        f"?sportId=1&date={slate_date}&hydrate=probablePitcher,linescore"
    )

    data = None
    step_start = perf_counter()
    for attempt in range(3):
        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            data = response.json()
            break
        except Exception:
            if attempt == 2:
                return pd.DataFrame()
            sleep(1 + attempt)
    profile_add(profile, "schedule/probable pitchers", perf_counter() - step_start)

    step_start = perf_counter()
    team_records = get_team_records(season)
    profile_add(profile, "team records", perf_counter() - step_start)
    last_5_cache = {}
    games = []

    for day in data.get("dates", []):
        for game in day.get("games", []):
            away_side = game["teams"]["away"]
            home_side = game["teams"]["home"]
            game_date = game.get("gameDate", "")
            game_status = game["status"]["detailedState"]
            linescore = game.get("linescore", {})

            away_team = away_side["team"]["name"]
            home_team = home_side["team"]["name"]
            away_team_id = away_side["team"].get("id")
            home_team_id = home_side["team"].get("id")

            if away_team_id not in last_5_cache:
                step_start = perf_counter()
                last_5_cache[away_team_id] = get_team_last_5_results(away_team_id, away_team, slate_date)
                profile_add(profile, "last 5 team results", perf_counter() - step_start)
            if home_team_id not in last_5_cache:
                step_start = perf_counter()
                last_5_cache[home_team_id] = get_team_last_5_results(home_team_id, home_team, slate_date)
                profile_add(profile, "last 5 team results", perf_counter() - step_start)

            away_record = format_team_record(
                away_side,
                team_records.get(away_team, UNAVAILABLE),
            )
            home_record = format_team_record(
                home_side,
                team_records.get(home_team, UNAVAILABLE),
            )
            away_runs_per_game = get_team_runs_per_game(team_records, away_team)
            home_runs_per_game = get_team_runs_per_game(team_records, home_team)

            away_offense = get_team_offense_score(away_team)
            home_offense = get_team_offense_score(home_team)

            away_first_inning = get_first_inning_risk(away_team)
            home_first_inning = get_first_inning_risk(home_team)

            away_first_live = get_live_first_inning_stats(away_team)
            home_first_live = get_live_first_inning_stats(home_team)

            away_bullpen = get_bullpen_fatigue_score(away_team)
            home_bullpen = get_bullpen_fatigue_score(home_team)

            away_bullpen_data = get_bullpen_data(away_team)
            home_bullpen_data = get_bullpen_data(home_team)

            away_pitcher_data = game["teams"]["away"].get("probablePitcher", {})
            home_pitcher_data = game["teams"]["home"].get("probablePitcher", {})

            away_pitcher_id = away_pitcher_data.get("id")
            home_pitcher_id = home_pitcher_data.get("id")

            away_pitcher = away_pitcher_data.get("fullName", UNAVAILABLE)
            home_pitcher = home_pitcher_data.get("fullName", UNAVAILABLE)
            away_pitcher_throws = get_pitcher_throwing_side(away_pitcher_id)
            home_pitcher_throws = get_pitcher_throwing_side(home_pitcher_id)

            step_start = perf_counter()
            away_stats = get_pitcher_stats(away_pitcher_id, season)
            home_stats = get_pitcher_stats(home_pitcher_id, season)
            profile_add(profile, "pitcher season/recent stats", perf_counter() - step_start)

            step_start = perf_counter()
            away_pitcher_first = get_pitcher_first_stats(
                away_pitcher_id,
                season
            )

            home_pitcher_first = get_pitcher_first_stats(
                home_pitcher_id,
                season
            )
            profile_add(profile, "pitcher first-inning splits", perf_counter() - step_start)

            step_start = perf_counter()
            pitcher_status = probable_pitcher_status(
                away_pitcher_id,
                home_pitcher_id,
            )
            first_inning_data_status = pitcher_first_inning_data_status(
                away_pitcher_first,
                home_pitcher_first,
            )
            bullpen_status = bullpen_data_status(
                away_bullpen_data,
                home_bullpen_data,
            )
            result_status = game_result_status(game_status)
            model_data_quality, model_data_quality_notes = model_data_quality_status(
                pitcher_status,
                first_inning_data_status,
                bullpen_status,
            )
            profile_add(profile, "data-quality checks", perf_counter() - step_start)

            step_start = perf_counter()
            nrfi_score, lean, summary, f5_edge, confidence = calculate_nrfi_score(
                away_stats,
                home_stats,
                away_offense,
                home_offense,
                away_first_inning,
                home_first_inning,
                away_pitcher_first["Pitcher YRFI %"],
                home_pitcher_first["Pitcher YRFI %"],
                away_first_live["Offense YRFI %"],
                home_first_live["Offense YRFI %"],
                away_pitcher_first["1st ERA"],
                home_pitcher_first["1st ERA"],
                away_pitcher_first["1st WHIP"],
                home_pitcher_first["1st WHIP"],
                away_first_live["1st Run Avg"],
                home_first_live["1st Run Avg"],
            )

            recommendation = generate_recommendation(
                lean,
                f5_edge,
                away_bullpen,
                home_bullpen,
            )

            edge_score = calculate_edge_score(
                nrfi_score,
                confidence,
                away_bullpen,
                home_bullpen,
            )

            (
                away_offensive_edge,
                home_offensive_edge,
                offensive_edge_winner,
                offensive_edge_margin,
            ) = calculate_offensive_edge(
                away_offense,
                home_offense,
                away_runs_per_game,
                home_runs_per_game,
                away_first_live["Offense YRFI %"],
                home_first_live["Offense YRFI %"],
                away_first_live["1st Run Avg"],
                home_first_live["1st Run Avg"],
            )

            (
                away_starter_edge,
                home_starter_edge,
                starter_edge_winner,
                starter_edge_margin,
            ) = calculate_starter_edge(
                away_stats["ERA"],
                home_stats["ERA"],
                away_stats["WHIP"],
                home_stats["WHIP"],
                away_stats["IP"],
                home_stats["IP"],
                away_stats["K"],
                home_stats["K"],
                away_pitcher_first["1st ERA"],
                home_pitcher_first["1st ERA"],
                away_pitcher_first["1st WHIP"],
                home_pitcher_first["1st WHIP"],
                away_pitcher_first["Pitcher YRFI %"],
                home_pitcher_first["Pitcher YRFI %"],
            )

            (
                away_bullpen_edge,
                home_bullpen_edge,
                bullpen_edge_winner,
                bullpen_edge_margin,
            ) = calculate_bullpen_edge(
                away_bullpen,
                home_bullpen,
                away_bullpen_data["Yesterday Relievers"],
                home_bullpen_data["Yesterday Relievers"],
                away_bullpen_data["Yesterday Pitches"],
                home_bullpen_data["Yesterday Pitches"],
                away_bullpen_data["Last 3 Days Pitches"],
                home_bullpen_data["Last 3 Days Pitches"],
                away_bullpen_data["Back-to-Back Arms"],
                home_bullpen_data["Back-to-Back Arms"],
            )

            first_inning_pick, first_inning_confidence, first_inning_score = calculate_first_inning_decision(
                away_pitcher_first["Pitcher YRFI %"],
                home_pitcher_first["Pitcher YRFI %"],
                away_first_live["Offense YRFI %"],
                home_first_live["Offense YRFI %"],
                away_pitcher_first["1st ERA"],
                home_pitcher_first["1st ERA"],
                away_pitcher_first["1st WHIP"],
                home_pitcher_first["1st WHIP"],
                away_first_live["1st Run Avg"],
                home_first_live["1st Run Avg"],
                LEAGUE_YRFI_AVG,
            )

            away_matchup_pressure, away_matchup_strength = classify_first_inning_matchup_pressure(
                away_first_live["Offense YRFI %"],
                home_pitcher_first["Pitcher YRFI %"],
                LEAGUE_YRFI_AVG,
            )
            home_matchup_pressure, home_matchup_strength = classify_first_inning_matchup_pressure(
                home_first_live["Offense YRFI %"],
                away_pitcher_first["Pitcher YRFI %"],
                LEAGUE_YRFI_AVG,
            )
            first_inning_matchup_summary = summarize_first_inning_matchup_pressure(
                away_matchup_pressure,
                home_matchup_pressure,
            )
            first_inning_signal_type = classify_first_inning_signal_type(
                away_matchup_pressure,
                home_matchup_pressure,
            )
            first_inning_matchup_modifier = calculate_first_inning_matchup_modifier(
                away_matchup_pressure,
                home_matchup_pressure,
            )

            f5_pick, f5_confidence, f5_score = calculate_f5_decision(
                starter_edge_winner,
                starter_edge_margin,
                offensive_edge_winner,
                offensive_edge_margin,
                away_team,
                home_team,
            )

            (
                full_game_pick,
                full_game_confidence,
                full_game_score,
                full_game_agreement,
                full_game_edge,
            ) = calculate_full_game_decision(
                starter_edge_winner,
                starter_edge_margin,
                offensive_edge_winner,
                offensive_edge_margin,
                bullpen_edge_winner,
                bullpen_edge_margin,
                away_starter_edge,
                home_starter_edge,
                away_offensive_edge,
                home_offensive_edge,
                away_bullpen_edge,
                home_bullpen_edge,
                away_team,
                home_team,
            )

            profile_add(profile, "model calculations", perf_counter() - step_start)

            step_start = perf_counter()
            games.append({
                "Game Time": format_game_time(game_date, timezone_name),
                "Game Sort Time": game_date,
                "Status Sort": game_status_sort_value(game_status),
                "First Inning Result": build_first_inning_result(linescore, game_status),
                "First Inning Result Compact": build_first_inning_result(linescore, game_status),
                "F5 Result": build_f5_result(linescore, game_status, away_team, home_team),
                "F5 Result Compact": build_f5_result(linescore, game_status, away_team, home_team, compact=True),
                "Full Game Result": build_full_game_result(linescore, game_status, away_team, home_team),
                "Full Game Result Compact": build_full_game_result(linescore, game_status, away_team, home_team, compact=True),
                "Probable Pitcher Status": pitcher_status,
                "Pitcher 1st Inning Data Status": first_inning_data_status,
                "Bullpen Data Status": bullpen_status,
                "Game Result Status": result_status,
                "Model Data Quality": model_data_quality,
                "Model Data Quality Notes": model_data_quality_notes,
                "Game": f"{away_team} @ {home_team}",
                "Recommendation": recommendation,
                "Confidence": confidence,
                "Edge Score": edge_score,
                "NRFI Score": nrfi_score,
                "Lean": lean,
                "F5 Edge": f5_edge,
                "First Inning Pick": first_inning_pick,
                "First Inning Confidence": first_inning_confidence,
                "First Inning Score": first_inning_score,
                "First Inning Signal Type": first_inning_signal_type,
                "F5 Pick": f5_pick,
                "F5 Confidence": f5_confidence,
                "F5 Score": f5_score,
                "Full Game Pick": full_game_pick,
                "Full Game Confidence": full_game_confidence,
                "Full Game Score": full_game_score,
                "Full Game Agreement": full_game_agreement,
                "Full Game Edge": full_game_edge,

                "Away Record": away_record,
                "Home Record": home_record,
                "Away Runs Per Game": away_runs_per_game,
                "Home Runs Per Game": home_runs_per_game,

                "Away Pitcher": away_pitcher,
                "Home Pitcher": home_pitcher,
                "Away Pitcher Throws": away_pitcher_throws,
                "Home Pitcher Throws": home_pitcher_throws,
                "Away Pitcher Record": f'{away_stats["W"]}-{away_stats["L"]}',
                "Home Pitcher Record": f'{home_stats["W"]}-{home_stats["L"]}',
                "Away ERA": away_stats["ERA"],
                "Home ERA": home_stats["ERA"],
                "Away WHIP": away_stats["WHIP"],
                "Home WHIP": home_stats["WHIP"],
                "Away IP": away_stats["IP"],
                "Home IP": home_stats["IP"],
                "Away IP/Start": away_stats["IP/Start"],
                "Home IP/Start": home_stats["IP/Start"],
                "Away K": away_stats["K"],
                "Home K": home_stats["K"],
                "Away Last 7 ERA": away_stats["Last 7 ERA"],
                "Home Last 7 ERA": home_stats["Last 7 ERA"],
                "Away Last 7 WHIP": away_stats["Last 7 WHIP"],
                "Home Last 7 WHIP": home_stats["Last 7 WHIP"],
                "Away Last 7 K/BB": away_stats["Last 7 K/BB"],
                "Home Last 7 K/BB": home_stats["Last 7 K/BB"],
                "Away Last 7 P/IP": away_stats["Last 7 P/IP"],
                "Home Last 7 P/IP": home_stats["Last 7 P/IP"],
                "Away Last 7 OPS": away_stats["Last 7 OPS"],
                "Home Last 7 OPS": home_stats["Last 7 OPS"],
                "Away Last 15 ERA": away_stats["Last 15 ERA"],
                "Home Last 15 ERA": home_stats["Last 15 ERA"],
                "Away Last 15 WHIP": away_stats["Last 15 WHIP"],
                "Home Last 15 WHIP": home_stats["Last 15 WHIP"],
                "Away Last 15 K/BB": away_stats["Last 15 K/BB"],
                "Home Last 15 K/BB": home_stats["Last 15 K/BB"],
                "Away Last 15 P/IP": away_stats["Last 15 P/IP"],
                "Home Last 15 P/IP": home_stats["Last 15 P/IP"],
                "Away Last 15 OPS": away_stats["Last 15 OPS"],
                "Home Last 15 OPS": home_stats["Last 15 OPS"],
                "Away Last 30 ERA": away_stats["Last 30 ERA"],
                "Home Last 30 ERA": home_stats["Last 30 ERA"],
                "Away Last 30 WHIP": away_stats["Last 30 WHIP"],
                "Home Last 30 WHIP": home_stats["Last 30 WHIP"],
                "Away Last 30 K/BB": away_stats["Last 30 K/BB"],
                "Home Last 30 K/BB": home_stats["Last 30 K/BB"],
                "Away Last 30 P/IP": away_stats["Last 30 P/IP"],
                "Home Last 30 P/IP": home_stats["Last 30 P/IP"],
                "Away Last 30 OPS": away_stats["Last 30 OPS"],
                "Home Last 30 OPS": home_stats["Last 30 OPS"],
                "Away Starter Edge": away_starter_edge,
                "Home Starter Edge": home_starter_edge,
                "Starter Edge Winner": starter_edge_winner,
                "Starter Edge Margin": starter_edge_margin,

                "Away Offense": away_offense,
                "Home Offense": home_offense,
                "Away Offensive Edge": away_offensive_edge,
                "Home Offensive Edge": home_offensive_edge,
                "Offensive Edge Winner": offensive_edge_winner,
                "Offensive Edge Margin": offensive_edge_margin,

                "Away 1st Inning Risk": away_first_inning,
                "Home 1st Inning Risk": home_first_inning,
                "Away Offense YRFI %": away_first_live["Offense YRFI %"],
                "Home Offense YRFI %": home_first_live["Offense YRFI %"],
                "Away 1st Run Avg": away_first_live["1st Run Avg"],
                "Home 1st Run Avg": home_first_live["1st Run Avg"],
                "Away 1st Inning Matchup Pressure": away_matchup_pressure,
                "Home 1st Inning Matchup Pressure": home_matchup_pressure,
                "Away 1st Inning Matchup Strength": away_matchup_strength,
                "Home 1st Inning Matchup Strength": home_matchup_strength,
                "1st Inning Matchup Summary": first_inning_matchup_summary,
                "1st Inning Matchup Modifier": first_inning_matchup_modifier,

                "Away Pitcher YRFI %": away_pitcher_first["Pitcher YRFI %"],
                "Home Pitcher YRFI %": home_pitcher_first["Pitcher YRFI %"],
                "League YRFI %": LEAGUE_YRFI_AVG,
                "Away 1st ERA": away_pitcher_first["1st ERA"],
                "Home 1st ERA": home_pitcher_first["1st ERA"],
                "Away 1st WHIP": away_pitcher_first["1st WHIP"],
                "Home 1st WHIP": home_pitcher_first["1st WHIP"],
                "Away 1st IP": away_pitcher_first["1st IP"],
                "Home 1st IP": home_pitcher_first["1st IP"],
                "Away 1st Games": away_pitcher_first["1st Games"],
                "Home 1st Games": home_pitcher_first["1st Games"],
                "Away 1st R": away_pitcher_first["1st R"],
                "Home 1st R": home_pitcher_first["1st R"],
                "Away 1st ER": away_pitcher_first["1st ER"],
                "Home 1st ER": home_pitcher_first["1st ER"],
                "Away 1st H": away_pitcher_first["1st H"],
                "Home 1st H": home_pitcher_first["1st H"],
                "Away 1st BB": away_pitcher_first["1st BB"],
                "Home 1st BB": home_pitcher_first["1st BB"],
                "Away 1st HR": away_pitcher_first["1st HR"],
                "Home 1st HR": home_pitcher_first["1st HR"],
                "Away 1st BF": away_pitcher_first["1st BF"],
                "Home 1st BF": home_pitcher_first["1st BF"],
                "Away 1st Split Source": away_pitcher_first["1st Split Source"],
                "Home 1st Split Source": home_pitcher_first["1st Split Source"],

                "Away Bullpen Fatigue": away_bullpen,
                "Home Bullpen Fatigue": home_bullpen,
                "Away Bullpen Edge": away_bullpen_edge,
                "Home Bullpen Edge": home_bullpen_edge,
                "Bullpen Edge Winner": bullpen_edge_winner,
                "Bullpen Edge Margin": bullpen_edge_margin,
                "Away Last 5 Results": last_5_cache.get(away_team_id, []),
                "Home Last 5 Results": last_5_cache.get(home_team_id, []),
                "Away Bullpen Status": bullpen_label(away_bullpen),
                "Home Bullpen Status": bullpen_label(home_bullpen),
                "Away Yesterday Relievers": away_bullpen_data["Yesterday Relievers"],
                "Home Yesterday Relievers": home_bullpen_data["Yesterday Relievers"],
                "Away Yesterday Pitches": away_bullpen_data["Yesterday Pitches"],
                "Home Yesterday Pitches": home_bullpen_data["Yesterday Pitches"],
                "Away 3 Day Bullpen IP": away_bullpen_data["Last 3 Days IP"],
                "Home 3 Day Bullpen IP": home_bullpen_data["Last 3 Days IP"],
                "Away 3 Day Bullpen Pitches": away_bullpen_data["Last 3 Days Pitches"],
                "Home 3 Day Bullpen Pitches": home_bullpen_data["Last 3 Days Pitches"],
                "Away 3 Day Relievers": away_bullpen_data["Last 3 Days Relievers"],
                "Home 3 Day Relievers": home_bullpen_data["Last 3 Days Relievers"],
                "Away Back-to-Back Arms": away_bullpen_data["Back-to-Back Arms"],
                "Home Back-to-Back Arms": home_bullpen_data["Back-to-Back Arms"],

                "Agent Notes": summary,
                "Status": game_status,
            })
            profile_add(profile, "row assembly", perf_counter() - step_start)

    step_start = perf_counter()
    df = pd.DataFrame(games)
    validate_model_contract(df)
    profile_add(profile, "dataframe validation", perf_counter() - step_start)
    profile_add(profile, "total", perf_counter() - total_start)
    profile_print(profile)
    return df


if __name__ == "__main__":
    df = get_today_games()
    print(df)
