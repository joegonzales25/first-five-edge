import argparse
import csv
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import model_history


HISTORY_COLUMNS = [
    "model_version",
    "slate_date",
    "game",
    "market",
    "pick",
    "confidence",
    "score",
    "signal_type",
    "result",
    "outcome",
    "status",
    "created_at",
    "updated_at",
]


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_value(value):
    if value in ["", "None", "nan", "NaN"]:
        return None
    return value


def clean_score(value):
    value = clean_value(value)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_row(row):
    now = utc_now()
    normalized = {column: clean_value(row.get(column)) for column in HISTORY_COLUMNS}
    normalized["score"] = clean_score(normalized.get("score"))
    normalized["signal_type"] = normalized.get("signal_type")
    normalized["created_at"] = normalized.get("created_at") or now
    normalized["updated_at"] = normalized.get("updated_at") or normalized["created_at"]

    stored_outcome = clean_value(row.get("stored_outcome"))
    if stored_outcome and not normalized.get("outcome"):
        normalized["outcome"] = stored_outcome

    normalized["outcome"] = model_history.grade_history_row(
        normalized.get("market"),
        normalized.get("pick"),
        normalized.get("result"),
    )
    return normalized


def load_sqlite_rows(source_path):
    source_path = Path(source_path)
    if not source_path.exists():
        raise FileNotFoundError(f"SQLite history file not found: {source_path}")

    with sqlite3.connect(source_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT
                model_version,
                slate_date,
                game,
                market,
                pick,
                confidence,
                score,
                signal_type,
                result,
                outcome,
                status,
                created_at,
                updated_at
            FROM model_history
            ORDER BY date(slate_date), model_version, game, market
            """
        ).fetchall()

    return [normalize_row(dict(row)) for row in rows]


def load_csv_rows(source_path):
    source_path = Path(source_path)
    if not source_path.exists():
        raise FileNotFoundError(f"CSV history file not found: {source_path}")

    with source_path.open(newline="", encoding="utf-8-sig") as source_file:
        return [normalize_row(row) for row in csv.DictReader(source_file)]


def upsert_rows(rows, dry_run=False):
    if dry_run:
        return 0

    with model_history.connect() as connection:
        model_history.init_db(connection)
        for row in rows:
            connection.execute(
                """
                INSERT INTO model_history (
                    model_version, slate_date, game, market, pick,
                    confidence, score, signal_type, result, outcome, status,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(model_version, slate_date, game, market)
                DO UPDATE SET
                    result = excluded.result,
                    outcome = excluded.outcome,
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                tuple(row[column] for column in HISTORY_COLUMNS),
            )
        connection.commit()

    return len(rows)


def summarize(rows):
    dates = sorted({row["slate_date"] for row in rows if row.get("slate_date")})
    versions = sorted({row["model_version"] for row in rows if row.get("model_version")})
    return {
        "rows": len(rows),
        "date_range": f"{dates[0]} to {dates[-1]}" if dates else "N/A",
        "versions": ", ".join(versions) if versions else "N/A",
    }


def parse_args():
    parser = argparse.ArgumentParser(
        description="Migrate model_history rows from local SQLite or CSV into the configured history backend.",
    )
    parser.add_argument(
        "--source-sqlite",
        default=str(model_history.DB_PATH),
        help="Path to the source SQLite history DB.",
    )
    parser.add_argument(
        "--source-csv",
        help="Path to a Performance History CSV export to import.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read and summarize rows without writing to the target backend.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    source_description = args.source_csv or args.source_sqlite
    rows = load_csv_rows(args.source_csv) if args.source_csv else load_sqlite_rows(args.source_sqlite)
    summary = summarize(rows)

    print(f"Source: {source_description}")
    print(f"Target backend: {model_history.history_backend()}")
    print(f"Rows: {summary['rows']}")
    print(f"Date range: {summary['date_range']}")
    print(f"Model versions: {summary['versions']}")

    if model_history.history_backend() == "turso" and not os.environ.get("TURSO_AUTH_TOKEN"):
        raise RuntimeError("TURSO_AUTH_TOKEN is required for Turso migration.")

    written = upsert_rows(rows, dry_run=args.dry_run)
    print("Dry run complete." if args.dry_run else f"Migrated rows: {written}")


if __name__ == "__main__":
    main()
