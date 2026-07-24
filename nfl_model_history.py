import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from history_backend_config import resolve_history_backend


DB_PATH = Path(
    os.environ.get(
        "FIRST_FIVE_EDGE_NFL_HISTORY_DB",
        Path(tempfile.gettempdir()) / "first_five_edge_nfl_model_history.sqlite3",
    )
)


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


def using_remote_history():
    return resolve_history_backend() == "turso"


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
        CREATE TABLE IF NOT EXISTS nfl_model_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id TEXT NOT NULL,
            season INTEGER,
            week INTEGER,
            slate_date TEXT NOT NULL,
            scheduled_kickoff TEXT,
            game_time TEXT,
            game TEXT NOT NULL,
            away_team TEXT,
            home_team TEXT,
            market_version TEXT NOT NULL,
            model_version TEXT NOT NULL,
            model_signal TEXT,
            side_edge TEXT,
            predicted_winner TEXT,
            confidence TEXT,
            edge_score REAL,
            scoring_edge TEXT,
            model_margin REAL,
            projected_total REAL,
            league_total_baseline REAL,
            rest_edge REAL,
            agent_notes TEXT,
            side_tracking_segment TEXT,
            side_discovery_pick TEXT,
            side_discovery_label TEXT,
            side_result TEXT,
            side_discovery_result TEXT,
            scoring_tracking_segment TEXT,
            scoring_discovery_pick TEXT,
            scoring_discovery_label TEXT,
            scoring_result TEXT,
            scoring_discovery_result TEXT,
            status TEXT,
            away_score INTEGER,
            home_score INTEGER,
            actual_winner TEXT,
            actual_total REAL,
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
    existing_columns = {
        row["name"]
        for row in fetch_rows(connection, "PRAGMA table_info(nfl_model_history)")
    }
    optional_columns = {
        "agent_notes": "TEXT",
        "side_tracking_segment": "TEXT",
        "side_discovery_pick": "TEXT",
        "side_discovery_label": "TEXT",
        "side_result": "TEXT",
        "side_discovery_result": "TEXT",
        "scoring_tracking_segment": "TEXT",
        "scoring_discovery_pick": "TEXT",
        "scoring_discovery_label": "TEXT",
        "scoring_result": "TEXT",
        "scoring_discovery_result": "TEXT",
        "graded_at": "TEXT",
        "locked_at": "TEXT",
        "snapshot_status": "TEXT",
    }
    for column, column_type in optional_columns.items():
        if column not in existing_columns:
            connection.execute(
                f"ALTER TABLE nfl_model_history ADD COLUMN {column} {column_type}"
            )
    connection.commit()


def utc_now():
    return datetime.now(timezone.utc)


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


def is_final_status(status):
    return str(status or "").strip().lower() in {
        "final",
        "game over",
        "full time",
        "full-time",
    }


def snapshot_is_open(row, now):
    kickoff = parse_kickoff(row.get("Scheduled Kickoff"))
    if str(row.get("Status", "")).strip().lower() not in {
        "",
        "scheduled",
        "pre-game",
        "preview",
    }:
        return False
    return kickoff is None or now < kickoff


def grade_side(segment, pick, actual_winner, completed):
    if segment not in {"Official", "Lean", "Watch"} or not pick:
        return "No Signal"
    if not completed or actual_winner is None:
        return "Pending"
    if actual_winner == "Tie":
        return "Push"
    return "Correct" if pick == actual_winner else "Missed"


def grade_scoring(segment, pick, actual_total, baseline, completed):
    if segment not in {"Official", "Lean", "Watch"} or not pick:
        return "No Signal"
    if not completed or actual_total is None or baseline is None:
        return "Pending"
    if pick == "High Scoring Environment":
        return "Correct" if actual_total > baseline else "Missed"
    if pick == "Low Scoring Environment":
        return "Correct" if actual_total < baseline else "Missed"
    return "No Signal"


def prediction_values(row, market_version, model_version, now_text):
    return {
        "game_id": str(row.get("Game ID") or ""),
        "season": safe_int(row.get("Season")),
        "week": safe_int(row.get("Week")),
        "slate_date": str(row.get("Slate Date") or ""),
        "scheduled_kickoff": row.get("Scheduled Kickoff"),
        "game_time": row.get("Game Time"),
        "game": row.get("Game"),
        "away_team": row.get("Away"),
        "home_team": row.get("Home"),
        "market_version": market_version,
        "model_version": model_version,
        "model_signal": row.get("Model Signal"),
        "side_edge": row.get("Side Edge"),
        "predicted_winner": row.get("Predicted Winner"),
        "confidence": row.get("Confidence"),
        "edge_score": safe_float(row.get("Edge Score")),
        "scoring_edge": row.get("Scoring Edge"),
        "model_margin": safe_float(row.get("Model Margin")),
        "projected_total": safe_float(row.get("Projected Total")),
        "league_total_baseline": safe_float(
            row.get("League Total Baseline")
        ),
        "rest_edge": safe_float(row.get("Rest Edge")),
        "agent_notes": row.get("Agent Notes"),
        "side_tracking_segment": row.get("Side Tracking Segment"),
        "side_discovery_pick": row.get("Side Discovery Pick"),
        "side_discovery_label": row.get("Side Discovery Label"),
        "scoring_tracking_segment": row.get("Scoring Tracking Segment"),
        "scoring_discovery_pick": row.get("Scoring Discovery Pick"),
        "scoring_discovery_label": row.get("Scoring Discovery Label"),
        "status": row.get("Status"),
        "created_at": now_text,
        "updated_at": now_text,
        "snapshot_status": "Pregame",
    }


def result_values(row, stored, now_text):
    completed = is_final_status(row.get("Status"))
    away_score = safe_int(row.get("Away Score"))
    home_score = safe_int(row.get("Home Score"))
    actual_winner = row.get("Actual Winner")
    actual_total = safe_float(row.get("Actual Total"))
    model_margin = safe_float(stored.get("model_margin"))
    projected_total = safe_float(stored.get("projected_total"))
    actual_margin = (
        home_score - away_score
        if home_score is not None and away_score is not None
        else None
    )
    return {
        "status": row.get("Status"),
        "away_score": away_score,
        "home_score": home_score,
        "actual_winner": actual_winner,
        "actual_total": actual_total,
        "side_result": grade_side(
            stored.get("side_tracking_segment"),
            stored.get("predicted_winner"),
            actual_winner,
            completed,
        ),
        "side_discovery_result": grade_side(
            stored.get("side_tracking_segment"),
            stored.get("side_discovery_pick"),
            actual_winner,
            completed,
        ),
        "scoring_result": grade_scoring(
            stored.get("scoring_tracking_segment"),
            stored.get("scoring_edge"),
            actual_total,
            safe_float(stored.get("league_total_baseline")),
            completed,
        ),
        "scoring_discovery_result": grade_scoring(
            stored.get("scoring_tracking_segment"),
            stored.get("scoring_discovery_pick"),
            actual_total,
            safe_float(stored.get("league_total_baseline")),
            completed,
        ),
        "margin_error": (
            abs(model_margin - actual_margin)
            if model_margin is not None and actual_margin is not None
            else None
        ),
        "total_error": (
            abs(projected_total - actual_total)
            if projected_total is not None and actual_total is not None
            else None
        ),
        "updated_at": now_text,
        "graded_at": now_text if completed else None,
    }


def existing_snapshot(connection, game_id, market_version, model_version):
    return fetch_one(
        connection,
        """
        SELECT *
        FROM nfl_model_history
        WHERE game_id = ?
          AND market_version = ?
          AND model_version = ?
        """,
        (str(game_id), market_version, model_version),
    )


def insert_values(connection, values):
    columns = list(values)
    placeholders = ", ".join(["?"] * len(columns))
    connection.execute(
        f"""
        INSERT INTO nfl_model_history ({", ".join(columns)})
        VALUES ({placeholders})
        """,
        [values[column] for column in columns],
    )


def update_prediction(connection, row_id, values):
    immutable = {
        "game_id",
        "market_version",
        "model_version",
        "created_at",
        "snapshot_status",
    }
    columns = [column for column in values if column not in immutable]
    connection.execute(
        f"""
        UPDATE nfl_model_history
        SET {", ".join(f"{column} = ?" for column in columns)}
        WHERE id = ? AND snapshot_status = 'Pregame'
        """,
        [*[values[column] for column in columns], row_id],
    )


def update_result(connection, row_id, values, should_lock):
    connection.execute(
        """
        UPDATE nfl_model_history
        SET status = ?,
            away_score = ?,
            home_score = ?,
            actual_winner = ?,
            actual_total = ?,
            side_result = ?,
            side_discovery_result = ?,
            scoring_result = ?,
            scoring_discovery_result = ?,
            margin_error = ?,
            total_error = ?,
            updated_at = ?,
            graded_at = COALESCE(graded_at, ?),
            locked_at = CASE
                WHEN ? THEN COALESCE(locked_at, ?)
                ELSE locked_at
            END,
            snapshot_status = CASE
                WHEN snapshot_status = 'Not Tracked' THEN 'Not Tracked'
                WHEN ? THEN 'Locked'
                ELSE snapshot_status
            END
        WHERE id = ?
        """,
        (
            values["status"],
            values["away_score"],
            values["home_score"],
            values["actual_winner"],
            values["actual_total"],
            values["side_result"],
            values["side_discovery_result"],
            values["scoring_result"],
            values["scoring_discovery_result"],
            values["margin_error"],
            values["total_error"],
            values["updated_at"],
            values["graded_at"],
            should_lock,
            values["updated_at"],
            should_lock,
            row_id,
        ),
    )


def record_nfl_history(
    slate,
    market_version,
    model_version,
    db_path=DB_PATH,
    now=None,
):
    counts = {
        "inserted": 0,
        "updated": 0,
        "not_tracked": 0,
    }
    if slate is None or slate.empty:
        return counts

    now = now or utc_now()
    now_text = now.isoformat(timespec="seconds")
    with connect(db_path) as connection:
        init_db(connection)
        for _, row in slate.iterrows():
            game_id = row.get("Game ID")
            if not game_id:
                continue
            existing = existing_snapshot(
                connection,
                game_id,
                market_version,
                model_version,
            )
            is_open = snapshot_is_open(row, now)

            if existing is None:
                values = prediction_values(
                    row,
                    market_version,
                    model_version,
                    now_text,
                )
                if not is_open:
                    values["snapshot_status"] = "Not Tracked"
                    values["locked_at"] = now_text
                    counts["not_tracked"] += 1
                insert_values(connection, values)
                counts["inserted"] += 1
                existing = existing_snapshot(
                    connection,
                    game_id,
                    market_version,
                    model_version,
                )
            elif is_open and existing.get("snapshot_status") == "Pregame":
                update_prediction(
                    connection,
                    existing["id"],
                    prediction_values(
                        row,
                        market_version,
                        model_version,
                        now_text,
                    ),
                )
                counts["updated"] += 1
                continue

            should_lock = not is_open
            update_result(
                connection,
                existing["id"],
                result_values(row, existing, now_text),
                should_lock,
            )
            counts["updated"] += 1
        connection.commit()
    return counts


def load_nfl_history(
    model_version=None,
    market_version=None,
    season=None,
    week=None,
    db_path=DB_PATH,
):
    with connect(db_path) as connection:
        init_db(connection)
        where = []
        params = []
        for column, value in [
            ("model_version", model_version),
            ("market_version", market_version),
            ("season", season),
            ("week", week),
        ]:
            if value is not None:
                where.append(f"{column} = ?")
                params.append(value)
        where_clause = f"WHERE {' AND '.join(where)}" if where else ""
        return fetch_rows(
            connection,
            f"""
            SELECT *
            FROM nfl_model_history
            {where_clause}
            ORDER BY season DESC, week DESC, scheduled_kickoff, game
            """,
            params,
        )


def accuracy(rows, field):
    graded = [row for row in rows if row.get(field) in {"Correct", "Missed"}]
    if not graded:
        return 0.0
    return round(
        sum(row.get(field) == "Correct" for row in graded) / len(graded),
        4,
    )


def load_nfl_performance_summary(
    model_version=None,
    market_version=None,
    db_path=DB_PATH,
):
    rows = [
        row
        for row in load_nfl_history(
            model_version=model_version,
            market_version=market_version,
            db_path=db_path,
        )
        if row.get("snapshot_status") != "Not Tracked"
    ]
    side = [
        row
        for row in rows
        if row.get("side_tracking_segment") in {"Official", "Lean", "Watch"}
    ]
    scoring = [
        row
        for row in rows
        if row.get("scoring_tracking_segment") in {"Official", "Lean", "Watch"}
    ]
    completed = [row for row in rows if is_final_status(row.get("status"))]
    return {
        "snapshots": len(rows),
        "completed": len(completed),
        "side_signal_games": len(side),
        "side_signal_accuracy": accuracy(side, "side_result"),
        "scoring_signal_games": len(scoring),
        "scoring_signal_accuracy": accuracy(scoring, "scoring_result"),
        "storage_backend": "Turso" if using_remote_history() else "SQLite",
        "db_path": (
            os.environ.get("TURSO_DATABASE_URL", "")
            if using_remote_history()
            else str(db_path)
        ),
    }
