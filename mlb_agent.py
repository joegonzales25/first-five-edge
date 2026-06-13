import requests
import pandas as pd

from datetime import date, datetime
from zoneinfo import ZoneInfo


UNAVAILABLE = "N/A"

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
    from pitcher_first_inning_stats import get_pitcher_first_inning_stats
except Exception:
    get_pitcher_first_inning_stats = None


def safe_float(value):
    try:
        return float(value)
    except Exception:
        return None


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


def get_pitcher_first_stats(pitcher_id, season=None):
    fallback = {
        "Pitcher YRFI %": UNAVAILABLE,
        "1st ERA": UNAVAILABLE,
        "1st WHIP": UNAVAILABLE,
        "Starts": 0,
    }

    if get_pitcher_first_inning_stats is None:
        return fallback

    try:
        return get_pitcher_first_inning_stats(pitcher_id, season)
    except Exception:
        return fallback


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
        display_dt = utc_dt.astimezone(ZoneInfo(timezone_name))
    except Exception:
        display_dt = utc_dt.astimezone(ZoneInfo("America/New_York"))

    return display_dt.strftime("%I:%M %p ET").lstrip("0")


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


def get_pitcher_stats(pitcher_id):
    fallback = {
        "ERA": None,
        "WHIP": None,
        "W": UNAVAILABLE,
        "L": UNAVAILABLE,
        "IP": UNAVAILABLE,
        "K": UNAVAILABLE,
    }

    if not pitcher_id:
        return fallback

    url = (
        f"https://statsapi.mlb.com/api/v1/people/"
        f"{pitcher_id}/stats?stats=season&group=pitching"
    )

    try:
        data = requests.get(url, timeout=10).json()
        stats = data["stats"][0]["splits"][0]["stat"]

        return {
            "ERA": safe_float(stats.get("era")),
            "WHIP": safe_float(stats.get("whip")),
            "W": stats.get("wins", UNAVAILABLE),
            "L": stats.get("losses", UNAVAILABLE),
            "IP": stats.get("inningsPitched", UNAVAILABLE),
            "K": stats.get("strikeOuts", UNAVAILABLE),
        }

    except Exception:
        return fallback


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
        cap=12,
    )
    away_score, home_score = add_offensive_edge_points(
        away_score,
        home_score,
        away_offense_yrfi,
        home_offense_yrfi,
        weight=0.25,
        cap=10,
    )
    away_score, home_score = add_offensive_edge_points(
        away_score,
        home_score,
        away_first_run_avg,
        home_first_run_avg,
        weight=10,
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
):
    score = 50

    for away_value, home_value, neutral, weight, cap in [
        (away_pitcher_yrfi, home_pitcher_yrfi, 32, 0.35, 12),
        (away_offense_yrfi, home_offense_yrfi, 35, 0.25, 10),
        (away_first_era, home_first_era, 3.75, 3, 10),
        (away_first_whip, home_first_whip, 1.15, 16, 10),
        (away_first_run_avg, home_first_run_avg, 0.45, 18, 10),
    ]:
        values = [safe_float(away_value), safe_float(home_value)]
        available = [value for value in values if value is not None]

        if not available:
            continue

        avg_value = sum(available) / len(available)
        impact = max(-cap, min(cap, round((avg_value - neutral) * weight, 1)))
        score += impact

    distance = abs(score - 50)
    confidence = confidence_from_margin(distance * 2)

    if confidence == "Pass":
        return "Pass", "Pass"
    if score >= 56:
        return "YRFI Yes", confidence
    if score <= 44:
        return "NRFI Yes", confidence

    return "Pass", "Pass"


def calculate_f5_decision(
    starter_winner,
    starter_margin,
    offensive_winner,
    offensive_margin,
):
    starter_margin = safe_float(starter_margin) or 0
    offensive_margin = safe_float(offensive_margin) or 0

    if starter_winner == offensive_winner and starter_winner in ["Away", "Home"]:
        margin = starter_margin + offensive_margin
        confidence = confidence_from_margin(margin)

        if confidence == "Pass":
            return "Pass", "Pass"

        return f"{starter_winner} F5", confidence

    if starter_winner in ["Away", "Home"] and offensive_winner == "Even":
        confidence = confidence_from_margin(starter_margin)

        if confidence == "Pass":
            return "Pass", "Pass"

        return f"{starter_winner} F5", confidence

    if offensive_winner in ["Away", "Home"] and starter_winner == "Even":
        confidence = confidence_from_margin(offensive_margin)

        if confidence == "Pass":
            return "Pass", "Pass"

        return f"{offensive_winner} F5", confidence

    return "Pass", "Pass"


def calculate_full_game_decision(
    starter_winner,
    starter_margin,
    offensive_winner,
    offensive_margin,
    bullpen_winner,
    bullpen_margin,
):
    away_score = 0
    home_score = 0
    agreement = {"Away": 0, "Home": 0}

    for winner, margin in [
        (starter_winner, starter_margin),
        (offensive_winner, offensive_margin),
        (bullpen_winner, bullpen_margin),
    ]:
        margin = safe_float(margin) or 0

        if winner == "Away":
            away_score += margin
            agreement["Away"] += 1
        elif winner == "Home":
            home_score += margin
            agreement["Home"] += 1

    margin = round(abs(away_score - home_score), 1)
    confidence = confidence_from_margin(margin)

    if confidence == "Pass":
        return "Pass", "Pass"
    if away_score > home_score and agreement["Away"] >= 2:
        return "Away Full Game", confidence
    if home_score > away_score and agreement["Home"] >= 2:
        return "Home Full Game", confidence

    return "Pass", "Pass"


def get_today_games(selected_date=None):
    slate_date = selected_date or date.today().isoformat()
    season = int(str(slate_date)[0:4])

    url = (
        "https://statsapi.mlb.com/api/v1/schedule"
        f"?sportId=1&date={slate_date}&hydrate=probablePitcher,linescore"
    )

    try:
        data = requests.get(url, timeout=10).json()
    except Exception:
        return pd.DataFrame()

    team_records = get_team_records(season)
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

            away_stats = get_pitcher_stats(away_pitcher_id)
            home_stats = get_pitcher_stats(home_pitcher_id)

            away_pitcher_first = get_pitcher_first_stats(
                away_pitcher_id,
                season
            )

            home_pitcher_first = get_pitcher_first_stats(
                home_pitcher_id,
                season
            )

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

            first_inning_pick, first_inning_confidence = calculate_first_inning_decision(
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

            f5_pick, f5_confidence = calculate_f5_decision(
                starter_edge_winner,
                starter_edge_margin,
                offensive_edge_winner,
                offensive_edge_margin,
            )

            full_game_pick, full_game_confidence = calculate_full_game_decision(
                starter_edge_winner,
                starter_edge_margin,
                offensive_edge_winner,
                offensive_edge_margin,
                bullpen_edge_winner,
                bullpen_edge_margin,
            )

            games.append({
                "Game Time": format_game_time(game_date),
                "Game Sort Time": game_date,
                "Status Sort": game_status_sort_value(game_status),
                "First Inning Result": build_first_inning_result(linescore, game_status),
                "First Inning Result Compact": build_first_inning_result(linescore, game_status),
                "F5 Result": build_f5_result(linescore, game_status, away_team, home_team),
                "F5 Result Compact": build_f5_result(linescore, game_status, away_team, home_team, compact=True),
                "Full Game Result": build_full_game_result(linescore, game_status, away_team, home_team),
                "Full Game Result Compact": build_full_game_result(linescore, game_status, away_team, home_team, compact=True),
                "Game": f"{away_team} @ {home_team}",
                "Recommendation": recommendation,
                "Confidence": confidence,
                "Edge Score": edge_score,
                "NRFI Score": nrfi_score,
                "Lean": lean,
                "F5 Edge": f5_edge,
                "First Inning Pick": first_inning_pick,
                "First Inning Confidence": first_inning_confidence,
                "F5 Pick": f5_pick,
                "F5 Confidence": f5_confidence,
                "Full Game Pick": full_game_pick,
                "Full Game Confidence": full_game_confidence,

                "Away Record": away_record,
                "Home Record": home_record,
                "Away Runs Per Game": away_runs_per_game,
                "Home Runs Per Game": home_runs_per_game,

                "Away Pitcher": away_pitcher,
                "Home Pitcher": home_pitcher,
                "Away Pitcher Record": f'{away_stats["W"]}-{away_stats["L"]}',
                "Home Pitcher Record": f'{home_stats["W"]}-{home_stats["L"]}',
                "Away ERA": away_stats["ERA"],
                "Home ERA": home_stats["ERA"],
                "Away WHIP": away_stats["WHIP"],
                "Home WHIP": home_stats["WHIP"],
                "Away IP": away_stats["IP"],
                "Home IP": home_stats["IP"],
                "Away K": away_stats["K"],
                "Home K": home_stats["K"],
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

                "Away Pitcher YRFI %": away_pitcher_first["Pitcher YRFI %"],
                "Home Pitcher YRFI %": home_pitcher_first["Pitcher YRFI %"],
                "Away 1st ERA": away_pitcher_first["1st ERA"],
                "Home 1st ERA": home_pitcher_first["1st ERA"],
                "Away 1st WHIP": away_pitcher_first["1st WHIP"],
                "Home 1st WHIP": home_pitcher_first["1st WHIP"],

                "Away Bullpen Fatigue": away_bullpen,
                "Home Bullpen Fatigue": home_bullpen,
                "Away Bullpen Edge": away_bullpen_edge,
                "Home Bullpen Edge": home_bullpen_edge,
                "Bullpen Edge Winner": bullpen_edge_winner,
                "Bullpen Edge Margin": bullpen_edge_margin,
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

    return pd.DataFrame(games)


if __name__ == "__main__":
    df = get_today_games()
    print(df)
