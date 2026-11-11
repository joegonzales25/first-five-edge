"""Completed current-season results available before each CBB matchup."""

import pandas as pd
import requests


def fetch_cbb_team_schedule(team_id, season):
    response = requests.get(
        f"https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/teams/{team_id}/schedule",
        params={"season": int(season), "seasontype": 2}, timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    if str((payload.get("season") or {}).get("year")) != str(int(season)):
        raise ValueError("CBB team schedule returned a different season")
    if not isinstance(payload.get("events"), list):
        raise ValueError("CBB team schedule is missing events")
    return payload["events"]


def recent_team_results(events, team_id, team_name, kickoff, current_game_id):
    cutoff = pd.to_datetime(kickoff, utc=True, errors="coerce")
    if pd.isna(cutoff):
        return []
    results = {}
    for event in events:
        event_id = str(event.get("id") or "")
        when = pd.to_datetime(event.get("date"), utc=True, errors="coerce")
        if not event_id or event_id == str(current_game_id) or pd.isna(when) or when >= cutoff:
            continue
        contest = (event.get("competitions") or [{}])[0]
        status = contest.get("status") or event.get("status") or {}
        if not (status.get("type") or {}).get("completed"):
            continue
        competitors = contest.get("competitors") or []
        own = next((c for c in competitors if str((c.get("team") or {}).get("id")) == str(team_id)), None)
        opponent = next((c for c in competitors if str((c.get("team") or {}).get("id")) != str(team_id)), None)
        if own is None or opponent is None:
            continue
        scores = []
        for competitor in (own, opponent):
            score = competitor.get("score")
            score = score.get("value") if isinstance(score, dict) else score
            score = pd.to_numeric(score, errors="coerce")
            if pd.isna(score) or not 0 <= score < float("inf") or not float(score).is_integer():
                break
            scores.append(int(score))
        if len(scores) != 2 or scores[0] == scores[1]:
            continue
        name = opponent.get("team") or {}
        label = name.get("abbreviation") or name.get("shortDisplayName") or name.get("displayName") or "Opponent"
        venue = "vs (N)" if contest.get("neutralSite") else "@" if own.get("homeAway") == "away" else "vs"
        results[event_id] = {
            "Team": team_name, "Sort Date": when.isoformat(),
            "Date": when.tz_convert("America/New_York").strftime("%m/%d"),
            "Opponent": f"{venue} {label}", "Result": "W" if scores[0] > scores[1] else "L",
            "Score": f"{scores[0]}-{scores[1]}",
        }
    return sorted(results.values(), key=lambda r: r["Sort Date"], reverse=True)[:5]


def attach_cbb_game_history(slate, metadata, loader=fetch_cbb_team_schedule):
    result = slate.copy()
    for side in ("Away", "Home"):
        result[f"{side} Last 5 Results"] = pd.Series([[] for _ in range(len(result))], index=result.index, dtype=object)
    if result.empty or metadata.empty:
        return result
    by_id = {str(row["game_id"]): row for _, row in metadata.iterrows()}
    schedules = {}
    for index, row in result.iterrows():
        info = by_id.get(str(row["Game ID"]))
        if info is None:
            continue
        kickoff = pd.to_datetime(row.get("Sort Date"), utc=True, errors="coerce")
        if pd.isna(kickoff):
            continue
        season = kickoff.year + 1 if kickoff.month >= 10 else kickoff.year
        for side in ("Away", "Home"):
            team_id = info.get(f"{side.lower()}_team_id")
            if not team_id or pd.isna(team_id):
                continue
            key = (str(team_id), season)
            if key not in schedules:
                try:
                    schedules[key] = loader(*key)
                except (requests.RequestException, ValueError):
                    schedules[key] = []
            result.at[index, f"{side} Last 5 Results"] = recent_team_results(
                schedules[key], team_id, row[side], kickoff, row["Game ID"],
            )
    return result
