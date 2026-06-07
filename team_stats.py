import requests


def get_team_hitting_stats():
    url = (
        "https://statsapi.mlb.com/api/v1/teams/stats"
        "?group=hitting&stats=season&sportIds=1"
    )

    try:
        data = requests.get(url, timeout=10).json()
        splits = data.get("stats", [])[0].get("splits", [])

        team_scores = {}

        for split in splits:
            team_name = split["team"]["name"]
            stat = split["stat"]

            runs = int(stat.get("runs", 0))
            ops = float(stat.get("ops", 0))

            score = 5

            if ops >= 0.780:
                score += 3
            elif ops >= 0.740:
                score += 2
            elif ops >= 0.700:
                score += 1
            elif ops < 0.650:
                score -= 2

            if runs >= 350:
                score += 2
            elif runs >= 300:
                score += 1
            elif runs < 250:
                score -= 1

            team_scores[team_name] = max(1, min(10, score))

        return team_scores

    except Exception:
        return {}