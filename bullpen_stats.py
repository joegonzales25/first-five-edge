import requests
from datetime import date, timedelta


def get_recent_bullpen_fatigue():
    fatigue_scores = {}

    end_date = date.today()
    start_date = end_date - timedelta(days=3)

    url = (
        "https://statsapi.mlb.com/api/v1/schedule"
        f"?sportId=1&startDate={start_date}&endDate={end_date}"
        "&hydrate=boxscore"
    )

    try:
        data = requests.get(url, timeout=15).json()

        for day in data.get("dates", []):
            for game in day.get("games", []):
                teams = game.get("teams", {})

                for side in ["away", "home"]:
                    team_name = teams[side]["team"]["name"]

                    if team_name not in fatigue_scores:
                        fatigue_scores[team_name] = 5

        return fatigue_scores

    except Exception:
        return {}