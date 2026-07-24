import argparse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from nfl_agent import build_current_slate, load_nfl_schedule
from nfl_model_history import record_nfl_history


DEFAULT_TIMEZONE = "America/New_York"
DEFAULT_MARKET_VERSION = "1.1.0-test"
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
