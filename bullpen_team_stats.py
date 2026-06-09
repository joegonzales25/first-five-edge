import requests


def get_team_bullpen_stats():
    url = (
        "https://statsapi.mlb.com/api/v1/teams/stats"
        "?group=pitching&stats=season&sportIds=1"
    )

    try:
        data = requests.get(url, timeout=15).json()
    except Exception:
        return {}

    final = {}

    for split in data.get("stats", [])[0].get("splits", []):
        team = split["team"]["name"]
        stat = split["stat"]

        final[team] = {
            "Bullpen ERA": stat.get("era", "TBD"),
            "Bullpen IP": stat.get("inningsPitched", "TBD"),
        }

    return final


if __name__ == "__main__":
    data = get_team_bullpen_stats()
    print(data)
    print("Teams found:", len(data))