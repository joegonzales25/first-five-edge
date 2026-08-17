import argparse
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from nfl_agent import build_current_slate, load_nfl_schedule
from nfl_challenger import attach_features, load_feature_file
from nfl_model_history import record_nfl_history
from nfl_schedule_store import (
    feature_rows_to_frame,
    load_latest_nfl_features,
    record_nfl_pregame_features,
    sync_nfl_schedule,
)


DEFAULT_TIMEZONE = "America/New_York"
DEFAULT_MARKET_VERSION = "1.2.0-test"
DEFAULT_MODEL_VERSION = "1.0.0"
DEFAULT_LOOKBACK_DAYS = 3
DEFAULT_LOOKAHEAD_DAYS = 8


def parse_args():
    parser = argparse.ArgumentParser(
        description="Record NFL monitored-test snapshots and settle recent games."
    )
    parser.add_argument(
        "--date",
        help="Reference date in YYYY-MM-DD format. Defaults to today ET.",
    )
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    parser.add_argument("--market-version", default=DEFAULT_MARKET_VERSION)
    parser.add_argument("--model-version", default=DEFAULT_MODEL_VERSION)
    parser.add_argument(
        "--challenger-features",
        default=os.environ.get("NFL_CHALLENGER_FEATURES_PATH"),
        help="Normalized pregame challenger feature CSV keyed by game_id.",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=DEFAULT_LOOKBACK_DAYS,
    )
    parser.add_argument(
        "--lookahead-days",
        type=int,
        default=DEFAULT_LOOKAHEAD_DAYS,
    )
    return parser.parse_args()


def reference_date(args):
    if args.date:
        return datetime.strptime(args.date, "%Y-%m-%d").date()
    return datetime.now(ZoneInfo(args.timezone)).date()


def season_for_date(target_date):
    return target_date.year if target_date.month >= 3 else target_date.year - 1


def target_weeks(games, target_date, lookback_days, lookahead_days):
    start = pd.Timestamp(target_date - timedelta(days=max(0, lookback_days)))
    end = pd.Timestamp(target_date + timedelta(days=max(0, lookahead_days)))
    active = games[
        games["gameday_dt"].notna()
        & (games["gameday_dt"] >= start)
        & (games["gameday_dt"] <= end)
    ]
    return sorted(
        {
            (int(row["season"]), int(row["week"]))
            for _, row in active.iterrows()
        }
    )


def main():
    args = parse_args()
    target_date = reference_date(args)
    games = load_nfl_schedule()
    sync_nfl_schedule(games, season=season_for_date(target_date))
    if args.challenger_features:
        feature_frame = load_feature_file(args.challenger_features)
        record_nfl_pregame_features(feature_frame)
        games = attach_features(
            games,
            feature_frame,
        )
    else:
        feature_frame = feature_rows_to_frame(
            load_latest_nfl_features(games["game_id"].astype(str).tolist())
        )
        if not feature_frame.empty:
            games = attach_features(games, feature_frame)
    weeks = target_weeks(
        games,
        target_date,
        args.lookback_days,
        args.lookahead_days,
    )
    if not weeks:
        print(f"No NFL regular-season games near {target_date}.")
        return 0

    totals = {"inserted": 0, "updated": 0, "not_tracked": 0}
    for season, week in weeks:
        slate, _ = build_current_slate(
            season=season,
            week=week,
            today=target_date,
            games=games,
        )
        counts = record_nfl_history(
            slate,
            args.market_version,
            args.model_version,
        )
        for key in totals:
            totals[key] += counts.get(key, 0)
        print(
            f"NFL season {season} week {week}: {len(slate)} games, "
            f"counts {counts}."
        )

    print(
        f"NFL snapshot totals for {target_date}: {totals}; "
        f"market {args.market_version}, model {args.model_version}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
