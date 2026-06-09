import requests
from datetime import date, timedelta


def get_first_inning_stats(days_back=60):
    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=days_back)

    url = (
        "https://statsapi.mlb.com/api/v1/schedule"
        f"?sportId=1&startDate={start_date}&endDate={end_date}"
        "&hydrate=linescore"
    )

    try:
        data = requests.get(url, timeout=20).json()
    except Exception:
        return {}

    stats = {}

    for day in data.get("dates", []):
        for game in day.get("games", []):
            teams = game.get("teams", {})
            linescore = game.get("linescore", {})
            innings = linescore.get("innings", [])

            if not innings:
                continue

            first = innings[0]

            away_team = teams["away"]["team"]["name"]
            home_team = teams["home"]["team"]["name"]

            away_runs = first.get("away", {}).get("runs", 0)
            home_runs = first.get("home", {}).get("runs", 0)

            for team in [away_team, home_team]:
                stats.setdefault(team, {
                    "games": 0,
                    "yrfi_games": 0,
                    "first_runs": 0,
                })

            stats[away_team]["games"] += 1
            stats[home_team]["games"] += 1

            stats[away_team]["first_runs"] += away_runs
            stats[home_team]["first_runs"] += home_runs

            if away_runs > 0:
                stats[away_team]["yrfi_games"] += 1

            if home_runs > 0:
                stats[home_team]["yrfi_games"] += 1

    final = {}

    for team, s in stats.items():
        games = max(s["games"], 1)
        yrfi_pct = round((s["yrfi_games"] / games) * 100, 1)
        runs_avg = round(s["first_runs"] / games, 2)

        final[team] = {
            "Offense YRFI %": yrfi_pct,
            "1st Run Avg": runs_avg,
        }

    return final