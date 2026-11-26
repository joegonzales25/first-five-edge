"""Forward-only market storage for Phase 1: NFL, NBA, and CBB."""

import importlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pandas as pd
import requests

from cfb_market import SPORT_PATHS, comparison_rows, decode_context, number, valid_context

MODULES = {"NFL": "nfl_model_history", "NBA": "nba_model_history", "CBB": "cbb_model_history"}


def init_market_db(connection):
    connection.execute("""CREATE TABLE IF NOT EXISTS market_forward_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT, sport TEXT NOT NULL, game_id TEXT NOT NULL,
        model_version TEXT NOT NULL, market_version TEXT NOT NULL, track TEXT NOT NULL,
        track_version TEXT NOT NULL, slate_date TEXT, game TEXT, home_team TEXT, away_team TEXT,
        scheduled_kickoff TEXT, market_context TEXT NOT NULL, snapshot_status TEXT NOT NULL,
        status TEXT, home_score REAL, away_score REAL,
        UNIQUE(sport, game_id, model_version, market_version, track, track_version)
    )""")
    connection.execute("""CREATE TABLE IF NOT EXISTS market_forward_observations (
        id INTEGER PRIMARY KEY AUTOINCREMENT, sport TEXT NOT NULL, game_id TEXT NOT NULL,
        model_version TEXT NOT NULL, market_version TEXT NOT NULL, track TEXT NOT NULL, track_version TEXT NOT NULL,
        captured_at TEXT NOT NULL, market_context TEXT NOT NULL,
        UNIQUE(sport, game_id, model_version, market_version, track, track_version, captured_at)
    )""")


def persist_market_row(connection, sport, row, stored, model_version, market_version, now):
    if not stored:
        return
    kickoff = row.get("Scheduled Kickoff", row.get("Sort Date"))
    kickoff = pd.to_datetime(kickoff, utc=True, errors="coerce")
    now = pd.to_datetime(now, utc=True)
    is_open = (pd.notna(kickoff) and now < kickoff
               and str(row.get("Status")).lower() in {"scheduled", "pre-game", "preview"}
               and stored.get("snapshot_status") == "Pregame")
    context = valid_context(row.get("Market Context"), kickoff, now) if is_open else {}
    tracks = [("Baseline", model_version, number(stored.get("model_margin")), number(stored.get("projected_total")))]
    if sport == "NFL" and stored.get("challenger_status") == "Tracked":
        # Current automated challenger inputs do not independently model totals.
        tracks.append(("Challenger", stored.get("challenger_model_version") or "unknown", number(stored.get("challenger_model_margin")), None))
    # Always settle existing tracks, including a challenger unavailable later.
    existing_tracks = connection.execute("""SELECT track, track_version FROM market_forward_snapshots
        WHERE sport=? AND game_id=? AND model_version=? AND market_version=?""",
        (sport, str(row["Game ID"]), model_version, market_version)).fetchall()
    known = {(t[0], t[1]) for t in tracks}
    for item in existing_tracks:
        track = item["track"] if hasattr(item, "keys") else item[0]
        version = item["track_version"] if hasattr(item, "keys") else item[1]
        if (track, version) not in known:
            tracks.append((track, version, None, None))
    for track, track_version, margin, total in tracks:
        key = (sport, str(row["Game ID"]), model_version, market_version, track, track_version)
        if context and (margin is not None or total is not None):
            paired = {**context, "model_margin": margin, "projected_total": total,
                      "prediction_as_of": stored.get("created_at") if sport in {"NBA", "CBB"} else context.get("prediction_as_of") or str(now),
                      "track": track, "track_version": track_version}
            raw = json.dumps(paired, allow_nan=False)
            # A locked comparison cannot reopen even if the upstream status regresses.
            existing = connection.execute("""SELECT snapshot_status FROM market_forward_snapshots
                WHERE sport=? AND game_id=? AND model_version=? AND market_version=? AND track=? AND track_version=?""", key).fetchone()
            locked = existing and (existing["snapshot_status"] if hasattr(existing, "keys") else existing[0]) == "Locked"
            if not locked:
                connection.execute("""INSERT OR IGNORE INTO market_forward_observations
                    (sport, game_id, model_version, market_version, track, track_version, captured_at, market_context)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", (*key, paired["captured_at"], raw))
                connection.execute("""INSERT INTO market_forward_snapshots
                    (sport, game_id, model_version, market_version, track, track_version, slate_date,
                     game, home_team, away_team, scheduled_kickoff, market_context, snapshot_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pregame')
                    ON CONFLICT(sport, game_id, model_version, market_version, track, track_version)
                    DO UPDATE SET market_context=excluded.market_context, scheduled_kickoff=excluded.scheduled_kickoff
                    WHERE market_forward_snapshots.snapshot_status='Pregame'""",
                    (*key, stored.get("slate_date"), row.get("Game"), row.get("Home"), row.get("Away"), kickoff.isoformat(), raw))
        connection.execute("""UPDATE market_forward_snapshots
            SET status=?, home_score=?, away_score=?,
                snapshot_status=CASE WHEN ? THEN 'Locked' ELSE snapshot_status END
            WHERE sport=? AND game_id=? AND model_version=? AND market_version=? AND track=? AND track_version=?""",
            (row.get("Status"), number(row.get("Home Score")), number(row.get("Away Score")), not is_open, *key))


def load_market_snapshots(sport, model_version, market_version):
    module = importlib.import_module(MODULES[sport])
    connection = module.connect()
    try:
        try:
            conditions, params = ["sport=?"], [sport]
            for column, value in [("model_version", model_version), ("market_version", market_version)]:
                if value is not None:
                    conditions.append(f"{column}=?")
                    params.append(value)
            return module.fetch_rows(connection,
                f"SELECT * FROM market_forward_snapshots WHERE {' AND '.join(conditions)} ORDER BY slate_date DESC, game, track",
                params)
        except Exception as exc:
            if "no such table" in str(exc).lower():
                return []
            raise
    finally:
        connection.close()


def reconcile_market_results(connection, sport, now):
    now = pd.to_datetime(now, utc=True)
    cursor = connection.execute("""SELECT id, scheduled_kickoff, market_context FROM market_forward_snapshots
        WHERE sport=? AND (status IS NULL OR status != 'Final')""", (sport,))
    columns = [c[0] for c in cursor.description]
    pending = {}
    for item in cursor.fetchall():
        item = dict(item) if hasattr(item, "keys") else dict(zip(columns, item))
        kickoff = pd.to_datetime(item["scheduled_kickoff"], utc=True, errors="coerce")
        if pd.isna(kickoff) or kickoff > now:
            continue
        connection.execute("UPDATE market_forward_snapshots SET snapshot_status='Locked' WHERE id=?", (item["id"],))
        event_id = decode_context(item["market_context"]).get("event_id")
        if event_id:
            pending.setdefault(str(event_id), []).append(item["id"])

    def fetch(event_id):
        try:
            response = requests.get(f"https://site.api.espn.com/apis/site/v2/sports/{SPORT_PATHS[sport]}/summary",
                                    params={"event": event_id}, timeout=15)
            response.raise_for_status()
            header = response.json().get("header") or {}
            contest = (header.get("competitions") or [{}])[0]
            if str(header.get("id")) != event_id or not ((contest.get("status") or {}).get("type") or {}).get("completed"):
                return event_id, None
            scores = {}
            for competitor in contest.get("competitors") or []:
                raw = competitor.get("score")
                score = number(raw.get("value") if isinstance(raw, dict) else raw)
                if score is not None and score >= 0 and score.is_integer():
                    scores[competitor.get("homeAway")] = score
            return event_id, scores if "home" in scores and "away" in scores else None
        except (requests.RequestException, ValueError, TypeError):
            return event_id, None

    with ThreadPoolExecutor(max_workers=6) as pool:
        for event_id, scores in pool.map(fetch, pending):
            if scores:
                for row_id in pending[event_id]:
                    connection.execute("""UPDATE market_forward_snapshots SET status='Final',
                        home_score=?, away_score=?, snapshot_status='Locked' WHERE id=?""",
                        (scores["home"], scores["away"], row_id))


def reconcile_sport_markets(sport):
    module = importlib.import_module(MODULES[sport])
    connection = module.connect()
    try:
        init_market_db(connection)
        reconcile_market_results(connection, sport, datetime.now(timezone.utc))
        connection.commit()
    finally:
        connection.close()


def market_report(records):
    report = []
    for saved in records:
        if saved.get("snapshot_status") != "Locked":
            continue
        row = {"Game": saved.get("game"), "Home": saved.get("home_team"), "Away": saved.get("away_team"),
               "Status": saved.get("status"), "Snapshot Status": "Locked",
               "Home Score": saved.get("home_score"), "Away Score": saved.get("away_score")}
        for comparison in comparison_rows(row, decode_context(saved.get("market_context"))):
            report.append({"Sport": saved.get("sport"), "Slate": saved.get("slate_date"),
                           "Model Track": saved.get("track"), "Model": saved.get("track_version"),
                           "Baseline Version": saved.get("model_version"), "Market Version": saved.get("market_version"), **comparison})
    return report
