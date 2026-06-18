import requests
from datetime import date


UNAVAILABLE = "N/A"


def safe_float(value):
    try:
        return float(value)
    except Exception:
        return None


def get_pitcher_game_log(pitcher_id, season=None):
    if not pitcher_id:
        return []

    season = season or date.today().year

    url = (
        f"https://statsapi.mlb.com/api/v1/people/{pitcher_id}/stats"
        f"?stats=gameLog&group=pitching&season={season}"
    )

    try:
        data = requests.get(url, timeout=15).json()
        return data.get("stats", [])[0].get("splits", [])
    except Exception:
        return []


def get_pitcher_first_inning_split(pitcher_id, season=None):
    if not pitcher_id:
        return {}

    season = season or date.today().year
    url = (
        f"https://statsapi.mlb.com/api/v1/people/{pitcher_id}/stats"
        f"?stats=statSplits&group=pitching&season={season}&sitCodes=i01"
    )

    try:
        data = requests.get(url, timeout=15).json()
        splits = data.get("stats", [])[0].get("splits", [])
        if not splits:
            return {}
        return splits[0].get("stat", {})
    except Exception:
        return {}


def estimate_pitcher_first_inning_stats(pitcher_id, season=None):
    """
    Stable V1.1 placeholder using MLB game logs.

    Note:
    MLB game logs do not directly expose first-inning-only pitcher stats.
    This returns a conservative estimate until we wire true inning-level Statcast data.
    """

    logs = get_pitcher_game_log(pitcher_id, season)

    if not logs:
        return {
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

    starts = 0
    total_era = 0
    total_whip = 0
    valid_games = 0

    for game in logs:
        stat = game.get("stat", {})

        games_started = int(stat.get("gamesStarted", 0))

        if games_started <= 0:
            continue

        era = safe_float(stat.get("era"))
        whip = safe_float(stat.get("whip"))

        starts += 1

        if era is not None and whip is not None:
            total_era += era
            total_whip += whip
            valid_games += 1

    if starts == 0 or valid_games == 0:
        return {
            "Pitcher YRFI %": UNAVAILABLE,
            "1st ERA": UNAVAILABLE,
            "1st WHIP": UNAVAILABLE,
            "1st IP": UNAVAILABLE,
            "1st Games": starts,
            "1st R": UNAVAILABLE,
            "1st ER": UNAVAILABLE,
            "1st H": UNAVAILABLE,
            "1st BB": UNAVAILABLE,
            "1st HR": UNAVAILABLE,
            "1st BF": UNAVAILABLE,
            "1st Split Source": "Estimated",
            "Starts": starts,
        }

    avg_era = total_era / valid_games
    avg_whip = total_whip / valid_games

    # Conservative proxy until true 1st-inning split is added.
    estimated_yrfi = min(55, max(15, round((avg_era * 6) + (avg_whip * 10), 1)))
    estimated_first_era = round(avg_era * 0.85, 2)
    estimated_first_whip = round(avg_whip * 0.90, 2)

    return {
        "Pitcher YRFI %": estimated_yrfi,
        "1st ERA": estimated_first_era,
        "1st WHIP": estimated_first_whip,
        "1st IP": UNAVAILABLE,
        "1st Games": starts,
        "1st R": UNAVAILABLE,
        "1st ER": UNAVAILABLE,
        "1st H": UNAVAILABLE,
        "1st BB": UNAVAILABLE,
        "1st HR": UNAVAILABLE,
        "1st BF": UNAVAILABLE,
        "1st Split Source": "Estimated",
        "Starts": starts,
    }


def get_pitcher_first_inning_stats(pitcher_id, season=None):
    estimated = estimate_pitcher_first_inning_stats(pitcher_id, season)
    actual = get_pitcher_first_inning_split(pitcher_id, season)

    if not actual:
        return estimated

    return {
        **estimated,
        "1st ERA": actual.get("era", estimated["1st ERA"]),
        "1st WHIP": actual.get("whip", estimated["1st WHIP"]),
        "1st IP": actual.get("inningsPitched", UNAVAILABLE),
        "1st Games": actual.get("gamesPlayed", estimated["Starts"]),
        "1st R": actual.get("runs", UNAVAILABLE),
        "1st ER": actual.get("earnedRuns", UNAVAILABLE),
        "1st H": actual.get("hits", UNAVAILABLE),
        "1st BB": actual.get("baseOnBalls", UNAVAILABLE),
        "1st HR": actual.get("homeRuns", UNAVAILABLE),
        "1st BF": actual.get("battersFaced", UNAVAILABLE),
        "1st Split Source": "MLB actual split",
    }


if __name__ == "__main__":
    # Example pitcher id. Replace with any MLB pitcher ID for testing.
    test_pitcher_id = 669373
    data = get_pitcher_first_inning_stats(test_pitcher_id)
    print(data)
