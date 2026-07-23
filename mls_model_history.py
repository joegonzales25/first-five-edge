import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from history_backend_config import resolve_history_backend


DB_PATH = Path(
    os.environ.get(
        "FIRST_FIVE_EDGE_MLS_HISTORY_DB",
        Path(tempfile.gettempdir()) / "first_five_edge_mls_model_history.sqlite3",
    )
)


def history_backend():
    return resolve_history_backend()


def using_remote_history():
    return history_backend() == "turso"


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
    if columns:
        return dict(zip(columns, row))
    return dict(row)


def fetch_rows(connection, query, params=()):
    cursor = connection.execute(query, params)
    rows = cursor.fetchall()
    columns = [column[0] for column in cursor.description or []]
    return [row_to_dict(row, columns) for row in rows]


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
        CREATE TABLE IF NOT EXISTS mls_model_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id TEXT NOT NULL,
            season INTEGER,
            slate_date TEXT NOT NULL,
            game_time TEXT,
            game TEXT NOT NULL,
            away_team TEXT,
            home_team TEXT,
            market_version TEXT NOT NULL,
            model_version TEXT NOT NULL,
            model_signal TEXT,
            double_chance_edge TEXT,
            full_match_edge TEXT,
            scoring_edge TEXT,
            btts_edge TEXT,
            confidence TEXT,
            edge_score REAL,
            model_margin REAL,
            projected_total REAL,
            league_total_baseline REAL,
            draw_risk REAL,
            away_prior_games INTEGER,
            home_prior_games INTEGER,
            rest_edge REAL,
            status TEXT,
            away_score INTEGER,
            home_score INTEGER,
            actual_winner TEXT,
            actual_total REAL,
            double_chance_result TEXT,
            full_match_result TEXT,
            scoring_result TEXT,
            btts_result TEXT,
            margin_error REAL,
            total_error REAL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            graded_at TEXT,
            locked_at TEXT,
            snapshot_status TEXT,
            UNIQUE(game_id, market_version, model_version)
        )
        """
    )
    connection.commit()


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_int(value):
    if value is None or value == "":
        return None
    try:
        if pd.isna(value):
            return None
        return int(value)
    except Exception:
        return None


def safe_float(value):
    if value is None or value == "":
        return None
    try:
        if pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def is_final(row):
    return is_final_status(row.get("Status"))


def is_final_status(status):
    return str(status or "").strip().lower() in [
        "final",
        "game over",
        "full time",
        "full-time",
    ]


def is_snapshot_eligible(row):
    status = str(row.get("Status", "")).strip().lower()
    return status in ["scheduled", "pre-game", "preview"]


def is_pregame_status(status):
    return str(status or "").strip().lower() in [
        "",
        "scheduled",
        "pre-game",
        "preview",
        "postponed",
    ]


def prediction_values(row, slate_date, market_version, model_version, now):
    return {
        "game_id": str(row.get("Game ID") or row.get("game_id") or ""),
        "season": safe_int(row.get("Season")),
        "slate_date": str(slate_date),
        "game_time": row.get("Game Time"),
        "game": row.get("Game"),
        "away_team": row.get("Away"),
        "home_team": row.get("Home"),
        "market_version": market_version,
        "model_version": model_version,
        "model_signal": row.get("Model Signal"),
        "double_chance_edge": row.get("Side Edge"),
        "full_match_edge": row.get("Full Match Edge"),
        "scoring_edge": row.get("Scoring Edge"),
        "btts_edge": row.get("BTTS Edge"),
        "confidence": row.get("Confidence"),
        "edge_score": safe_float(row.get("Edge Score")),
        "model_margin": safe_float(row.get("Model Margin")),
        "projected_total": safe_float(row.get("Projected Total")),
        "league_total_baseline": safe_float(row.get("League Total Baseline")),
        "draw_risk": safe_float(row.get("Draw Risk")),
        "away_prior_games": safe_int(row.get("Away Prior Games")),
        "home_prior_games": safe_int(row.get("Home Prior Games")),
        "rest_edge": safe_float(row.get("Rest Edge")),
        "status": row.get("Status"),
        "created_at": now,
        "updated_at": now,
        "locked_at": None,
        "snapshot_status": "Pregame",
    }


def result_values(row, now):
    away_score = safe_int(row.get("Away Score"))
    home_score = safe_int(row.get("Home Score"))
    actual_total = safe_float(row.get("Actual Total"))
    model_margin = safe_float(row.get("Model Margin"))
    projected_total = safe_float(row.get("Projected Total"))
    actual_margin = home_score - away_score if away_score is not None and home_score is not None else None
    margin_error = abs(model_margin - actual_margin) if model_margin is not None and actual_margin is not None else None
    total_error = abs(projected_total - actual_total) if projected_total is not None and actual_total is not None else None
    return {
        "status": row.get("Status"),
        "away_score": away_score,
        "home_score": home_score,
        "actual_winner": row.get("Actual Winner"),
        "actual_total": actual_total,
        "double_chance_result": row.get("Side Result"),
        "full_match_result": row.get("Winner Result"),
        "scoring_result": row.get("Scoring Result"),
        "btts_result": row.get("BTTS Result"),
        "margin_error": margin_error,
        "total_error": total_error,
        "updated_at": now,
        "graded_at": now if is_final(row) else None,
    }


def existing_snapshot(connection, game_id, market_version, model_version):
    return fetch_one(
        connection,
        """
        SELECT id
        FROM mls_model_history
        WHERE game_id = ?
          AND market_version = ?
          AND model_version = ?
        """,
        (str(game_id), market_version, model_version),
    )


def insert_prediction(connection, row_values):
    columns = list(row_values.keys())
    placeholders = ", ".join(["?"] * len(columns))
    connection.execute(
        f"""
        INSERT INTO mls_model_history ({", ".join(columns)})
        VALUES ({placeholders})
        """,
        [row_values[column] for column in columns],
    )


def update_result(connection, game_id, market_version, model_version, values):
    should_lock = not is_pregame_status(values["status"])
    connection.execute(
        """
        UPDATE mls_model_history
        SET status = ?,
            away_score = ?,
            home_score = ?,
            actual_winner = ?,
            actual_total = ?,
            double_chance_result = ?,
            full_match_result = ?,
            scoring_result = ?,
            btts_result = ?,
            margin_error = ?,
            total_error = ?,
            updated_at = ?,
            graded_at = COALESCE(graded_at, ?),
            locked_at = CASE
                WHEN ? THEN COALESCE(locked_at, ?)
                ELSE locked_at
            END,
            snapshot_status = CASE
                WHEN ? THEN 'Locked'
                ELSE COALESCE(snapshot_status, 'Pregame')
            END
        WHERE game_id = ?
          AND market_version = ?
          AND model_version = ?
        """,
        (
            values["status"],
            values["away_score"],
            values["home_score"],
            values["actual_winner"],
            values["actual_total"],
            values["double_chance_result"],
            values["full_match_result"],
            values["scoring_result"],
            values["btts_result"],
            values["margin_error"],
            values["total_error"],
            values["updated_at"],
            values["graded_at"],
            should_lock,
            values["updated_at"],
            should_lock,
            str(game_id),
            market_version,
            model_version,
        ),
    )


def record_mls_history(slate, slate_date, market_version, model_version, db_path=DB_PATH):
    if slate is None or slate.empty:
        return {"inserted": 0, "updated": 0, "skipped_without_snapshot": 0}

    counts = {"inserted": 0, "updated": 0, "skipped_without_snapshot": 0}
    now = utc_now()
    with connect(db_path) as connection:
        init_db(connection)
        for _, row in slate.iterrows():
            game_id = row.get("Game ID") or row.get("game_id")
            if not game_id:
                continue
            existing = existing_snapshot(connection, game_id, market_version, model_version)
            if existing is None and is_snapshot_eligible(row):
                insert_prediction(connection, prediction_values(row, slate_date, market_version, model_version, now))
                counts["inserted"] += 1
                continue
            if existing is None:
                counts["skipped_without_snapshot"] += 1
                continue
            update_result(connection, game_id, market_version, model_version, result_values(row, now))
            counts["updated"] += 1
        connection.commit()
    return counts


def load_mls_history(model_version=None, market_version=None, db_path=DB_PATH):
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
            FROM mls_model_history
            {where_clause}
            ORDER BY slate_date DESC, game_time DESC, game
            """,
            params,
        )


def accuracy(rows, field):
    graded = [row for row in rows if row.get(field) in ["Correct", "Missed"]]
    if not graded:
        return 0.0
    return round(sum(1 for row in graded if row.get(field) == "Correct") / len(graded), 4)


def avg(values):
    numbers = [safe_float(value) for value in values if safe_float(value) is not None]
    return round(sum(numbers) / len(numbers), 2) if numbers else 0.0


def load_mls_performance_summary(model_version=None, market_version=None, db_path=DB_PATH):
    rows = load_mls_history(model_version, market_version, db_path)
    completed = [row for row in rows if is_final_status(row.get("status"))]
    dc_signals = [row for row in rows if row.get("double_chance_edge") not in [None, "", "Pass"]]
    full_signals = [row for row in rows if row.get("full_match_edge") not in [None, "", "Pass"]]
    goals_signals = [
        row
        for row in rows
        if row.get("scoring_edge") not in [None, "", "Neutral Goals Environment"]
    ]
    btts_signals = [row for row in rows if row.get("btts_edge") not in [None, "", "Pass"]]
    return {
        "snapshots": len(rows),
        "completed": len(completed),
        "double_chance_signal_games": len(dc_signals),
        "double_chance_signal_accuracy": accuracy(dc_signals, "double_chance_result"),
        "full_match_signal_games": len(full_signals),
        "full_match_signal_accuracy": accuracy(full_signals, "full_match_result"),
        "goals_signal_games": len(goals_signals),
        "goals_signal_accuracy": accuracy(goals_signals, "scoring_result"),
        "btts_signal_games": len(btts_signals),
        "btts_signal_accuracy": accuracy(btts_signals, "btts_result"),
        "margin_mae": avg(row.get("margin_error") for row in completed),
        "total_mae": avg(row.get("total_error") for row in completed),
        "storage_backend": "Turso" if using_remote_history() else "SQLite",
        "db_path": os.environ.get("TURSO_DATABASE_URL", "") if using_remote_history() else str(db_path),
    }
