import json
from datetime import datetime, timezone

import pandas as pd

from nfl_challenger import CORE_FEATURES, OPTIONAL_FEATURES, normalize_features
from nfl_model_history import DB_PATH, connect, fetch_one, fetch_rows


SCHEDULE_SOURCE = "nflverse"
FEATURE_VERSION = "0.1.0-test"


def utc_now():
    return datetime.now(timezone.utc)


def clean_value(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def clean_int(value):
    value = clean_value(value)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def clean_float(value):
    value = clean_value(value)
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def clean_date(value):
    value = clean_value(value)
    if value is None:
        return None
    try:
        return pd.Timestamp(value).date().isoformat()
    except (TypeError, ValueError):
        return None


def schedule_kickoff(row):
    gameday = clean_date(row.get("gameday"))
    gametime = clean_value(row.get("gametime"))
    if gameday is None or gametime is None:
        return None
    raw = f"{gameday}T{gametime}"
    try:
        kickoff = pd.Timestamp(raw)
        if kickoff.tzinfo is None:
            kickoff = kickoff.tz_localize("America/New_York")
        return kickoff.tz_convert("UTC").isoformat()
    except Exception:
        return None


def schedule_status(row):
    away_score = clean_int(row.get("away_score"))
    home_score = clean_int(row.get("home_score"))
    return "Final" if away_score is not None and home_score is not None else "Scheduled"


def init_nfl_schedule_db(connection):
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS nfl_schedule (
            game_id TEXT PRIMARY KEY,
            season INTEGER NOT NULL,
            week INTEGER,
            game_type TEXT,
            slate_date TEXT,
            scheduled_kickoff TEXT,
            game_time TEXT,
            weekday TEXT,
            away_team TEXT,
            home_team TEXT,
            location TEXT,
            neutral_site INTEGER,
            stadium TEXT,
            roof TEXT,
            surface TEXT,
            away_rest REAL,
            home_rest REAL,
            status TEXT,
            away_score INTEGER,
            home_score INTEGER,
            source TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS nfl_pregame_features (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id TEXT NOT NULL,
            feature_version TEXT NOT NULL,
            as_of TEXT NOT NULL,
            source TEXT NOT NULL,
            net_epa_diff REAL,
            early_down_success_diff REAL,
            qb_epa_diff REAL,
            sack_rate_diff REAL,
            explosive_play_diff REAL,
            dvoa_diff REAL,
            pace_diff REAL,
            proe_diff REAL,
            drive_efficiency_sum REAL,
            weather_total_adjustment REAL,
            home_field REAL,
            rest_adjustment REAL,
            core_available INTEGER NOT NULL,
            core_required INTEGER NOT NULL,
            readiness TEXT NOT NULL,
            feature_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(game_id, feature_version, as_of)
        )
        """
    )
    connection.commit()


def schedule_values(row, now_text):
    game_id = clean_value(row.get("game_id"))
    location = clean_value(row.get("location"))
    return {
        "game_id": str(game_id or ""),
        "season": clean_int(row.get("season")),
        "week": clean_int(row.get("week")),
        "game_type": clean_value(row.get("game_type")),
        "slate_date": clean_date(row.get("gameday")),
        "scheduled_kickoff": schedule_kickoff(row),
        "game_time": clean_value(row.get("gametime")),
        "weekday": clean_value(row.get("weekday")),
        "away_team": clean_value(row.get("away_team")),
        "home_team": clean_value(row.get("home_team")),
        "location": location,
        "neutral_site": int(
            location is not None and str(location).lower() != "home"
        ),
        "stadium": clean_value(row.get("stadium")),
        "roof": clean_value(row.get("roof")),
        "surface": clean_value(row.get("surface")),
        "away_rest": clean_float(row.get("away_rest")),
        "home_rest": clean_float(row.get("home_rest")),
        "status": schedule_status(row),
        "away_score": clean_int(row.get("away_score")),
        "home_score": clean_int(row.get("home_score")),
        "source": SCHEDULE_SOURCE,
        "created_at": now_text,
        "updated_at": now_text,
    }


def insert_row(connection, table, values):
    columns = list(values)
    placeholders = ", ".join(["?"] * len(columns))
    connection.execute(
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
        [values[column] for column in columns],
    )


def update_schedule_row(connection, values):
    columns = [
        column
        for column in values
        if column not in {"game_id", "created_at"}
    ]
    connection.execute(
        f"""
        UPDATE nfl_schedule
        SET {', '.join(f'{column} = ?' for column in columns)}
        WHERE game_id = ?
        """,
        [*[values[column] for column in columns], values["game_id"]],
    )


def sync_nfl_schedule(games, season=None, db_path=DB_PATH, now=None):
    counts = {"inserted": 0, "updated": 0, "skipped": 0}
    if games is None or games.empty:
        return counts

    frame = games.copy()
    if "game_type" in frame:
        frame = frame[frame["game_type"].eq("REG")]
    if season is not None:
        frame = frame[frame["season"].eq(int(season))]

    now_text = (now or utc_now()).isoformat(timespec="seconds")
    with connect(db_path) as connection:
        init_nfl_schedule_db(connection)
        for _, row in frame.iterrows():
            values = schedule_values(row, now_text)
            if not values["game_id"] or values["season"] is None:
                counts["skipped"] += 1
                continue
            existing = fetch_one(
                connection,
                "SELECT game_id, created_at FROM nfl_schedule WHERE game_id = ?",
                (values["game_id"],),
            )
            if existing:
                values["created_at"] = existing.get("created_at") or now_text
                update_schedule_row(connection, values)
                counts["updated"] += 1
            else:
                insert_row(connection, "nfl_schedule", values)
                counts["inserted"] += 1
        connection.commit()
    return counts


def load_nfl_schedule_inventory(
    season=None,
    week=None,
    slate_date=None,
    db_path=DB_PATH,
):
    with connect(db_path) as connection:
        init_nfl_schedule_db(connection)
        where = []
        params = []
        for column, value in [
            ("season", season),
            ("week", week),
            ("slate_date", slate_date),
        ]:
            if value is not None:
                where.append(f"{column} = ?")
                params.append(value)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        return fetch_rows(
            connection,
            f"""
            SELECT *
            FROM nfl_schedule
            {clause}
            ORDER BY season, week, scheduled_kickoff, away_team, home_team
            """,
            params,
        )


def feature_values(row, feature_version, source, default_as_of, now_text):
    game_id = str(clean_value(row.get("game_id")) or "")
    raw_features = {
        column: clean_value(row.get(column))
        for column in (*CORE_FEATURES, *OPTIONAL_FEATURES)
    }
    features = normalize_features(raw_features)
    available = sum(features.get(column) is not None for column in CORE_FEATURES)
    required = len(CORE_FEATURES)
    if available == 0:
        readiness = "Awaiting Features"
    elif available < required:
        readiness = "Features Partial"
    else:
        readiness = "Model Ready"
    as_of = clean_value(row.get("as_of")) or default_as_of
    return {
        "game_id": game_id,
        "feature_version": feature_version,
        "as_of": str(as_of),
        "source": source,
        **{
            column: features.get(column)
            for column in (*CORE_FEATURES, *OPTIONAL_FEATURES)
        },
        "core_available": available,
        "core_required": required,
        "readiness": readiness,
        "feature_json": json.dumps(
            features,
            separators=(",", ":"),
            sort_keys=True,
        ),
        "created_at": now_text,
    }


def record_nfl_pregame_features(
    feature_frame,
    feature_version=FEATURE_VERSION,
    source="normalized-pregame",
    as_of=None,
    db_path=DB_PATH,
    now=None,
):
    counts = {"inserted": 0, "skipped": 0}
    if feature_frame is None or feature_frame.empty:
        return counts
    now_text = (now or utc_now()).isoformat(timespec="seconds")
    default_as_of = str(as_of or now_text)
    with connect(db_path) as connection:
        init_nfl_schedule_db(connection)
        for _, row in feature_frame.iterrows():
            values = feature_values(
                row,
                feature_version,
                source,
                default_as_of,
                now_text,
            )
            if not values["game_id"]:
                counts["skipped"] += 1
                continue
            existing = fetch_one(
                connection,
                """
                SELECT id FROM nfl_pregame_features
                WHERE game_id = ? AND feature_version = ? AND as_of = ?
                """,
                (
                    values["game_id"],
                    values["feature_version"],
                    values["as_of"],
                ),
            )
            if existing:
                counts["skipped"] += 1
                continue
            insert_row(connection, "nfl_pregame_features", values)
            counts["inserted"] += 1
        connection.commit()
    return counts


def load_latest_nfl_features(game_ids=None, db_path=DB_PATH):
    with connect(db_path) as connection:
        init_nfl_schedule_db(connection)
        rows = fetch_rows(
            connection,
            """
            SELECT features.*
            FROM nfl_pregame_features AS features
            WHERE features.id = (
                SELECT latest.id
                FROM nfl_pregame_features AS latest
                WHERE latest.game_id = features.game_id
                ORDER BY latest.as_of DESC, latest.id DESC
                LIMIT 1
            )
            ORDER BY features.game_id
            """,
        )
    if game_ids is None:
        return rows
    wanted = {str(game_id) for game_id in game_ids}
    return [row for row in rows if str(row.get("game_id")) in wanted]


def feature_rows_to_frame(rows):
    records = []
    for row in rows or []:
        try:
            features = json.loads(row.get("feature_json") or "{}")
        except (TypeError, ValueError):
            features = {}
        records.append({"game_id": row.get("game_id"), **features})
    return pd.DataFrame(records)
