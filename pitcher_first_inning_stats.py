import requests
from datetime import date


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
            "Pitcher YRFI %": "TBD",
            "1st ERA": "TBD",
            "1st WHIP": "TBD",
            "1st BB Avg": "TBD",
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
            "Pitcher YRFI %": "TBD",
            "1st ERA": "TBD",
            "1st WHIP": "TBD",
            "1st BB Avg": "TBD",
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
        "1st BB Avg": "TBD",
        "Starts": starts,
    }


def get_pitcher_first_inning_stats(pitcher_id, season=None):
    return estimate_pitcher_first_inning_stats(pitcher_id, season)


if __name__ == "__main__":
    # Example pitcher id. Replace with any MLB pitcher ID for testing.
    test_pitcher_id = 669373
    data = get_pitcher_first_inning_stats(test_pitcher_id)
    print(data)