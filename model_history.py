import re
import sqlite3
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


DB_PATH = Path(
    os.environ.get(
        "FIRST_FIVE_EDGE_HISTORY_DB",
        Path(tempfile.gettempdir()) / "first_five_edge_model_history.sqlite3",
    )
)
MARKETS = ["1st Inning", "First 5", "Full Game"]


def history_backend():
    configured_backend = os.environ.get("HISTORY_BACKEND", "").strip().lower()
    if configured_backend:
        return configured_backend
    if os.environ.get("TURSO_DATABASE_URL") and os.environ.get("TURSO_AUTH_TOKEN"):
        return "turso"

    return "sqlite"


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
        CREATE TABLE IF NOT EXISTS model_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_version TEXT NOT NULL,
            slate_date TEXT NOT NULL,
            game TEXT NOT NULL,
            market TEXT NOT NULL,
            pick TEXT NOT NULL,
            confidence TEXT,
            score REAL,
            signal_type TEXT,
            result TEXT,
            outcome TEXT,
            status TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(model_version, slate_date, game, market)
        )
        """
    )
    columns = {
        row["name"]
        for row in fetch_rows(connection, "PRAGMA table_info(model_history)")
    }
    if "signal_type" not in columns:
        connection.execute("ALTER TABLE model_history ADD COLUMN signal_type TEXT")
    if "locked_at" not in columns:
        connection.execute("ALTER TABLE model_history ADD COLUMN locked_at TEXT")
    if "snapshot_status" not in columns:
        connection.execute("ALTER TABLE model_history ADD COLUMN snapshot_status TEXT")
    connection.commit()


def table_columns(connection):
    return {
        row["name"]
        for row in fetch_rows(connection, "PRAGMA table_info(model_history)")
    }


def optional_signal_type_select(connection):
    if "signal_type" in table_columns(connection):
        return "signal_type"

    return "NULL AS signal_type"


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def is_no_edge_pick(pick):
    return str(pick).strip() in [
        "",
        "Pass",
        "No Edge",
        "F5 Pass",
        "No Edge (Pass)",
        "Not Tracked",
    ]


def is_pregame_status(status):
    return str(status or "").strip().lower() in [
        "",
        "scheduled",
        "pre-game",
        "preview",
        "postponed",
    ]


def is_not_tracked_pick(pick):
    return str(pick or "").strip() == "Not Tracked"


def split_game_name(game_name):
    if " @ " in str(game_name):
        return str(game_name).split(" @ ", 1)

    return "Away", "Home"


def safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_score_result(result):
    text = str(result or "")
    match = re.match(r"^(?:After 5|Final|In Progress):\s*(.+?)\s+(\d+),\s*(.+?)\s+(\d+)$", text)
    if not match:
        return None

    return {
        "away_team": match.group(1),
        "away_score": int(match.group(2)),
        "home_team": match.group(3),
        "home_score": int(match.group(4)),
    }


def grade_first_inning(pick, result):
    if is_no_edge_pick(pick):
        return "No Edge"
    if result in ["Pending", "In Progress", "", None]:
        return "Pending"
    if result not in ["YRFI", "NRFI"]:
        return "Pending"

    return "Hit" if str(pick).upper() == result else "Miss"


def grade_team_pick(pick, result, completed_prefix):
    if is_no_edge_pick(pick):
        return "No Edge"

    if not str(result or "").startswith(completed_prefix):
        return "Pending"

    parsed = parse_score_result(result)
    if parsed is None:
        return "Pending"

    away_score = parsed["away_score"]
    home_score = parsed["home_score"]
    if away_score == home_score:
        return "Push"

    winner = parsed["away_team"] if away_score > home_score else parsed["home_team"]
    return "Hit" if str(pick) == winner else "Miss"


def grade_history_row(market, pick, result):
    if is_not_tracked_pick(pick):
        return "Not Tracked"
    if str(market) == "1st Inning":
        return grade_first_inning(pick, result)
    if str(market) == "First 5":
        return grade_team_pick(pick, result, "After 5:")
    if str(market) == "Full Game":
        return grade_team_pick(pick, result, "Final:")

    return "No Edge" if is_no_edge_pick(pick) else "Pending"


def market_rows_for_game(row, slate_date, model_version):
    game = row.get("Game", "")
    status = row.get("Status", "")

    rows = [
        {
            "model_version": model_version,
            "slate_date": str(slate_date),
            "game": game,
            "market": "1st Inning",
            "pick": row.get("First Inning Pick", "No Edge"),
            "confidence": row.get("First Inning Confidence", "No Edge"),
            "score": safe_float(row.get("First Inning Score")),
            "signal_type": row.get("First Inning Signal Type", "neutral"),
            "result": row.get("First Inning Result", "Pending"),
            "status": status,
        },
        {
            "model_version": model_version,
            "slate_date": str(slate_date),
            "game": game,
            "market": "First 5",
            "pick": row.get("F5 Pick", "No Edge"),
            "confidence": row.get("F5 Confidence", "No Edge"),
            "score": safe_float(row.get("F5 Score")),
            "signal_type": None,
            "result": row.get("F5 Result", "Pending"),
            "status": status,
        },
        {
            "model_version": model_version,
            "slate_date": str(slate_date),
            "game": game,
            "market": "Full Game",
            "pick": row.get("Full Game Pick", "No Edge"),
            "confidence": row.get("Full Game Confidence", "No Edge"),
            "score": safe_float(row.get("Full Game Score")),
            "signal_type": None,
            "result": row.get("Full Game Result", "Pending"),
            "status": status,
        },
    ]

    for history_row in rows:
        history_row["locked_at"] = None
        history_row["snapshot_status"] = "Pregame"
        history_row["outcome"] = grade_history_row(
            history_row["market"],
            history_row["pick"],
            history_row["result"],
        )

    return rows


def not_tracked_history_row(history_row, now):
    skipped_row = dict(history_row)
    skipped_row["pick"] = "Not Tracked"
    skipped_row["confidence"] = "Not Tracked"
    skipped_row["score"] = None
    skipped_row["outcome"] = "Not Tracked"
    skipped_row["locked_at"] = now
    skipped_row["snapshot_status"] = "Not Tracked"
    return skipped_row


def stored_row_is_locked(row):
    if row is None:
        return False
    return row.get("snapshot_status") in ["Locked", "Not Tracked"] or bool(row.get("locked_at"))


def record_model_history(games, slate_date, model_version, db_path=DB_PATH):
    if games is None or games.empty:
        return

    now = utc_now()
    with connect(db_path) as connection:
        init_db(connection)
        for _, row in games.iterrows():
            for history_row in market_rows_for_game(row, slate_date, model_version):
                existing_row = fetch_one(
                    connection,
                    """
                    SELECT market, pick, result, locked_at, snapshot_status
                    FROM model_history
                    WHERE model_version = ?
                        AND slate_date = ?
                        AND game = ?
                        AND market = ?
                    """,
                    (
                        history_row["model_version"],
                        history_row["slate_date"],
                        history_row["game"],
                        history_row["market"],
                    ),
                )

                if existing_row is None:
                    insert_row = history_row
                    if not is_pregame_status(history_row["status"]):
                        insert_row = not_tracked_history_row(history_row, now)
                    connection.execute(
                        """
                        INSERT INTO model_history (
                            model_version, slate_date, game, market, pick,
                            confidence, score, signal_type, result, outcome, status,
                            created_at, updated_at, locked_at, snapshot_status
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            insert_row["model_version"],
                            insert_row["slate_date"],
                            insert_row["game"],
                            insert_row["market"],
                            insert_row["pick"],
                            insert_row["confidence"],
                            insert_row["score"],
                            insert_row["signal_type"],
                            insert_row["result"],
                            insert_row["outcome"],
                            insert_row["status"],
                            now,
                            now,
                            insert_row["locked_at"],
                            insert_row["snapshot_status"],
                        ),
                    )
                    continue

                if stored_row_is_locked(existing_row):
                    outcome = grade_history_row(
                        existing_row["market"],
                        existing_row["pick"],
                        history_row["result"],
                    )
                    connection.execute(
                        """
                        UPDATE model_history
                        SET result = ?,
                            outcome = ?,
                            status = ?,
                            updated_at = ?
                        WHERE model_version = ?
                            AND slate_date = ?
                            AND game = ?
                            AND market = ?
                        """,
                        (
                            history_row["result"],
                            outcome,
                            history_row["status"],
                            now,
                            history_row["model_version"],
                            history_row["slate_date"],
                            history_row["game"],
                            history_row["market"],
                        ),
                    )
                    continue

                if is_pregame_status(history_row["status"]):
                    connection.execute(
                        """
                        UPDATE model_history
                        SET pick = ?,
                            confidence = ?,
                            score = ?,
                            signal_type = ?,
                            result = ?,
                            outcome = ?,
                            status = ?,
                            updated_at = ?,
                            snapshot_status = 'Pregame'
                        WHERE model_version = ?
                            AND slate_date = ?
                            AND game = ?
                            AND market = ?
                        """,
                        (
                            history_row["pick"],
                            history_row["confidence"],
                            history_row["score"],
                            history_row["signal_type"],
                            history_row["result"],
                            history_row["outcome"],
                            history_row["status"],
                            now,
                            history_row["model_version"],
                            history_row["slate_date"],
                            history_row["game"],
                            history_row["market"],
                        ),
                    )
                    continue

                outcome = grade_history_row(
                    existing_row["market"],
                    existing_row["pick"],
                    history_row["result"],
                )
                connection.execute(
                    """
                    UPDATE model_history
                    SET result = ?,
                        outcome = ?,
                        status = ?,
                        locked_at = ?,
                        snapshot_status = 'Locked',
                        updated_at = ?
                    WHERE model_version = ?
                        AND slate_date = ?
                        AND game = ?
                        AND market = ?
                    """,
                    (
                        history_row["result"],
                        outcome,
                        history_row["status"],
                        now,
                        now,
                        history_row["model_version"],
                        history_row["slate_date"],
                        history_row["game"],
                        history_row["market"],
                    ),
                )
        connection.commit()


def build_history_filters(
    model_version=None,
    market=None,
    days=None,
    confidence=None,
    exact_date=None,
):
    where_clause = "WHERE pick NOT IN ('No Edge', 'Pass', 'F5 Pass', 'Not Tracked')"
    params = []

    if model_version:
        where_clause += " AND model_version = ?"
        params.append(model_version)
    if market and market != "All":
        where_clause += " AND market = ?"
        params.append(market)
    if exact_date:
        where_clause += " AND slate_date = ?"
        params.append(str(exact_date))
    if days:
        where_clause += " AND date(slate_date) >= date('now', ?)"
        params.append(f"-{int(days)} days")
    if confidence and confidence != "All":
        where_clause += " AND confidence = ?"
        params.append(confidence)

    return where_clause, params


def load_performance_summary(
    model_version=None,
    market=None,
    days=None,
    confidence=None,
    exact_date=None,
    db_path=DB_PATH,
):
    if not using_remote_history() and not db_path.exists():
        return []

    where_clause, params = build_history_filters(
        model_version,
        market,
        days,
        confidence,
        exact_date,
    )

    with connect(db_path) as connection:
        init_db(connection)
        rows = fetch_rows(
            connection,
            f"""
            SELECT
                market,
                pick,
                result
            FROM model_history
            {where_clause}
            ORDER BY CASE market
                WHEN '1st Inning' THEN 1
                WHEN 'First 5' THEN 2
                WHEN 'Full Game' THEN 3
                ELSE 4
            END
            """,
            params,
        )

    summary = {}
    for row in rows:
        market_name = row["market"]
        outcome = grade_history_row(market_name, row["pick"], row["result"])
        if outcome == "No Edge":
            continue

        if market_name not in summary:
            summary[market_name] = {
                "market": market_name,
                "total": 0,
                "hits": 0,
                "misses": 0,
                "pushes": 0,
                "pending": 0,
            }

        summary[market_name]["total"] += 1
        if outcome == "Hit":
            summary[market_name]["hits"] += 1
        elif outcome == "Miss":
            summary[market_name]["misses"] += 1
        elif outcome == "Push":
            summary[market_name]["pushes"] += 1
        elif outcome == "Pending":
            summary[market_name]["pending"] += 1

    return list(summary.values())


def load_model_versions(db_path=DB_PATH):
    if not using_remote_history() and not db_path.exists():
        return []

    with connect(db_path) as connection:
        init_db(connection)
        rows = fetch_rows(
            connection,
            """
            SELECT model_version, MAX(updated_at) AS latest_update
            FROM model_history
            GROUP BY model_version
            ORDER BY latest_update DESC, model_version DESC
            """
        )

    return [row["model_version"] for row in rows]


def load_history_diagnostics(db_path=DB_PATH):
    db_path = Path(db_path)
    remote_history = using_remote_history()
    remote_url = os.environ.get("TURSO_DATABASE_URL", "")
    diagnostics = {
        "storage_backend": "Turso" if remote_history else "SQLite",
        "db_path": remote_url if remote_history else str(db_path),
        "exists": remote_history or db_path.exists(),
        "size_bytes": 0 if remote_history else db_path.stat().st_size if db_path.exists() else 0,
        "total_rows": 0,
        "completed_rows": 0,
        "pending_rows": 0,
        "no_edge_rows": 0,
        "not_tracked_rows": 0,
        "result_updated_rows": 0,
        "model_versions": [],
        "earliest_slate_date": None,
        "latest_slate_date": None,
        "earliest_snapshot": None,
        "latest_snapshot": None,
        "latest_update": None,
    }

    if not remote_history and not db_path.exists():
        return diagnostics

    with connect(db_path) as connection:
        init_db(connection)
        row = fetch_one(
            connection,
            """
            SELECT
                COUNT(*) AS total_rows,
                SUM(CASE WHEN outcome IN ('Hit', 'Miss', 'Push') THEN 1 ELSE 0 END) AS completed_rows,
                SUM(CASE WHEN outcome = 'Pending' THEN 1 ELSE 0 END) AS pending_rows,
                SUM(CASE WHEN outcome = 'No Edge' THEN 1 ELSE 0 END) AS no_edge_rows,
                SUM(CASE WHEN outcome = 'Not Tracked' THEN 1 ELSE 0 END) AS not_tracked_rows,
                SUM(CASE WHEN updated_at != created_at THEN 1 ELSE 0 END) AS result_updated_rows,
                MIN(slate_date) AS earliest_slate_date,
                MAX(slate_date) AS latest_slate_date,
                MIN(created_at) AS earliest_snapshot,
                MAX(created_at) AS latest_snapshot,
                MAX(updated_at) AS latest_update
            FROM model_history
            """
        )
        versions = fetch_rows(
            connection,
            """
            SELECT model_version
            FROM model_history
            GROUP BY model_version
            ORDER BY MAX(updated_at) DESC, model_version DESC
            """
        )

    if row:
        diagnostics.update(
            {
                "total_rows": row["total_rows"] or 0,
                "completed_rows": row["completed_rows"] or 0,
                "pending_rows": row["pending_rows"] or 0,
                "no_edge_rows": row["no_edge_rows"] or 0,
                "not_tracked_rows": row["not_tracked_rows"] or 0,
                "result_updated_rows": row["result_updated_rows"] or 0,
                "earliest_slate_date": row["earliest_slate_date"],
                "latest_slate_date": row["latest_slate_date"],
                "earliest_snapshot": row["earliest_snapshot"],
                "latest_snapshot": row["latest_snapshot"],
                "latest_update": row["latest_update"],
                "model_versions": [version["model_version"] for version in versions],
            }
        )

    return diagnostics


def load_performance_export_rows(model_version=None, db_path=DB_PATH):
    db_path = Path(db_path)
    if not using_remote_history() and not db_path.exists():
        return []

    where_clause = ""
    params = []
    if model_version:
        where_clause = "WHERE model_version = ?"
        params.append(model_version)

    with connect(db_path) as connection:
        init_db(connection)
        signal_type_select = optional_signal_type_select(connection)
        rows = fetch_rows(
            connection,
            f"""
            SELECT
                model_version,
                slate_date,
                market,
                game,
                pick,
                confidence,
                score,
                {signal_type_select},
                result,
                outcome AS stored_outcome,
                status,
                created_at,
                updated_at,
                locked_at,
                snapshot_status
            FROM model_history
            {where_clause}
            ORDER BY date(slate_date) DESC,
                CASE market
                    WHEN '1st Inning' THEN 1
                    WHEN 'First 5' THEN 2
                    WHEN 'Full Game' THEN 3
                    ELSE 4
            END,
                game
            """,
            params,
        )

    export_rows = []
    for row in rows:
        export_row = dict(row)
        export_row["outcome"] = grade_history_row(
            export_row["market"],
            export_row["pick"],
            export_row["result"],
        )
        export_rows.append(export_row)

    return export_rows


def load_slate_history_rows(model_version, slate_date, db_path=DB_PATH):
    db_path = Path(db_path)
    if not using_remote_history() and not db_path.exists():
        return []

    with connect(db_path) as connection:
        init_db(connection)
        signal_type_select = optional_signal_type_select(connection)
        return fetch_rows(
            connection,
            f"""
            SELECT
                slate_date,
                market,
                game,
                pick,
                confidence,
                score,
                {signal_type_select},
                result,
                outcome,
                status,
                created_at,
                updated_at,
                locked_at,
                snapshot_status
            FROM model_history
            WHERE model_version = ?
                AND slate_date = ?
            """,
            (model_version, str(slate_date)),
        )


def load_performance_details(
    model_version=None,
    market=None,
    days=None,
    confidence=None,
    exact_date=None,
    limit=200,
    db_path=DB_PATH,
):
    if not using_remote_history() and not db_path.exists():
        return []

    where_clause, params = build_history_filters(
        model_version,
        market,
        days,
        confidence,
        exact_date,
    )
    params.append(limit)

    with connect(db_path) as connection:
        init_db(connection)
        signal_type_select = optional_signal_type_select(connection)
        rows = fetch_rows(
            connection,
            f"""
            SELECT
                slate_date,
                market,
                game,
                pick,
                confidence,
                score,
                {signal_type_select},
                result,
                outcome AS stored_outcome,
                status,
                created_at,
                updated_at,
                locked_at,
                snapshot_status
            FROM model_history
            {where_clause}
            ORDER BY date(slate_date) DESC,
                CASE market
                    WHEN '1st Inning' THEN 1
                    WHEN 'First 5' THEN 2
                    WHEN 'Full Game' THEN 3
                    ELSE 4
                END,
                game
            LIMIT ?
            """,
            params,
        )

    detail_rows = []
    for row in rows:
        detail_row = dict(row)
        detail_row["outcome"] = grade_history_row(
            detail_row["market"],
            detail_row["pick"],
            detail_row["result"],
        )
        detail_rows.append(detail_row)

    return detail_rows
