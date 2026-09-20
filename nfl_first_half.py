"""Experimental first-half sides, trained only on earlier completed games."""

from datetime import timedelta

import numpy as np
import pandas as pd
import requests

VERSION = "0.1.0-watch"
URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
ALIASES = {"LAR": "LA", "WSH": "WAS"}


def normalize_events(payload):
    records = []
    for event in payload.get("events", []):
        for contest in event.get("competitions", []):
            status = contest.get("status", event.get("status", {}))
            if not (status.get("type", {}).get("completed") or
                    status.get("period", 0) >= 3 or
                    status.get("type", {}).get("name") == "STATUS_HALFTIME"):
                continue
            teams = {c.get("homeAway"): c for c in contest.get("competitors", [])}
            values = {}
            for side in ("away", "home"):
                competitor = teams.get(side, {})
                quarters = competitor.get("linescores", [])
                if len(quarters) < 2:
                    break
                try:
                    points = [float(q["value"]) for q in quarters[:2]]
                    if not all(np.isfinite(p) and p >= 0 and p.is_integer() for p in points):
                        break
                except (KeyError, TypeError, ValueError):
                    break
                name = competitor.get("team", {}).get("abbreviation")
                values[side] = ALIASES.get(name, name)
                values[side + "_half"] = int(sum(points))
            else:
                kickoff = pd.to_datetime(event.get("date"), utc=True, errors="coerce")
                if pd.notna(kickoff) and values["away"] and values["home"]:
                    records.append({**values, "kickoff": kickoff,
                                    "completed": bool(status.get("type", {}).get("completed")),
                                    "neutral": bool(contest.get("neutralSite"))})
    return records


def load_history(season, through_week):
    records = {}
    with requests.Session() as session:
        for year, last_week in ((season - 1, 18), (season, through_week)):
            for week in range(1, min(18, last_week) + 1):
                response = session.get(URL, params={"dates": year, "seasontype": 2,
                                                   "week": week, "limit": 100}, timeout=15)
                response.raise_for_status()
                payload = response.json()
                # Reject an endpoint silently returning the current week.
                if int(payload.get("season", {}).get("year", -1)) != year or int(payload.get("week", {}).get("number", -1)) != week:
                    raise ValueError("NFL first-half source returned a different season/week")
                for record in normalize_events(payload):
                    records[(record["kickoff"], record["away"], record["home"])] = record
    if not records:
        raise ValueError("NFL first-half source returned no usable quarter scores")
    return list(records.values())


def predict(away, home, kickoff, history, neutral=False):
    kickoff = pd.to_datetime(kickoff, utc=True, errors="coerce")
    empty = {"First Half Version": VERSION, "First Half Pick": None,
             "First Half Margin": None, "First Half Tracking Segment": "No Edge",
             "Early Edge": "Not Available", "First Half History Games": 0}
    if pd.isna(kickoff):
        return empty
    eligible = [r for r in history if r["completed"] and
                r["kickoff"] + timedelta(hours=6) < kickoff and
                r["kickoff"] >= kickoff - timedelta(days=550)]
    counts = [sum(team in (r["away"], r["home"]) for r in eligible) for team in (away, home)]
    empty["First Half History Games"] = min(counts)
    if min(counts) < 8:
        return empty
    teams = sorted({t for r in eligible for t in (r["away"], r["home"])})
    indices = {t: i for i, t in enumerate(teams)}
    design, targets = [], []
    for r in eligible:
        vector = np.zeros(len(teams) + 1)
        vector[indices[r["home"]]] = 1
        vector[indices[r["away"]]] = -1
        vector[-1] = 0 if r["neutral"] else 1
        weight = np.sqrt(0.5 ** ((kickoff - r["kickoff"]).days / 180))
        design.append(vector * weight)
        targets.append((r["home_half"] - r["away_half"]) * weight)
    x = np.asarray(design)
    coefficients = np.linalg.solve(x.T @ x + np.eye(x.shape[1]) * 4, x.T @ targets)
    margin = float(coefficients[indices[home]] - coefficients[indices[away]] +
                   (0 if neutral else coefficients[-1]))
    pick = home if margin > 0 else away
    tracked = abs(margin) >= 2
    return {**empty, "First Half Margin": round(margin, 2),
            "First Half Pick": pick if tracked else None,
            "First Half Tracking Segment": "Watch" if tracked else "No Edge",
            "Early Edge": f"{pick} Watch" if tracked else "Pass"}


def attach_first_half(slate, history):
    slate = slate.copy()
    for index, row in slate.iterrows():
        kickoff = pd.to_datetime(row.get("Scheduled Kickoff"), utc=True, errors="coerce")
        values = predict(row["Away"], row["Home"], kickoff, history,
                         neutral=bool(row.get("Neutral Site", False)))
        matches = [r for r in history if r["away"] == row["Away"] and r["home"] == row["Home"]
                   and pd.notna(kickoff) and abs((r["kickoff"] - kickoff).total_seconds()) < 3600]
        if len(matches) == 1:
            values.update({"Away First Half": matches[0]["away_half"],
                           "Home First Half": matches[0]["home_half"]})
        for key, value in values.items():
            if key not in slate:
                slate[key] = pd.Series(None, index=slate.index, dtype=object)
            slate.at[index, key] = value
    return slate


def backtest(history, season):
    """Chronological holdout report; ties are excluded from accuracy."""
    rows = []
    for game in sorted(history, key=lambda r: r["kickoff"]):
        season_year = game["kickoff"].year if game["kickoff"].month >= 3 else game["kickoff"].year - 1
        if not game["completed"] or season_year != season:
            continue
        prediction = predict(game["away"], game["home"], game["kickoff"], history, game["neutral"])
        pick = prediction["First Half Pick"]
        winner = game["home"] if game["home_half"] > game["away_half"] else game["away"]
        result = "No Signal" if not pick else "Push" if game["home_half"] == game["away_half"] else "Correct" if pick == winner else "Missed"
        rows.append({"Game": f"{game['away']} @ {game['home']}", "Kickoff": game["kickoff"], **prediction, "Result": result})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Chronological NFL first-half Watch backtest")
    parser.add_argument("--season", type=int, required=True)
    args = parser.parse_args()
    report = backtest(load_history(args.season, 18), args.season)
    if report.empty:
        print("No completed first-half data available")
    else:
        print(report.to_csv(index=False))
        print(report["Result"].value_counts().to_string())
