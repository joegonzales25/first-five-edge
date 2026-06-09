import requests
from datetime import date, timedelta
from collections import defaultdict


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


def get_recent_bullpen_fatigue(days_back=3):
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

    team_data = defaultdict(lambda: {
        "last_3_days_pitches": 0,
        "yesterday_pitches": 0,
        "yesterday_relievers": 0,
        "pitcher_dates": defaultdict(set),
    })

    yesterday = str(end_date)

    for day in schedule.get("dates", []):
        game_date = day.get("date")

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

                team_box = boxscore.get("teams", {}).get(side, {})
                players = team_box.get("players", {})
                pitcher_ids = team_box.get("pitchers", [])

                for pitcher_id in pitcher_ids:
                    player = players.get(f"ID{pitcher_id}", {})
                    pitching = player.get("stats", {}).get("pitching", {})

                    games_started = safe_int(pitching.get("gamesStarted", 0))
                    pitches = safe_int(pitching.get("numberOfPitches", 0))

                    # Skip starting pitchers
                    if games_started > 0 or pitches <= 0:
                        continue

                    team_data[team_name]["last_3_days_pitches"] += pitches
                    team_data[team_name]["pitcher_dates"][pitcher_id].add(game_date)

                    if game_date == yesterday:
                        team_data[team_name]["yesterday_pitches"] += pitches
                        team_data[team_name]["yesterday_relievers"] += 1

    final_scores = {}

    for team, stats in team_data.items():
        back_to_back_arms = 0

        for _, dates_used in stats["pitcher_dates"].items():
            sorted_dates = sorted(list(dates_used))

            for i in range(1, len(sorted_dates)):
                prev_date = date.fromisoformat(sorted_dates[i - 1])
                curr_date = date.fromisoformat(sorted_dates[i])

                if (curr_date - prev_date).days == 1:
                    back_to_back_arms += 1
                    break

        score = 0

        # Yesterday relievers used
        if stats["yesterday_relievers"] >= 5:
            score += 2
        elif stats["yesterday_relievers"] >= 3:
            score += 1

        # Yesterday bullpen pitches
        if stats["yesterday_pitches"] >= 100:
            score += 3
        elif stats["yesterday_pitches"] >= 70:
            score += 2
        elif stats["yesterday_pitches"] >= 40:
            score += 1

        # Back-to-back arms
        if back_to_back_arms >= 3:
            score += 3
        elif back_to_back_arms == 2:
            score += 2
        elif back_to_back_arms == 1:
            score += 1

        # Last 3 days bullpen pitches
        if stats["last_3_days_pitches"] >= 250:
            score += 3
        elif stats["last_3_days_pitches"] >= 180:
            score += 2
        elif stats["last_3_days_pitches"] >= 120:
            score += 1

        fatigue_score = max(1, min(10, score))

        final_scores[team] = {
            "Fatigue Score": fatigue_score,
            "Yesterday Relievers": stats["yesterday_relievers"],
            "Yesterday Pitches": stats["yesterday_pitches"],
            "Last 3 Days Pitches": stats["last_3_days_pitches"],
            "Back-to-Back Arms": back_to_back_arms,
        }

    return final_scores


if __name__ == "__main__":
    data = get_recent_bullpen_fatigue()
    print(data)
    print("Teams found:", len(data))