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


def connect(db_path=DB_PATH):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


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
            result TEXT,
            outcome TEXT,
            status TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(model_version, slate_date, game, market)
        )
        """
    )
    connection.commit()


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def is_no_edge_pick(pick):
    return str(pick).strip() in ["", "Pass", "No Edge", "F5 Pass", "No Edge (Pass)"]


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
            "result": row.get("Full Game Result", "Pending"),
            "status": status,
        },
    ]

    for history_row in rows:
        if history_row["market"] == "1st Inning":
            history_row["outcome"] = grade_first_inning(
                history_row["pick"],
                history_row["result"],
            )
        else:
            history_row["outcome"] = grade_team_pick(
                history_row["pick"],
                history_row["result"],
                "After 5:" if history_row["market"] == "First 5" else "Final:",
            )

    return rows


def record_model_history(games, slate_date, model_version, db_path=DB_PATH):
    if games is None or games.empty:
        return

    now = utc_now()
    with connect(db_path) as connection:
        init_db(connection)
        for _, row in games.iterrows():
            for history_row in market_rows_for_game(row, slate_date, model_version):
                connection.execute(
                    """
                    INSERT INTO model_history (
                        model_version, slate_date, game, market, pick,
                        confidence, score, result, outcome, status,
                        created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(model_version, slate_date, game, market)
                    DO UPDATE SET
                        result = excluded.result,
                        outcome = excluded.outcome,
                        status = excluded.status,
                        updated_at = excluded.updated_at
                    """,
                    (
                        history_row["model_version"],
                        history_row["slate_date"],
                        history_row["game"],
                        history_row["market"],
                        history_row["pick"],
                        history_row["confidence"],
                        history_row["score"],
                        history_row["result"],
                        history_row["outcome"],
                        history_row["status"],
                        now,
                        now,
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
    where_clause = "WHERE pick NOT IN ('No Edge', 'Pass', 'F5 Pass')"
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
    if not db_path.exists():
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
        rows = connection.execute(
            f"""
            SELECT
                market,
                COUNT(*) AS total,
                SUM(CASE WHEN outcome = 'Hit' THEN 1 ELSE 0 END) AS hits,
                SUM(CASE WHEN outcome = 'Miss' THEN 1 ELSE 0 END) AS misses,
                SUM(CASE WHEN outcome = 'Push' THEN 1 ELSE 0 END) AS pushes,
                SUM(CASE WHEN outcome = 'Pending' THEN 1 ELSE 0 END) AS pending
            FROM model_history
            {where_clause}
            GROUP BY market
            ORDER BY CASE market
                WHEN '1st Inning' THEN 1
                WHEN 'First 5' THEN 2
                WHEN 'Full Game' THEN 3
                ELSE 4
            END
            """,
            params,
        ).fetchall()

    return [dict(row) for row in rows]


def load_model_versions(db_path=DB_PATH):
    if not db_path.exists():
        return []

    with connect(db_path) as connection:
        init_db(connection)
        rows = connection.execute(
            """
            SELECT model_version, MAX(updated_at) AS latest_update
            FROM model_history
            GROUP BY model_version
            ORDER BY latest_update DESC, model_version DESC
            """
        ).fetchall()

    return [row["model_version"] for row in rows]


def load_history_diagnostics(db_path=DB_PATH):
    db_path = Path(db_path)
    diagnostics = {
        "storage_backend": "SQLite",
        "db_path": str(db_path),
        "exists": db_path.exists(),
        "size_bytes": db_path.stat().st_size if db_path.exists() else 0,
        "total_rows": 0,
        "completed_rows": 0,
        "pending_rows": 0,
        "no_edge_rows": 0,
        "model_versions": [],
        "earliest_slate_date": None,
        "latest_slate_date": None,
        "latest_update": None,
    }

    if not db_path.exists():
        return diagnostics

    with connect(db_path) as connection:
        init_db(connection)
        row = connection.execute(
            """
            SELECT
                COUNT(*) AS total_rows,
                SUM(CASE WHEN outcome IN ('Hit', 'Miss', 'Push') THEN 1 ELSE 0 END) AS completed_rows,
                SUM(CASE WHEN outcome = 'Pending' THEN 1 ELSE 0 END) AS pending_rows,
                SUM(CASE WHEN outcome = 'No Edge' THEN 1 ELSE 0 END) AS no_edge_rows,
                MIN(slate_date) AS earliest_slate_date,
                MAX(slate_date) AS latest_slate_date,
                MAX(updated_at) AS latest_update
            FROM model_history
            """
        ).fetchone()
        versions = connection.execute(
            """
            SELECT model_version
            FROM model_history
            GROUP BY model_version
            ORDER BY MAX(updated_at) DESC, model_version DESC
            """
        ).fetchall()

    if row:
        diagnostics.update(
            {
                "total_rows": row["total_rows"] or 0,
                "completed_rows": row["completed_rows"] or 0,
                "pending_rows": row["pending_rows"] or 0,
                "no_edge_rows": row["no_edge_rows"] or 0,
                "earliest_slate_date": row["earliest_slate_date"],
                "latest_slate_date": row["latest_slate_date"],
                "latest_update": row["latest_update"],
                "model_versions": [version["model_version"] for version in versions],
            }
        )

    return diagnostics


def load_performance_export_rows(model_version=None, db_path=DB_PATH):
    db_path = Path(db_path)
    if not db_path.exists():
        return []

    where_clause = ""
    params = []
    if model_version:
        where_clause = "WHERE model_version = ?"
        params.append(model_version)

    with connect(db_path) as connection:
        init_db(connection)
        rows = connection.execute(
            f"""
            SELECT
                model_version,
                slate_date,
                market,
                game,
                pick,
                confidence,
                score,
                result,
                outcome,
                status,
                created_at,
                updated_at
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
        ).fetchall()

    return [dict(row) for row in rows]


def load_performance_details(
    model_version=None,
    market=None,
    days=None,
    confidence=None,
    exact_date=None,
    limit=200,
    db_path=DB_PATH,
):
    if not db_path.exists():
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
        rows = connection.execute(
            f"""
            SELECT
                slate_date,
                market,
                game,
                pick,
                confidence,
                score,
                result,
                outcome,
                status,
                created_at,
                updated_at
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
        ).fetchall()

    return [dict(row) for row in rows]
