import requests
from datetime import date, timedelta


def safe_int(value):
    try:
        return int(value)
    except Exception:
        return 0


def get_boxscore(game_pk):
    url = f"https://statsapi.mlb.com/api/v1/game/{game_pk}/boxscore"
    try:
        return requests.get(url, timeout=15).json()
    except Exception:
        return {}


def get_recent_bullpen_fatigue(days_back=2):
    fatigue = {}

    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=days_back)

    schedule_url = (
        "https://statsapi.mlb.com/api/v1/schedule"
        f"?sportId=1&startDate={start_date}&endDate={end_date}"
    )

    try:
        schedule = requests.get(schedule_url, timeout=15).json()
    except Exception:
        return {}

    for day in schedule.get("dates", []):
        for game in day.get("games", []):
            game_pk = game.get("gamePk")
            if not game_pk:
                continue

            boxscore = get_boxscore(game_pk)

            for side in ["away", "home"]:
                team_name = (
                    game.get("teams", {})
                    .get(side, {})
                    .get("team", {})
                    .get("name")
                )

                if not team_name:
                    continue

                fatigue.setdefault(team_name, {
                    "relievers_used": 0,
                    "bullpen_pitches": 0,
                })

                team_box = boxscore.get("teams", {}).get(side, {})
                players = team_box.get("players", {})
                pitcher_ids = team_box.get("pitchers", [])

                for pitcher_id in pitcher_ids:
                    player = players.get(f"ID{pitcher_id}", {})
                    pitching = player.get("stats", {}).get("pitching", {})

                    games_started = safe_int(pitching.get("gamesStarted", 0))
                    pitches = safe_int(pitching.get("numberOfPitches", 0))

                    if games_started > 0:
                        continue

                    if pitches <= 0:
                        continue

                    fatigue[team_name]["relievers_used"] += 1
                    fatigue[team_name]["bullpen_pitches"] += pitches

    final_scores = {}

    for team, stats in fatigue.items():
        relievers_used = stats["relievers_used"]
        bullpen_pitches = stats["bullpen_pitches"]

        score = 3

        if relievers_used >= 14:
            score += 4
        elif relievers_used >= 10:
            score += 3
        elif relievers_used >= 7:
            score += 2
        elif relievers_used >= 4:
            score += 1

        if bullpen_pitches >= 240:
            score += 4
        elif bullpen_pitches >= 180:
            score += 3
        elif bullpen_pitches >= 120:
            score += 2
        elif bullpen_pitches >= 70:
            score += 1

        final_scores[team] = max(1, min(10, score))

    return final_scores


if __name__ == "__main__":
    scores = get_recent_bullpen_fatigue()
    print(scores)
    print("Teams found:", len(scores))