import requests
import pandas as pd

from datetime import date
from datetime import datetime


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
    BULLPEN_FATIGUE = get_recent_bullpen_fatigue()
except Exception:
    try:
        from bullpen_data import BULLPEN_FATIGUE
    except Exception:
        BULLPEN_FATIGUE = {}


def get_team_offense_score(team_name):
    return TEAM_OFFENSE.get(team_name, 5)


def get_bullpen_fatigue_score(team_name):
    return BULLPEN_FATIGUE.get(team_name, 5)


def format_game_time(raw_time):
    if not raw_time:
        return "TBD"

    try:
        utc_dt = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
        local_dt = utc_dt.astimezone()
        return local_dt.strftime("%I:%M %p %Z")
    except Exception:
        return raw_time


def get_pitcher_stats(pitcher_id):
    if not pitcher_id:
        return {
            "ERA": None,
            "WHIP": None,
        }

    url = (
        f"https://statsapi.mlb.com/api/v1/people/"
        f"{pitcher_id}/stats?stats=season&group=pitching"
    )

    try:
        data = requests.get(url, timeout=10).json()
        stats = data["stats"][0]["splits"][0]["stat"]

        return {
            "ERA": float(stats.get("era", 0)),
            "WHIP": float(stats.get("whip", 0)),
        }

    except Exception:
        return {
            "ERA": None,
            "WHIP": None,
        }


def calculate_nrfi_score(away_stats, home_stats, away_offense, home_offense):
    if away_stats["ERA"] is None or home_stats["ERA"] is None:
        return None, "Pending", "Waiting on probable pitchers", "Pending", "N/A"

    avg_era = (away_stats["ERA"] + home_stats["ERA"]) / 2
    avg_whip = (away_stats["WHIP"] + home_stats["WHIP"]) / 2
    combined_offense = away_offense + home_offense

    score = 70
    reasons = []

    if avg_era <= 3.00:
        score += 10
        reasons.append("Strong starter ERA profile")
    elif avg_era <= 4.00:
        score += 5
        reasons.append("Solid starter ERA profile")
    elif avg_era >= 5.00:
        score -= 12
        reasons.append("High starter ERA creates YRFI risk")
    elif avg_era >= 4.50:
        score -= 7
        reasons.append("Elevated starter ERA risk")

    if avg_whip <= 1.10:
        score += 8
        reasons.append("Low WHIP limits early baserunners")
    elif avg_whip <= 1.25:
        score += 4
        reasons.append("Good WHIP profile")
    elif avg_whip >= 1.45:
        score -= 10
        reasons.append("High WHIP creates traffic risk")
    elif avg_whip >= 1.35:
        score -= 6
        reasons.append("Elevated WHIP risk")

    if combined_offense >= 17:
        score -= 10
        reasons.append("Elite offensive matchup increases YRFI risk")
    elif combined_offense >= 14:
        score -= 5
        reasons.append("Above-average offenses reduce NRFI confidence")
    elif combined_offense <= 8:
        score += 6
        reasons.append("Weak offensive matchup supports NRFI")

    score = max(35, min(85, score))

    if score >= 68:
        lean = "Strong NRFI"
    elif score >= 60:
        lean = "NRFI"
    elif score <= 48:
        lean = "YRFI"
    else:
        lean = "Pass"

    if away_stats["ERA"] < home_stats["ERA"] and away_offense >= home_offense:
        f5_edge = "Away F5 Lean"
    elif home_stats["ERA"] < away_stats["ERA"] and home_offense >= away_offense:
        f5_edge = "Home F5 Lean"
    else:
        f5_edge = "F5 Pass"

    if score >= 75:
        confidence = "A+"
    elif score >= 68:
        confidence = "A"
    elif score >= 60:
        confidence = "B"
    elif score >= 50:
        confidence = "C"
    else:
        confidence = "D"

    summary = "; ".join(reasons) if reasons else "Neutral starter profile"

    return round(score, 1), lean, summary, f5_edge, confidence


def generate_recommendation(lean, f5_edge, away_bullpen, home_bullpen):
    notes = []

    if lean in ["Strong NRFI", "NRFI"]:
        notes.append(lean)

    if lean == "YRFI":
        notes.append("YRFI Look")

    if f5_edge != "F5 Pass":
        notes.append(f5_edge)

    if away_bullpen >= 7:
        notes.append("Fade Away Bullpen")

    if home_bullpen >= 7:
        notes.append("Fade Home Bullpen")

    if not notes:
        return "Pass"

    return " / ".join(notes)


def get_today_games():
    today = date.today().isoformat()

    url = (
        "https://statsapi.mlb.com/api/v1/schedule"
        f"?sportId=1&date={today}&hydrate=probablePitcher"
    )

    try:
        data = requests.get(url, timeout=10).json()
    except Exception:
        return pd.DataFrame()

    games = []

    for day in data.get("dates", []):
        for game in day.get("games", []):
            away_team = game["teams"]["away"]["team"]["name"]
            home_team = game["teams"]["home"]["team"]["name"]

            game_time = format_game_time(game.get("gameDate", ""))

            away_offense = get_team_offense_score(away_team)
            home_offense = get_team_offense_score(home_team)

            away_bullpen = get_bullpen_fatigue_score(away_team)
            home_bullpen = get_bullpen_fatigue_score(home_team)

            away_pitcher_data = game["teams"]["away"].get("probablePitcher", {})
            home_pitcher_data = game["teams"]["home"].get("probablePitcher", {})

            away_pitcher = away_pitcher_data.get("fullName", "TBD")
            home_pitcher = home_pitcher_data.get("fullName", "TBD")

            away_stats = get_pitcher_stats(away_pitcher_data.get("id"))
            home_stats = get_pitcher_stats(home_pitcher_data.get("id"))

            nrfi_score, lean, summary, f5_edge, confidence = calculate_nrfi_score(
                away_stats,
                home_stats,
                away_offense,
                home_offense,
            )

            recommendation = generate_recommendation(
                lean,
                f5_edge,
                away_bullpen,
                home_bullpen,
            )

            games.append({
                "Game Time": game_time,
                "Game": f"{away_team} @ {home_team}",
                "Recommendation": recommendation,
                "Confidence": confidence,
                "NRFI Score": nrfi_score,
                "Lean": lean,
                "F5 Edge": f5_edge,
                "Away Pitcher": away_pitcher,
                "Home Pitcher": home_pitcher,
                "Away ERA": away_stats["ERA"],
                "Home ERA": home_stats["ERA"],
                "Away WHIP": away_stats["WHIP"],
                "Home WHIP": home_stats["WHIP"],
                "Away Offense": away_offense,
                "Home Offense": home_offense,
                "Away Bullpen Fatigue": away_bullpen,
                "Home Bullpen Fatigue": home_bullpen,
                "Agent Notes": summary,
                "Status": game["status"]["detailedState"],
            })

    return pd.DataFrame(games)


if __name__ == "__main__":
    df = get_today_games()
    print(df)