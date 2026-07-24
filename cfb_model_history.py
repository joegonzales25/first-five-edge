import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from history_backend_config import resolve_history_backend


DB_PATH = Path(
    os.environ.get(
        "FIRST_FIVE_EDGE_CFB_HISTORY_DB",
        Path(tempfile.gettempdir()) / "first_five_edge_cfb_model_history.sqlite3",
    )
)
MARKETS = {
    "Full Game": {
        "pick": "Side Pick",
        "segment": "Side Tracking Segment",
        "result": "Side Result",
        "confidence": "Side Confidence",
        "score": "Side Score",
    },
    "Scoring Environment": {
        "pick": "Scoring Pick",
        "segment": "Scoring Tracking Segment",
        "result": "Scoring Result",
        "confidence": "Scoring Confidence",
        "score": "Scoring Score",
    },
    "First Half": {
        "pick": "First Half Pick",
        "segment": "First Half Tracking Segment",
        "result": "First Half Result",
        "confidence": "First Half Confidence",
        "score": "First Half Score",
    },
}


class ManagedConnection:
    def __init__(self, connection):
        self.connection = connection

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def __enter__(self):
        return self.connection

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None and hasattr(self.connection, "commit"):
            self.connection.commit()
        if hasattr(self.connection, "close"):
            self.connection.close()
        return False


def history_backend():
    return resolve_history_backend()


def using_remote_history():
    return history_backend() == "turso"


def connect(db_path=DB_PATH):
    if using_remote_history():
        import libsql

        return ManagedConnection(
            libsql.connect(
                database=os.environ["TURSO_DATABASE_URL"],
                auth_token=os.environ["TURSO_AUTH_TOKEN"],
            )
        )
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def row_to_dict(row, columns=None):
    if isinstance(row, dict):
        return row
    if hasattr(row, "keys"):
        return {key: row[key] for key in row.keys()}
    return dict(zip(columns or [], row))


def fetch_rows(connection, query, params=()):
    cursor = connection.execute(query, params)
    columns = [column[0] for column in cursor.description or []]
    return [row_to_dict(row, columns) for row in cursor.fetchall()]


def fetch_one(connection, query, params=()):
    cursor = connection.execute(query, params)
    row = cursor.fetchone()
    if row is None:
        return None
    columns = [column[0] for column in cursor.description or []]
    return row_to_dict(row, columns)


def init_db(connection):
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS cfb_model_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id TEXT NOT NULL,
            season INTEGER,
            week INTEGER,
            slate_date TEXT NOT NULL,
            market TEXT NOT NULL,
            game TEXT NOT NULL,
            away_team TEXT,
            home_team TEXT,
            scheduled_kickoff TEXT,
            market_version TEXT NOT NULL,
            model_version TEXT NOT NULL,
            pick TEXT,
            decision_tier TEXT,
            confidence TEXT,
            score REAL,
            model_margin REAL,
            projected_total REAL,
            league_total_baseline REAL,
            status TEXT,
            away_score INTEGER,
            home_score INTEGER,
            away_first_half INTEGER,
            home_first_half INTEGER,
            result TEXT,
            stored_outcome TEXT,
            data_quality TEXT,
            downgrade_reasons TEXT,
            source TEXT,
            source_timestamp TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            graded_at TEXT,
            locked_at TEXT,
            snapshot_status TEXT,
            UNIQUE(game_id, market, market_version, model_version)
        )
        """
    )
    connection.commit()


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_int(value):
    try:
        if value is None or pd.isna(value):
            return None
        return int(value)
    except Exception:
        return None


def safe_float(value):
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def parse_kickoff(value):
    try:
        return pd.to_datetime(value, utc=True).to_pydatetime()
    except Exception:
        return None


def is_pregame_status(status):
    return str(status or "").strip().lower() in {
        "",
        "scheduled",
        "pre-game",
        "preview",
    }


def snapshot_is_open(row, now):
    kickoff = parse_kickoff(row.get("Scheduled Kickoff"))
    if not is_pregame_status(row.get("Status")):
        return False
    return kickoff is None or now < kickoff


def outcome_for_result(result):
    return {
        "Correct": "Hit",
        "Missed": "Miss",
        "Push": "Push",
        "No Signal": "No Edge",
    }.get(str(result or ""), "Pending")


def prediction_values(
    row,
    market,
    config,
    slate_date,
    market_version,
    model_version,
    now_text,
):
    downgrade_reasons = row.get("Downgrade Reasons") or []
    if not isinstance(downgrade_reasons, list):
        downgrade_reasons = [str(downgrade_reasons)]
    return {
        "game_id": str(row.get("Game ID") or ""),
        "season": safe_int(row.get("Season")),
        "week": safe_int(row.get("Week")),
        "slate_date": str(slate_date),
        "market": market,
        "game": row.get("Game"),
        "away_team": row.get("Away"),
        "home_team": row.get("Home"),
        "scheduled_kickoff": row.get("Scheduled Kickoff"),
        "market_version": market_version,
        "model_version": model_version,
        "pick": row.get(config["pick"]),
        "decision_tier": row.get(config["segment"]),
        "confidence": row.get(config["confidence"]),
        "score": safe_float(row.get(config["score"])),
        "model_margin": safe_float(row.get("Model Margin")),
        "projected_total": safe_float(row.get("Projected Total")),
        "league_total_baseline": safe_float(
            row.get("League Total Baseline")
        ),
        "status": row.get("Status"),
        "data_quality": row.get("Data Quality"),
        "downgrade_reasons": "; ".join(downgrade_reasons),
        "source": row.get("Source"),
        "source_timestamp": row.get("Source Timestamp"),
        "created_at": now_text,
        "updated_at": now_text,
        "locked_at": None,
        "snapshot_status": "Pregame",
    }


def result_values(row, config, now_text):
    result = row.get(config["result"]) or "Pending"
    return {
        "status": row.get("Status"),
        "away_score": safe_int(row.get("Away Score")),
        "home_score": safe_int(row.get("Home Score")),
        "away_first_half": safe_int(row.get("Away First Half")),
        "home_first_half": safe_int(row.get("Home First Half")),
        "result": result,
        "stored_outcome": outcome_for_result(result),
        "updated_at": now_text,
        "graded_at": now_text
        if result in {"Correct", "Missed", "Push"}
        else None,
    }


def existing_snapshot(
    connection, game_id, market, market_version, model_version
):
    return fetch_one(
        connection,
        """
        SELECT *
        FROM cfb_model_history
        WHERE game_id = ?
          AND market = ?
          AND market_version = ?
          AND model_version = ?
        """,
        (str(game_id), market, market_version, model_version),
    )


def insert_prediction(connection, values):
    columns = list(values)
    placeholders = ", ".join(["?"] * len(columns))
    connection.execute(
        f"""
        INSERT INTO cfb_model_history ({", ".join(columns)})
        VALUES ({placeholders})
        """,
        [values[column] for column in columns],
    )


def update_open_prediction(connection, row_id, values):
    mutable = [
        "pick",
        "decision_tier",
        "confidence",
        "score",
        "model_margin",
        "projected_total",
        "league_total_baseline",
        "status",
        "data_quality",
        "downgrade_reasons",
        "source",
        "source_timestamp",
        "scheduled_kickoff",
        "updated_at",
    ]
    connection.execute(
        f"""
        UPDATE cfb_model_history
        SET {", ".join(f"{column} = ?" for column in mutable)}
        WHERE id = ? AND snapshot_status = 'Pregame'
        """,
        [values[column] for column in mutable] + [row_id],
    )


def update_result(connection, row_id, values, should_lock):
    connection.execute(
        """
        UPDATE cfb_model_history
        SET status = ?,
            away_score = ?,
            home_score = ?,
            away_first_half = ?,
            home_first_half = ?,
            result = ?,
            stored_outcome = ?,
            updated_at = ?,
            graded_at = COALESCE(graded_at, ?),
            locked_at = CASE
                WHEN ? THEN COALESCE(locked_at, ?)
                ELSE locked_at
            END,
            snapshot_status = CASE
                WHEN ? THEN 'Locked'
                ELSE snapshot_status
            END
        WHERE id = ?
        """,
        (
            values["status"],
            values["away_score"],
            values["home_score"],
            values["away_first_half"],
            values["home_first_half"],
            values["result"],
            values["stored_outcome"],
            values["updated_at"],
            values["graded_at"],
            should_lock,
            values["updated_at"],
            should_lock,
            row_id,
        ),
    )


def record_cfb_history(
    slate,
    slate_date,
    market_version,
    model_version,
    db_path=DB_PATH,
):
    counts = {
        "inserted": 0,
        "refreshed": 0,
        "locked_or_graded": 0,
        "skipped_without_snapshot": 0,
    }
    if slate is None or slate.empty:
        return counts

    now = datetime.now(timezone.utc)
    now_text = now.isoformat(timespec="seconds")
    with connect(db_path) as connection:
        init_db(connection)
        for _, row in slate.iterrows():
            game_id = row.get("Game ID")
            if not game_id:
                continue
            open_snapshot = snapshot_is_open(row, now)
            for market, config in MARKETS.items():
                existing = existing_snapshot(
                    connection,
                    game_id,
                    market,
                    market_version,
                    model_version,
                )
                prediction = prediction_values(
                    row,
                    market,
                    config,
                    slate_date,
                    market_version,
                    model_version,
                    now_text,
                )
                result = result_values(row, config, now_text)

                if existing is None:
                    if not open_snapshot:
                        counts["skipped_without_snapshot"] += 1
                        continue
                    prediction.update(result)
                    insert_prediction(connection, prediction)
                    counts["inserted"] += 1
                    continue

                if (
                    existing.get("snapshot_status") == "Pregame"
                    and open_snapshot
                ):
                    update_open_prediction(connection, existing["id"], prediction)
                    update_result(connection, existing["id"], result, False)
                    counts["refreshed"] += 1
                    continue

                update_result(connection, existing["id"], result, True)
                counts["locked_or_graded"] += 1
        connection.commit()
    return counts


def load_cfb_history(
    model_version=None,
    market_version=None,
    db_path=DB_PATH,
):
    with connect(db_path) as connection:
        init_db(connection)
        where = []
        params = []
        if model_version:
            where.append("model_version = ?")
            params.append(model_version)
        if market_version:
            where.append("market_version = ?")
            params.append(market_version)
        where_clause = f"WHERE {' AND '.join(where)}" if where else ""
        return fetch_rows(
            connection,
            f"""
            SELECT *
            FROM cfb_model_history
            {where_clause}
            ORDER BY slate_date DESC, scheduled_kickoff DESC, game, market
            """,
            params,
        )


def load_cfb_performance_summary(
    model_version=None,
    market_version=None,
    db_path=DB_PATH,
):
    rows = load_cfb_history(model_version, market_version, db_path)
    graded = [
        row for row in rows if row.get("result") in {"Correct", "Missed", "Push"}
    ]
    return {
        "snapshots": len(rows),
        "completed": len(graded),
        "official": sum(
            1 for row in rows if row.get("decision_tier") == "Official"
        ),
        "leans": sum(1 for row in rows if row.get("decision_tier") == "Lean"),
        "watches": sum(
            1 for row in rows if row.get("decision_tier") == "Watch"
        ),
        "storage_backend": "Turso" if using_remote_history() else "SQLite",
        "db_path": (
            os.environ.get("TURSO_DATABASE_URL", "")
            if using_remote_history()
            else str(db_path)
        ),
    }


def performance_group(label, rows):
    hits = sum(1 for row in rows if row.get("result") == "Correct")
    misses = sum(1 for row in rows if row.get("result") == "Missed")
    pushes = sum(1 for row in rows if row.get("result") == "Push")
    pending = sum(1 for row in rows if row.get("result") == "Pending")
    return {
        "Segment": label,
        "Decisions": len(rows),
        "Hits": hits,
        "Misses": misses,
        "Pushes": pushes,
        "Pending": pending,
        "Win Rate": round(hits / (hits + misses), 4)
        if hits + misses
        else None,
    }


def load_cfb_performance_tables(
    model_version=None,
    market_version=None,
    db_path=DB_PATH,
):
    rows = load_cfb_history(model_version, market_version, db_path)
    tracked = [
        row
        for row in rows
        if row.get("decision_tier") in {"Official", "Lean", "Watch"}
    ]
    return {
        "tier": [
            performance_group(
                tier,
                [row for row in tracked if row.get("decision_tier") == tier],
            )
            for tier in ["Official", "Lean", "Watch"]
        ],
        "market": [
            performance_group(
                market,
                [row for row in tracked if row.get("market") == market],
            )
            for market in MARKETS
        ],
        "history": tracked,
    }
