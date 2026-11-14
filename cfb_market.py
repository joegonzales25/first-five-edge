"""Pregame price observations and fixed-rule forward comparisons, not picks."""

from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import json
import math

import pandas as pd
import requests

VERSION = "projection-direction-v1"
SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/football/college-football/summary"


def number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def american_odds(value):
    value = number(value)
    return int(value) if value is not None and value.is_integer() and abs(value) >= 100 else None


def normalize_quotes(payload):
    quotes = []
    for item in payload.get("pickcenter") or []:
        provider = item.get("provider") or {}
        if not provider.get("name"):
            continue
        home, away = item.get("homeTeamOdds") or {}, item.get("awayTeamOdds") or {}
        spread = number(item.get("spread"))
        # ESPN spread magnitude is paired with explicit favorite flags rather
        # than assuming every negative feed spread belongs to the home team.
        home_spread = None
        if spread == 0:
            home_spread = 0.0
        elif spread is not None:
            if home.get("favorite") is True and away.get("favorite") is not True:
                home_spread = -abs(spread)
            elif away.get("favorite") is True and home.get("favorite") is not True:
                home_spread = abs(spread)
        total = number(item.get("overUnder"))
        total = total if total is not None and total > 0 else None
        if home_spread is None and total is None:
            continue
        quotes.append({
            "book": str(provider["name"]), "book_id": str(provider.get("id") or ""),
            "home_spread": home_spread, "total": total,
            "home_spread_odds": american_odds(home.get("spreadOdds")),
            "away_spread_odds": american_odds(away.get("spreadOdds")),
            "over_odds": american_odds(item.get("overOdds")),
            "under_odds": american_odds(item.get("underOdds")),
            "home_moneyline": american_odds(home.get("moneyLine")),
            "away_moneyline": american_odds(away.get("moneyLine")),
        })
    return quotes


def decode_context(raw):
    try:
        context = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):
        return {}
    return context if isinstance(context, dict) and isinstance(context.get("quotes"), list) else {}


def valid_context(raw, kickoff, now):
    context = decode_context(raw)
    captured = pd.to_datetime(context.get("captured_at"), utc=True, errors="coerce")
    kickoff = pd.to_datetime(kickoff, utc=True, errors="coerce")
    now = pd.to_datetime(now, utc=True)
    return context if pd.notna(captured) and pd.notna(kickoff) and captured <= now and captured < kickoff else {}


def attach_market_context(slate, now=None):
    result = slate.copy()
    result["Market Context"] = None

    def collect(item):
        index, row = item
        cutoff = pd.to_datetime(now or datetime.now(timezone.utc), utc=True)
        kickoff = pd.to_datetime(row.get("Scheduled Kickoff"), utc=True, errors="coerce")
        if pd.isna(kickoff) or cutoff >= kickoff or str(row.get("Status")).lower() not in {"scheduled", "pre-game", "preview"}:
            return index, None
        try:
            response = requests.get(SUMMARY_URL, params={"event": str(row["Game ID"])}, timeout=15)
            response.raise_for_status()
            payload = response.json()
            header = payload.get("header") or {}
            contest = (header.get("competitions") or [{}])[0]
            state = ((contest.get("status") or {}).get("type") or {}).get("state")
            if str(header.get("id")) != str(row["Game ID"]) or state != "pre":
                return index, None
            source_kickoff = pd.to_datetime(contest.get("date") or header.get("date"), utc=True, errors="coerce")
            if pd.isna(source_kickoff) or source_kickoff != kickoff:
                return index, None
            quotes = normalize_quotes(payload)
            captured = pd.to_datetime(now or datetime.now(timezone.utc), utc=True)
            if not quotes or captured >= kickoff:
                return index, None
            return index, json.dumps({
                "version": VERSION, "source": "ESPN summary", "captured_at": captured.isoformat(),
                "prediction_as_of": row.get("Source Timestamp"),
                "model_margin": number(row.get("Model Margin")),
                "projected_total": number(row.get("Projected Total")),
                "source_updated_at": None, "quotes": quotes,
            }, allow_nan=False)
        except (requests.RequestException, ValueError, TypeError):
            print(f"CFB market quote unavailable for {row['Game ID']}; baseline unchanged.")
            return index, None

    with ThreadPoolExecutor(max_workers=6) as pool:
        for index, context in pool.map(collect, result.iterrows()):
            result.at[index, "Market Context"] = context
    print(f"CFB pregame market coverage: {result['Market Context'].notna().sum()}/{len(result)} slate games.")
    return result


def comparison_rows(row, context):
    rows = []
    margin = number(context.get("model_margin", row.get("Model Margin")))
    projected_total = number(context.get("projected_total", row.get("Projected Total")))
    for quote in context.get("quotes", []):
        spread, total = number(quote.get("home_spread")), number(quote.get("total"))
        for market in ("Spread", "Total"):
            if market == "Spread":
                if margin is None or spread is None:
                    continue
                delta = margin + spread
                home = delta > 0
                selection = row.get("Home") if home else row.get("Away")
                line = spread if home else -spread
                odds = quote.get("home_spread_odds" if home else "away_spread_odds")
                actual = number(row.get("Home Score"))
                away_score = number(row.get("Away Score"))
                actual = actual - away_score + spread if actual is not None and away_score is not None else None
                actual = actual if home else -actual if actual is not None else None
                projection = margin
                market_line = spread
            else:
                if projected_total is None or total is None:
                    continue
                delta = projected_total - total
                selection = "Over" if delta > 0 else "Under"
                line, market_line = total, total
                odds = quote.get("over_odds" if delta > 0 else "under_odds")
                home_score, away_score = number(row.get("Home Score")), number(row.get("Away Score"))
                actual = home_score + away_score - total if home_score is not None and away_score is not None else None
                actual = actual if delta > 0 else -actual if actual is not None else None
                projection = projected_total
            no_difference = abs(delta) < 1e-9
            outcome = "No Difference" if no_difference else "Pending"
            if not no_difference and row.get("Snapshot Status") == "Locked" and str(row.get("Status")).lower() in {"final", "game over", "completed early"} and actual is not None:
                outcome = "Push" if abs(actual) < 1e-9 else "Cover" if actual > 0 else "Miss"
            odds = american_odds(odds)
            units = None
            if odds is not None:
                units = 0.0 if outcome == "Push" else -1.0 if outcome == "Miss" else (odds / 100 if odds > 0 else 100 / abs(odds)) if outcome == "Cover" else None
            rows.append({
                "Game": row.get("Game"), "Market": market, "Book": quote.get("book"),
                "Model Projection": projection, "Market Line": market_line,
                "Model Read": (
                    f"{row.get('Home') if margin >= 0 else row.get('Away')} by {abs(margin):g}"
                    if market == "Spread" else f"{projected_total:g} points"
                ),
                "Market Read": f"{row.get('Home')} {spread:+g}" if market == "Spread" else f"Total {total:g}",
                "Comparison": "No Difference" if no_difference else f"{selection} {line:+g}" if market == "Spread" else f"{selection} {line:g}",
                "Projection Difference": round(abs(delta), 3), "American Odds": odds,
                "Break-even %": round((100 / (odds + 100) if odds > 0 else abs(odds) / (abs(odds) + 100)) * 100, 2) if odds is not None else None,
                "Result": outcome, "Hypothetical Units": units,
                "Captured At": context.get("captured_at"), "Source": context.get("source"),
                "Prediction As Of": context.get("prediction_as_of"),
                "Rule": context.get("version"),
            })
    return rows


def forward_rows(history):
    result = []
    for saved in history:
        if saved.get("snapshot_status") != "Locked" or saved.get("market") not in {"Full Game", "Scoring Environment"}:
            continue
        context = valid_context(saved.get("market_context"), saved.get("scheduled_kickoff"), datetime.now(timezone.utc))
        row = {"Game": saved.get("game"), "Home": saved.get("home_team"), "Away": saved.get("away_team"),
               "Model Margin": saved.get("model_margin"), "Projected Total": saved.get("projected_total"),
               "Home Score": saved.get("home_score"), "Away Score": saved.get("away_score"),
               "Status": saved.get("status"), "Snapshot Status": saved.get("snapshot_status")}
        wanted = "Spread" if saved["market"] == "Full Game" else "Total"
        for comparison in comparison_rows(row, context):
            if comparison["Market"] == wanted:
                result.append({"Slate": saved.get("slate_date"), "Model": saved.get("model_version"),
                               "Market Version": saved.get("market_version"),
                               "Baseline Pick": saved.get("pick"), "Baseline Confidence": saved.get("confidence"),
                               "Decision Tier": saved.get("decision_tier"),
                               "Data Quality": saved.get("data_quality"), **comparison})
    return result
