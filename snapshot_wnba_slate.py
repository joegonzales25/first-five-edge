import argparse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from wnba_agent import build_current_slate
from wnba_model_history import record_wnba_history


DEFAULT_TIMEZONE = "America/New_York"
DEFAULT_MARKET_VERSION = "1.0.1-test"
DEFAULT_MODEL_VERSION = "1.0.0-test"
DEFAULT_SETTLEMENT_LOOKBACK_DAYS = 1


def parse_args():
    parser = argparse.ArgumentParser(
        description="Record the current WNBA slate snapshot for Edge Detector."
    )
    parser.add_argument(
        "--date",
        help="Slate date in YYYY-MM-DD format. Defaults to today in the selected timezone.",
    )
    parser.add_argument(
        "--timezone",
        default=DEFAULT_TIMEZONE,
        help=f"Timezone for slate selection and display. Defaults to {DEFAULT_TIMEZONE}.",
    )
    parser.add_argument(
        "--market-version",
        default=DEFAULT_MARKET_VERSION,
        help=f"WNBA market release. Defaults to {DEFAULT_MARKET_VERSION}.",
    )
    parser.add_argument(
        "--model-version",
        default=DEFAULT_MODEL_VERSION,
        help=f"WNBA model baseline. Defaults to {DEFAULT_MODEL_VERSION}.",
    )
    parser.add_argument(
        "--settlement-lookback-days",
        type=int,
        default=DEFAULT_SETTLEMENT_LOOKBACK_DAYS,
        help=(
            "When --date is omitted, also revisit this many previous slate dates "
            "to settle late finals. Defaults to 1."
        ),
    )
    return parser.parse_args()


def slate_date_for_args(date_value, timezone_name):
    if date_value:
        return datetime.strptime(date_value, "%Y-%m-%d").date()

    return datetime.now(ZoneInfo(timezone_name)).date()


def slate_dates_for_args(args):
    slate_date = slate_date_for_args(args.date, args.timezone)
    if args.date:
        return [slate_date]
    lookback_days = max(0, args.settlement_lookback_days)
    return [
        slate_date - timedelta(days=offset)
        for offset in range(lookback_days, -1, -1)
    ]


def record_slate_date(slate_date, args):
    slate, _ = build_current_slate(slate_date=slate_date)

    if slate is None or slate.empty:
        print(f"No WNBA games found for {slate_date}.")
        return {
            "games": 0,
            "inserted": 0,
            "updated": 0,
            "skipped_without_snapshot": 0,
        }

    counts = record_wnba_history(
        slate,
        slate_date,
        args.market_version,
        args.model_version,
    )
    print(
        f"Recorded WNBA snapshot for {slate_date}: "
        f"{len(slate)} games, market {args.market_version}, "
        f"model {args.model_version}, counts {counts}."
    )
    return {"games": len(slate), **counts}


def main():
    args = parse_args()
    totals = {
        "games": 0,
        "inserted": 0,
        "updated": 0,
        "skipped_without_snapshot": 0,
    }
    for slate_date in slate_dates_for_args(args):
        counts = record_slate_date(slate_date, args)
        for key in totals:
            totals[key] += counts.get(key, 0)

    print(f"WNBA snapshot run totals: {totals}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
