import requests
from datetime import date, timedelta
from collections import defaultdict


def safe_int(value):
    try:
        return int(value)
    except Exception:
        return 0


def innings_to_outs(value):
    if value in [None, ""]:
        return 0

    whole, _, partial = str(value).partition(".")
    outs = safe_int(whole) * 3

    if partial:
        outs += min(safe_int(partial[0]), 2)

    return outs


def outs_to_innings(outs):
    innings = outs // 3
    partial = outs % 3
    return f"{innings}.{partial}" if partial else str(innings)


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
        "last_3_days_outs": 0,
        "reliever_appearances": 0,
        "pitcher_dates": defaultdict(set),
    })

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
                    outs = innings_to_outs(pitching.get("inningsPitched", 0))

                    # Skip starting pitchers
                    if games_started > 0 or pitches <= 0:
                        continue

                    team_data[team_name]["last_3_days_pitches"] += pitches
                    team_data[team_name]["last_3_days_outs"] += outs
                    team_data[team_name]["reliever_appearances"] += 1
                    team_data[team_name]["pitcher_dates"][pitcher_id].add(game_date)

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
        last_3_days_innings = stats["last_3_days_outs"] / 3

        # Last 3 days bullpen innings
        if last_3_days_innings >= 12:
            score += 3
        elif last_3_days_innings >= 9:
            score += 2
        elif last_3_days_innings >= 6:
            score += 1

        # Last 3 days bullpen pitches
        if stats["last_3_days_pitches"] >= 250:
            score += 3
        elif stats["last_3_days_pitches"] >= 180:
            score += 2
        elif stats["last_3_days_pitches"] >= 120:
            score += 1

        # Last 3 days reliever appearances
        if stats["reliever_appearances"] >= 12:
            score += 3
        elif stats["reliever_appearances"] >= 9:
            score += 2
        elif stats["reliever_appearances"] >= 6:
            score += 1

        # Back-to-back arms
        if back_to_back_arms >= 3:
            score += 3
        elif back_to_back_arms == 2:
            score += 2
        elif back_to_back_arms == 1:
            score += 1

        fatigue_score = max(1, min(10, score))

        final_scores[team] = {
            "Fatigue Score": fatigue_score,
            "Last 3 Days IP": outs_to_innings(stats["last_3_days_outs"]),
            "Last 3 Days Pitches": stats["last_3_days_pitches"],
            "Last 3 Days Relievers": stats["reliever_appearances"],
            "Back-to-Back Arms": back_to_back_arms,
        }

    return final_scores


if __name__ == "__main__":
    data = get_recent_bullpen_fatigue()
    print(data)
    print("Teams found:", len(data))
