import requests
import pandas as pd

from datetime import date, datetime


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
    BULLPEN_FATIGUE = get_recent_bullpen_fatigue(days_back=2)
except Exception:
    try:
        from bullpen_data import BULLPEN_FATIGUE
    except Exception:
        BULLPEN_FATIGUE = {}


try:
    from first_inning_data import FIRST_INNING_RISK
except Exception:
    FIRST_INNING_RISK = {}


def get_team_offense_score(team_name):
    return TEAM_OFFENSE.get(team_name, 5)


def get_first_inning_risk(team_name):
    return FIRST_INNING_RISK.get(team_name, 5)


def get_bullpen_fatigue_score(team_name):
    return BULLPEN_FATIGUE.get(team_name, 5)


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
        return {"ERA": None, "WHIP": None}

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
        return {"ERA": None, "WHIP": None}


def calculate_nrfi_score(
    away_stats,
    home_stats,
    away_offense,
    home_offense,
    away_first_inning,
    home_first_inning,
):
    if away_stats["ERA"] is None or home_stats["ERA"] is None:
        return None, "Pending", "Waiting on probable pitchers", "Pending", "N/A"

    avg_era = (away_stats["ERA"] + home_stats["ERA"]) / 2
    avg_whip = (away_stats["WHIP"] + home_stats["WHIP"]) / 2
    combined_offense = away_offense + home_offense
    combined_first_inning = away_first_inning + home_first_inning

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
        score -= 8
        reasons.append("Elite offense profile increases YRFI risk")
    elif combined_offense >= 14:
        score -= 5
        reasons.append("Above-average offenses reduce NRFI confidence")
    elif combined_offense <= 8:
        score += 5
        reasons.append("Weak offensive matchup supports NRFI")

    if combined_first_inning >= 15:
        score -= 10
        reasons.append("High first-inning scoring risk")
    elif combined_first_inning >= 12:
        score -= 5
        reasons.append("Moderate first-inning scoring risk")
    elif combined_first_inning <= 8:
        score += 5
        reasons.append("Low first-inning scoring risk")

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

    summary = "; ".join(reasons) if reasons else "Neutral profile"

    return round(score, 1), lean, summary, f5_edge, confidence


def generate_recommendation(lean, f5_edge, away_bullpen, home_bullpen):
    notes = []

    if lean in ["Strong NRFI", "NRFI"]:
        notes.append(lean)

    if lean == "YRFI":
        notes.append("YRFI Look")

    if f5_edge != "F5 Pass":
        notes.append(f5_edge)

    if away_bullpen >= 8:
        notes.append("Fade Away Bullpen")

    if home_bullpen >= 8:
        notes.append("Fade Home Bullpen")

    return " / ".join(notes) if notes else "Pass"


def calculate_edge_score(nrfi_score, confidence, away_bullpen, home_bullpen):
    if nrfi_score is None:
        return None

    edge_score = nrfi_score

    if confidence == "A+":
        edge_score += 10
    elif confidence == "A":
        edge_score += 7
    elif confidence == "B":
        edge_score += 3

    if away_bullpen >= 8:
        edge_score += 2

    if home_bullpen >= 8:
        edge_score += 2

    return round(edge_score, 1)


def get_today_games(selected_date=None):
    slate_date = selected_date or date.today().isoformat()

    url = (
        "https://statsapi.mlb.com/api/v1/schedule"
        f"?sportId=1&date={slate_date}&hydrate=probablePitcher"
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

            away_offense = get_team_offense_score(away_team)
            home_offense = get_team_offense_score(home_team)

            away_first_inning = get_first_inning_risk(away_team)
            home_first_inning = get_first_inning_risk(home_team)

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
                away_first_inning,
                home_first_inning,
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

            games.append({
                "Game Time": format_game_time(game.get("gameDate", "")),
                "Game": f"{away_team} @ {home_team}",
                "Recommendation": recommendation,
                "Confidence": confidence,
                "Edge Score": edge_score,
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
                "Away 1st Inning Risk": away_first_inning,
                "Home 1st Inning Risk": home_first_inning,
                "Away Bullpen Fatigue": away_bullpen,
                "Home Bullpen Fatigue": home_bullpen,
                "Away Bullpen Status": bullpen_label(away_bullpen),
                "Home Bullpen Status": bullpen_label(home_bullpen),
                "Agent Notes": summary,
                "Status": game["status"]["detailedState"],
            })

    return pd.DataFrame(games)


if __name__ == "__main__":
    df = get_today_games()
    print(df)